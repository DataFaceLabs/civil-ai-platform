"""Tests for fail-closed browser-Origin data-plane selection."""

import pytest

from civilai_platform.services.data_routing import data_api_base_for_origin


@pytest.fixture(autouse=True)
def _routing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIVILAI_DATA_API_BASE", "http://prod.test:8000")
    monkeypatch.setenv("CIVILAI_DEV_DATA_API_BASE", "http://dev.test:8001")
    monkeypatch.setenv(
        "CIVILAI_DEV_DATA_ORIGINS",
        "https://develop.example.com,https://preview.example.com/",
    )


@pytest.mark.parametrize(
    "origin",
    [
        "https://develop.example.com",
        "https://develop.example.com/",
        "https://preview.example.com",
    ],
)
def test_allowlisted_origin_selects_dev(origin: str) -> None:
    assert data_api_base_for_origin(origin) == "http://dev.test:8001"


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "",
        "https://www.civil1.ai",
        "https://develop.example.com.evil.test",
        "http://develop.example.com",
    ],
)
def test_missing_or_untrusted_origin_fails_closed_to_prod(origin: str | None) -> None:
    assert data_api_base_for_origin(origin) == "http://prod.test:8000"


def test_missing_dev_base_fails_closed_to_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CIVILAI_DEV_DATA_API_BASE")
    assert data_api_base_for_origin("https://develop.example.com") == "http://prod.test:8000"
