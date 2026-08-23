"""Develop-plane Lambda env: no Origin split, always ``:8001``."""

from __future__ import annotations

import pytest

from civilai_platform.services.data_routing import data_api_base_for_origin

_DEVELOP_DATA_API = "http://data-api.test:8001"


@pytest.fixture(autouse=True)
def _develop_plane_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Match tofu for ``civilai-develop-api`` (primary = :8001, empty split)."""
    monkeypatch.setenv("CIVILAI_DATA_API_BASE", _DEVELOP_DATA_API)
    monkeypatch.delenv("CIVILAI_DEV_DATA_API_BASE", raising=False)
    monkeypatch.setenv("CIVILAI_DEV_DATA_ORIGINS", "")


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "",
        "https://www.civil1.ai",
        "https://develop.d3joxyeudajkza.amplifyapp.com",
    ],
)
def test_develop_lambda_always_uses_primary_data_api(origin: str | None) -> None:
    """Every Origin must hit :8001; the customer table/path is not selected here."""
    assert data_api_base_for_origin(origin) == _DEVELOP_DATA_API
