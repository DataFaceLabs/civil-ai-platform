import mimetypes
import uuid
from functools import lru_cache

import boto3

from civilai_platform.models.api import ArtifactPresignRequest, ArtifactPresignResponse
from civilai_platform.settings import get_settings

_memory_artifacts: dict[str, bytes] = {}


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
