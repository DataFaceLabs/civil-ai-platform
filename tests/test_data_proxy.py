"""Tests for data API proxy client."""

import httpx
import respx

from civilai_platform.services.data_proxy import DataProxyClient


@respx.mock
def test_data_proxy_forwards_service_key_and_pii_scope(monkeypatch) -> None:
    monkeypatch.setenv("CIVILAI_DATA_SERVICE_KEY", "test-key")
    route = respx.get("http://data.test/v1/entities/ent-1/determinations").mock(
        return_value=httpx.Response(200, json={"entity_id": "ent-1", "determinations": []})
    )
    client = DataProxyClient(base_url="http://data.test", service_key="test-key", include_pii=True)
    result = client.run_determinations("ent-1")
    assert result["entity_id"] == "ent-1"
    assert route.called
    assert route.calls[0].request.headers["X-Data-Service-Key"] == "test-key"
    assert route.calls[0].request.headers["X-Data-Scopes"] == "pii"


@respx.mock
def test_data_proxy_resolve_parcel_by_address() -> None:
    route = respx.post("http://data.test/v1/entities/resolve").mock(
        return_value=httpx.Response(200, json={"entity_id": "ent-1"})
    )
    client = DataProxyClient(base_url="http://data.test")
    result = client.resolve_parcel(address="123 Main St")
    assert result["entity_id"] == "ent-1"
    assert route.called
    assert route.calls[0].request.content == b'{"address":"123 Main St"}'


@respx.mock
def test_data_proxy_resolve_parcel_by_parcel_id() -> None:
    route = respx.post("http://data.test/v1/entities/resolve").mock(
        return_value=httpx.Response(200, json={"entity_id": "ent-1"})
    )
    client = DataProxyClient(base_url="http://data.test")
    result = client.resolve_parcel(parcel_id="870361")
    assert result["entity_id"] == "ent-1"
    assert route.called
    assert route.calls[0].request.content == b'{"parcel_id":"870361"}'


@respx.mock
def test_data_proxy_get_site() -> None:
    route = respx.get("http://data.test/v1/fe/site/by-entity/ent-1").mock(
        return_value=httpx.Response(200, json={"entity_id": "ent-1", "site": {}})
    )
    client = DataProxyClient(base_url="http://data.test")
    result = client.get_site("ent-1")
    assert result["entity_id"] == "ent-1"
    assert route.called
