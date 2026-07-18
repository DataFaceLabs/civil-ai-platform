import mimetypes
import secrets
import time
import uuid
from functools import lru_cache

import boto3

from civilai_platform.models.api import (
    ArtifactDownloadUrlResponse,
    ArtifactPresignRequest,
    ArtifactPresignResponse,
    LogoPresignRequest,
    LogoPresignResponse,
)
from civilai_platform.settings import get_settings
from civilai_platform.store.keys import tenant_logo_s3_key

_memory_artifacts: dict[str, bytes] = {}
# Short-lived tokens so Microsoft Office Online can fetch a file without auth.
# token -> (s3_key, expires_at_epoch)
_preview_tokens: dict[str, tuple[str, float]] = {}


@lru_cache
def _s3_client():
    settings = get_settings()
    session = boto3.Session(profile_name=settings.aws_profile, region_name=settings.aws_region)
    return session.client("s3")


def artifact_s3_key(tenant_id: str, project_id: str, kind: str, filename: str) -> str:
    safe = filename.replace("/", "_")
    if kind == "feasibility_html":
        return f"tenant/{tenant_id}/project/{project_id}/state/feasibility.html"
    return f"tenant/{tenant_id}/project/{project_id}/uploads/{uuid.uuid4()}/{safe}"


def assert_project_artifact_key(tenant_id: str, project_id: str, key: str) -> None:
    prefix = f"tenant/{tenant_id}/project/{project_id}/"
    if not key.startswith(prefix):
        raise ValueError("Artifact key does not belong to this project")


def tenant_logo_url(logo_s3_key: str | None) -> str | None:
    if not logo_s3_key:
        return None
    settings = get_settings()
    if settings.artifact_backend == "s3" and settings.app_bucket:
        return _s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.app_bucket, "Key": logo_s3_key},
            ExpiresIn=3600,
        )
    return f"/v1/tenant/logo/download?key={logo_s3_key}"


def presign_tenant_logo(*, tenant_id: str, request: LogoPresignRequest) -> LogoPresignResponse:
    settings = get_settings()
    key = tenant_logo_s3_key(tenant_id, request.filename)
    expires = 3600
    if settings.artifact_backend == "s3" and settings.app_bucket:
        url = _s3_client().generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.app_bucket,
                "Key": key,
                "ContentType": request.content_type,
            },
            ExpiresIn=expires,
        )
        return LogoPresignResponse(upload_url=url, s3_key=key, expires_in=expires)
    return LogoPresignResponse(
        upload_url=f"/v1/tenant/logo/upload?key={key}",
        s3_key=key,
        expires_in=expires,
    )


def presign_upload(
    *,
    tenant_id: str,
    project_id: str,
    request: ArtifactPresignRequest,
) -> ArtifactPresignResponse:
    settings = get_settings()
    key = artifact_s3_key(tenant_id, project_id, request.kind, request.filename)
    expires = 3600

    if settings.artifact_backend == "s3" and settings.app_bucket:
        url = _s3_client().generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.app_bucket,
                "Key": key,
                "ContentType": request.content_type,
            },
            ExpiresIn=expires,
        )
        return ArtifactPresignResponse(upload_url=url, s3_key=key, expires_in=expires)

    # Local dev: fake presign URL pointing to platform upload endpoint
    return ArtifactPresignResponse(
        upload_url=f"/v1/projects/{project_id}/artifacts/upload?key={key}",
        s3_key=key,
        expires_in=expires,
    )


def _purge_expired_preview_tokens(now: float | None = None) -> None:
    current = time.time() if now is None else now
    expired = [token for token, (_, exp) in _preview_tokens.items() if exp <= current]
    for token in expired:
        _preview_tokens.pop(token, None)


def issue_preview_token(key: str, expires_in: int = 3600) -> str:
    _purge_expired_preview_tokens()
    token = secrets.token_urlsafe(32)
    _preview_tokens[token] = (key, time.time() + expires_in)
    return token


def resolve_preview_token(token: str) -> str | None:
    _purge_expired_preview_tokens()
    entry = _preview_tokens.get(token)
    if not entry:
        return None
    key, expires_at = entry
    if expires_at <= time.time():
        _preview_tokens.pop(token, None)
        return None
    return key


def presign_download(*, key: str) -> ArtifactDownloadUrlResponse:
    """Return a time-limited URL Microsoft Office Online (or a browser) can GET without auth."""
    settings = get_settings()
    expires = 3600
    if settings.artifact_backend == "s3" and settings.app_bucket:
        url = _s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.app_bucket, "Key": key},
            ExpiresIn=expires,
        )
        return ArtifactDownloadUrlResponse(download_url=url, expires_in=expires)

    token = issue_preview_token(key, expires)
    return ArtifactDownloadUrlResponse(
        download_url=f"/v1/public/artifacts/{token}",
        expires_in=expires,
    )


def store_memory_artifact(key: str, data: bytes) -> None:
    _memory_artifacts[key] = data


def get_memory_artifact(key: str) -> bytes | None:
    return _memory_artifacts.get(key)


def artifact_media_type(key: str) -> str:
    filename = key.rsplit("/", 1)[-1]
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def download_artifact_bytes(key: str) -> bytes | None:
    settings = get_settings()
    if settings.artifact_backend == "memory":
        return get_memory_artifact(key)
    if settings.artifact_backend == "s3" and settings.app_bucket:
        obj = _s3_client().get_object(Bucket=settings.app_bucket, Key=key)
        return obj["Body"].read()
    return None
