"""Unit tests for S3 artifact download error handling and Lambda-safe redirects."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from civilai_platform.app import create_app
from civilai_platform.models.api import ArtifactDownloadUrlResponse
from civilai_platform.services import artifacts as artifact_svc
from civilai_platform.store import get_store
from tests.conftest import bootstrap_client_user


def _client_error(code: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": "missing"}},
        "GetObject",
    )


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIVILAI_DEV_AUTH", "true")
    monkeypatch.setenv("CIVILAI_STORE_BACKEND", "memory")
    monkeypatch.setenv("CIVILAI_ARTIFACT_BACKEND", "memory")
    get_store.cache_clear()


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


def test_download_artifact_bytes_returns_none_for_missing_s3_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = MagicMock()
    settings.artifact_backend = "s3"
    settings.app_bucket = "civilai-app-uat"
    monkeypatch.setattr(artifact_svc, "get_settings", lambda: settings)

    client = MagicMock()
    client.get_object.side_effect = _client_error("NoSuchKey")
    monkeypatch.setattr(artifact_svc, "_s3_client", lambda: client)

    assert artifact_svc.download_artifact_bytes("tenant/t/project/p/uploads/x.png") is None


def test_download_artifact_bytes_reraises_unexpected_s3_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = MagicMock()
    settings.artifact_backend = "s3"
    settings.app_bucket = "civilai-app-uat"
    monkeypatch.setattr(artifact_svc, "get_settings", lambda: settings)

    client = MagicMock()
    client.get_object.side_effect = _client_error("AccessDenied")
    monkeypatch.setattr(artifact_svc, "_s3_client", lambda: client)

    with pytest.raises(ClientError):
        artifact_svc.download_artifact_bytes("tenant/t/project/p/uploads/x.png")


def test_download_artifact_redirects_to_presign_on_s3_backend(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    """S3 mode must not stream bytes through Lambda (6MB sync response limit)."""
    boot = bootstrap_client_user(client, "artifact-user")
    tenant_id = boot["memberships"][0]["tenant_id"]
    headers = {"X-Dev-User-Id": "artifact-user", "X-Tenant-Id": tenant_id}

    proj = client.post(
        "/v1/projects",
        json={
            "name": "Exhibit Project",
            "address": "1 Main",
            "jurisdiction": "Travis County",
        },
        headers=headers,
    )
    assert proj.status_code == 201, proj.text
    project_id = proj.json()["project_id"]
    key = f"tenant/{tenant_id}/project/{project_id}/uploads/abc/New Exhibit 2.png"

    settings = MagicMock()
    settings.artifact_backend = "s3"
    settings.app_bucket = "civilai-data"
    # download_artifact imports get_settings locally from settings module.
    monkeypatch.setattr(
        "civilai_platform.settings.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        artifact_svc,
        "presign_download",
        lambda *, key: ArtifactDownloadUrlResponse(
            download_url=f"https://s3.example/presigned?key={key}",
            expires_in=3600,
        ),
    )

    # follow_redirects=False so we assert the 307 itself (not a follow-on GET).
    res = client.get(
        f"/v1/projects/{project_id}/artifacts/download",
        params={"key": key},
        headers=headers,
        follow_redirects=False,
    )
    assert res.status_code == 307
    from urllib.parse import unquote

    assert unquote(res.headers["location"]) == f"https://s3.example/presigned?key={key}"
