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
