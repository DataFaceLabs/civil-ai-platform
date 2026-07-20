"""Tests for the /v1/data-proxy route group."""

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from civilai_platform.app import create_app
from civilai_platform.store import get_store
from tests.conftest import bootstrap_client_user


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIVILAI_DEV_AUTH", "true")
    monkeypatch.setenv("CIVILAI_STORE_BACKEND", "memory")
    monkeypatch.setenv("CIVILAI_ARTIFACT_BACKEND", "memory")
    monkeypatch.setenv("CIVILAI_DATA_API_BASE", "http://data.test")
    monkeypatch.delenv("CIVILAI_DEV_DATA_API_BASE", raising=False)
    monkeypatch.delenv("CIVILAI_DEV_DATA_ORIGINS", raising=False)
    get_store.cache_clear()


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


def _headers(user_id: str, tenant_id: str | None = None) -> dict[str, str]:
    h = {"X-Dev-User-Id": user_id}
    if tenant_id:
        h["X-Tenant-Id"] = tenant_id
    return h


def _bootstrap(client: TestClient, user_id: str) -> str:
    boot = bootstrap_client_user(client, user_id, name="Data Proxy Firm")
    return boot["memberships"][0]["tenant_id"]


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


@respx.mock
def test_site_by_entity_happy_path(client: TestClient) -> None:
    tenant_id = _bootstrap(client, "user-a")
    respx.get("http://data.test/v1/fe/site/by-entity/ent-1").mock(
        return_value=httpx.Response(200, json={"parcel": [], "zoning": []})
    )
    res = client.get(
        "/v1/data-proxy/fe/site/by-entity/ent-1",
        headers=_headers("user-a", tenant_id),
    )
    assert res.status_code == 200
    assert res.json()["parcel"] == []


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
    from starlette.requests import Request

    from civilai_platform.api.routes.data_proxy import get_data_proxy

    request = Request({"type": "http", "headers": []})
    client = get_data_proxy(request)
    assert client.include_pii is False


def test_passthrough_requires_authentication(client: TestClient) -> None:
    res = client.get("/v1/data-proxy/passthrough/sections/zoning/facts/ent-1")
    assert res.status_code == 401


def test_passthrough_rejects_paths_outside_allowlist(client: TestClient) -> None:
    tenant_id = _bootstrap(client, "user-a")
    # An admin/experimental path must not be reachable through the browser proxy.
    res = client.post(
        "/v1/data-proxy/passthrough/experimental/llm/invoke",
        json={"prompt": "x"},
        headers=_headers("user-a", tenant_id),
    )
    assert res.status_code == 403


@respx.mock
def test_passthrough_get_forwards_with_service_key(client: TestClient) -> None:
    tenant_id = _bootstrap(client, "user-a")
    route = respx.get("http://data.test/v1/sections/flood/facts/ent-1").mock(
        return_value=httpx.Response(200, json={"entity_id": "ent-1", "facts": [1]})
    )
    res = client.get(
        "/v1/data-proxy/passthrough/sections/flood/facts/ent-1",
        headers=_headers("user-a", tenant_id),
    )
    assert res.status_code == 200
    assert res.json()["facts"] == [1]
    # Service key injected server-side; PII scope never requested.
    sent = route.calls.last.request
    assert "X-Data-Scopes" not in sent.headers


@respx.mock
def test_passthrough_routes_allowlisted_develop_origin_to_dev_data(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CIVILAI_DEV_DATA_API_BASE", "http://dev-data.test")
    monkeypatch.setenv("CIVILAI_DEV_DATA_ORIGINS", "https://develop.example.com")
    tenant_id = _bootstrap(client, "user-dev")
    route = respx.get("http://dev-data.test/v1/sections/flood/facts/ent-1").mock(
        return_value=httpx.Response(200, json={"entity_id": "ent-1", "plane": "dev"})
    )

    res = client.get(
        "/v1/data-proxy/passthrough/sections/flood/facts/ent-1",
        headers={
            **_headers("user-dev", tenant_id),
            "Origin": "https://develop.example.com",
        },
    )

    assert res.status_code == 200
    assert res.json()["plane"] == "dev"
    assert route.called


@respx.mock
def test_passthrough_post_preserves_409_body(client: TestClient) -> None:
    """A 409 ambiguous-address response must reach the FE intact, not become a 500."""
    tenant_id = _bootstrap(client, "user-a")
    respx.post("http://data.test/v1/fe/site/resolve-address").mock(
        return_value=httpx.Response(409, json={"message": "ambiguous", "candidates": []})
    )
    res = client.post(
        "/v1/data-proxy/passthrough/fe/site/resolve-address",
        json={"address": "123 Main St"},
        headers=_headers("user-a", tenant_id),
    )
    assert res.status_code == 409
    assert res.json()["message"] == "ambiguous"


@respx.mock
def test_passthrough_preserves_404(client: TestClient) -> None:
    """404 must pass through so the FE can skip an unavailable section."""
    tenant_id = _bootstrap(client, "user-a")
    respx.get("http://data.test/v1/sections/soils/facts/ent-1").mock(
        return_value=httpx.Response(404, json={"detail": "no facts"})
    )
    res = client.get(
        "/v1/data-proxy/passthrough/sections/soils/facts/ent-1",
        headers=_headers("user-a", tenant_id),
    )
    assert res.status_code == 404
