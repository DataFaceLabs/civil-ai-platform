"""Platform proxy to civil-ai-data governed APIs."""

from __future__ import annotations

import os
from typing import Any

import httpx

from civilai_platform.settings import get_settings

_DEFAULT_TIMEOUT_SEC = 30.0
_DEFAULT_LLM_INVOKE_TIMEOUT_SEC = 180.0


def llm_invoke_timeout_sec() -> float:
    """Match civil-ai-data OpenAI client budget (120s) plus web-search headroom."""
    raw = os.getenv("CIVILAI_DATA_LLM_INVOKE_TIMEOUT_SEC", "").strip()
    if not raw:
        return _DEFAULT_LLM_INVOKE_TIMEOUT_SEC
    try:
        return max(float(raw), 1.0)
    except ValueError:
        return _DEFAULT_LLM_INVOKE_TIMEOUT_SEC


def _upstream_error_message(exc: httpx.HTTPStatusError) -> str:
    try:
        payload = exc.response.json()
    except ValueError:
        return exc.response.text.strip() or str(exc)
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
    return exc.response.text.strip() or str(exc)


class DataProxyClient:
    """Calls civil-ai-data with service credentials and optional PII scope."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        service_key: str | None = None,
        include_pii: bool = False,
        timeout: float = _DEFAULT_TIMEOUT_SEC,
    ) -> None:
        settings = get_settings()
        self.base_url = (
            base_url or os.getenv("CIVILAI_DATA_API_BASE", "http://localhost:8000")
        ).rstrip("/")
        self.service_key = service_key or os.getenv("CIVILAI_DATA_SERVICE_KEY", "").strip()
        self.include_pii = include_pii
        self.timeout = timeout
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.service_key:
            headers["X-Data-Service-Key"] = self.service_key
        if self.include_pii:
            headers["X-Data-Scopes"] = "pii"
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        effective_timeout = self.timeout if timeout is None else timeout
        try:
            with httpx.Client(timeout=effective_timeout) as client:
                resp = client.request(method, url, headers=self._headers(), json=json)
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise RuntimeError(_upstream_error_message(exc)) from exc
                return resp.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"Data API request timed out after {effective_timeout:.0f}s "
                f"({method} {path}). For LLM invokes, increase "
                "CIVILAI_DATA_LLM_INVOKE_TIMEOUT_SEC or disable web search."
            ) from exc

    def get_section_facts(self, entity_id: str, section_id: str) -> dict[str, Any]:
        return self.request("GET", f"/v1/sections/{section_id}/facts/{entity_id}")

    def run_determinations(self, entity_id: str) -> dict[str, Any]:
        return self.request("GET", f"/v1/entities/{entity_id}/determinations")

    def resolve_parcel(
        self, *, address: str | None = None, parcel_id: str | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if address:
            body["address"] = address
        if parcel_id:
            body["parcel_id"] = parcel_id
        return self.request("POST", "/v1/entities/resolve", json=body)

    def get_site(self, entity_id: str) -> dict[str, Any]:
        return self.request("GET", f"/v1/fe/site/by-entity/{entity_id}")

    def invoke_llm(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.request(
            "POST",
            "/v1/experimental/llm/invoke",
            json=body,
            timeout=llm_invoke_timeout_sec(),
        )
