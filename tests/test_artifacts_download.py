"""Unit tests for S3 artifact download error handling."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from civilai_platform.services import artifacts as artifact_svc


def _client_error(code: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": "missing"}},
        "GetObject",
    )


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
