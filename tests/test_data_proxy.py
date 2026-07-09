"""Tests for data API proxy client."""

import httpx
import respx

from civilai_platform.services.data_proxy import DataProxyClient, llm_invoke_timeout_sec


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


def test_llm_invoke_timeout_default() -> None:
    assert llm_invoke_timeout_sec() == 180.0


def test_llm_invoke_timeout_from_env(monkeypatch) -> None:
    monkeypatch.setenv("CIVILAI_DATA_LLM_INVOKE_TIMEOUT_SEC", "240")
    assert llm_invoke_timeout_sec() == 240.0


@respx.mock
def test_data_proxy_invoke_llm_uses_longer_timeout(monkeypatch) -> None:
    monkeypatch.setenv("CIVILAI_DATA_LLM_INVOKE_TIMEOUT_SEC", "150")
    route = respx.post("http://data.test/v1/experimental/llm/invoke").mock(
        return_value=httpx.Response(200, json={"text": "ok", "model_id": "gpt-5.5"})
    )
    client = DataProxyClient(base_url="http://data.test", timeout=30.0)
    result = client.invoke_llm({"user_prompt": "hello"})
    assert result["text"] == "ok"
    assert route.called
    assert route.calls[0].request.extensions["timeout"]["connect"] == 150.0
