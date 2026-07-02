"""Tests for the /v1/data-proxy route group."""

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from civilai_platform.app import create_app
from civilai_platform.store import get_store


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIVILAI_DEV_AUTH", "true")
    monkeypatch.setenv("CIVILAI_STORE_BACKEND", "memory")
    monkeypatch.setenv("CIVILAI_ARTIFACT_BACKEND", "memory")
    monkeypatch.setenv("CIVILAI_DATA_API_BASE", "http://data.test")
    get_store.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _headers(user_id: str, tenant_id: str | None = None) -> dict[str, str]:
    h = {"X-Dev-User-Id": user_id}
    if tenant_id:
        h["X-Tenant-Id"] = tenant_id
    return h


def _bootstrap(client: TestClient, user_id: str) -> str:
    res = client.post(
        "/v1/dev/bootstrap",
        json={"name": "Data Proxy Firm", "email": f"{user_id}@example.com"},
        headers=_headers(user_id),
    )
    assert res.status_code == 200
    return res.json()["memberships"][0]["tenant_id"]


def test_resolve_requires_authentication(client: TestClient) -> None:
    res = client.post("/v1/data-proxy/entities/resolve", json={"address": "123 Main St"})
    assert res.status_code == 401


def test_resolve_requires_tenant_header(client: TestClient) -> None:
    # Authenticated user with no X-Tenant-Id at all.
    res = client.post(
        "/v1/data-proxy/entities/resolve",
        json={"address": "123 Main St"},
        headers=_headers("user-no-membership"),
    )
    assert res.status_code == 400


def test_resolve_requires_membership(client: TestClient) -> None:
    # Authenticated user with a tenant header but no membership in that tenant.
    tenant_id = _bootstrap(client, "user-a")
    res = client.post(
        "/v1/data-proxy/entities/resolve",
        json={"address": "123 Main St"},
        headers=_headers("user-no-membership", tenant_id),
    )
    assert res.status_code == 403


@respx.mock
def test_resolve_happy_path(client: TestClient) -> None:
    tenant_id = _bootstrap(client, "user-a")
    respx.post("http://data.test/v1/entities/resolve").mock(
        return_value=httpx.Response(200, json={"entity_id": "ent-1"})
    )
    res = client.post(
        "/v1/data-proxy/entities/resolve",
        json={"address": "123 Main St"},
        headers=_headers("user-a", tenant_id),
    )
    assert res.status_code == 200
    assert res.json()["entity_id"] == "ent-1"


@respx.mock
def test_section_facts_happy_path(client: TestClient) -> None:
    tenant_id = _bootstrap(client, "user-a")
    respx.get("http://data.test/v1/sections/zoning/facts/ent-1").mock(
        return_value=httpx.Response(200, json={"entity_id": "ent-1", "facts": []})
    )
    res = client.get(
        "/v1/data-proxy/sections/zoning/facts/ent-1",
        headers=_headers("user-a", tenant_id),
    )
    assert res.status_code == 200
    assert res.json()["entity_id"] == "ent-1"


def test_section_facts_requires_authentication(client: TestClient) -> None:
    res = client.get("/v1/data-proxy/sections/zoning/facts/ent-1")
    assert res.status_code == 401


def test_site_by_entity_returns_501_until_backend_route_exists(client: TestClient) -> None:
    tenant_id = _bootstrap(client, "user-a")
    res = client.get(
        "/v1/data-proxy/fe/site/by-entity/ent-1",
        headers=_headers("user-a", tenant_id),
    )
    assert res.status_code == 501


def test_site_by_entity_requires_authentication(client: TestClient) -> None:
    res = client.get("/v1/data-proxy/fe/site/by-entity/ent-1")
    assert res.status_code == 401


@respx.mock
def test_determinations_happy_path(client: TestClient) -> None:
    tenant_id = _bootstrap(client, "user-a")
    respx.get("http://data.test/v1/entities/ent-1/determinations").mock(
        return_value=httpx.Response(200, json={"entity_id": "ent-1", "determinations": []})
    )
    res = client.get(
        "/v1/data-proxy/entities/ent-1/determinations",
        headers=_headers("user-a", tenant_id),
    )
    assert res.status_code == 200
    assert res.json()["entity_id"] == "ent-1"


def test_determinations_requires_authentication(client: TestClient) -> None:
    res = client.get("/v1/data-proxy/entities/ent-1/determinations")
    assert res.status_code == 401


def test_resolve_body_has_no_pii_scope_field() -> None:
    """No request field exists to request the pii scope through this proxy."""
    from civilai_platform.api.routes.data_proxy import ResolveBody

    assert set(ResolveBody.model_fields) == {"address", "parcel_id"}


def test_data_proxy_dependency_never_requests_pii() -> None:
    """The route-level DataProxyClient factory must not opt into PII scope."""
    from civilai_platform.api.routes.data_proxy import get_data_proxy

    client = get_data_proxy()
    assert client.include_pii is False
