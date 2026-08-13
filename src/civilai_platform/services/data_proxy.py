"""Platform proxy to civil-ai-data governed APIs."""

from __future__ import annotations

import os
from typing import Any

import httpx

from civilai_platform.settings import get_settings

_DEFAULT_TIMEOUT_SEC = 30.0
# Address/parcel site lookups hit live geocoders + CAD ArcGIS; Williams Dr
# envelope ambiguity routinely exceeds the default 30s proxy budget.
_DEFAULT_SITE_PASSTHROUGH_TIMEOUT_SEC = 90.0
# Section facts via Athena (local ``make serve-athena`` or remote lake) often
# take 15–60s; civil-ai-data polls Athena for up to ~60s before giving up.
_DEFAULT_SECTION_PASSTHROUGH_TIMEOUT_SEC = 90.0
_DEFAULT_LLM_INVOKE_TIMEOUT_SEC = 180.0
_DEFAULT_DRAFT_LLM_INVOKE_TIMEOUT_SEC = 660.0

_SITE_PASSTHROUGH_SUFFIXES = (
    "fe/site/resolve-address",
    "fe/site/by-address",
    "fe/site/by-parcel",
    "fe/site/by-entity",
)


def _read_timeout_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(float(raw), 1.0)
    except ValueError:
        return default


def _is_section_facts_path(data_path: str) -> bool:
    """True for ``sections/{id}/facts/{entity}`` (and trailing path variants)."""
    parts = [p for p in data_path.lstrip("/").split("/") if p]
    return (
        len(parts) >= 4
        and parts[0] == "sections"
        and parts[2] == "facts"
    )


def passthrough_timeout_sec(data_path: str) -> float:
    """Timeout for status-preserving passthrough calls.

    FE site address/parcel resolution hits live geocoders + CAD ArcGIS and can
    exceed the default 30s budget (override with
    CIVILAI_DATA_SITE_PASSTHROUGH_TIMEOUT_SEC). Section fact lookups against
    Athena need a similar budget (override with
    CIVILAI_DATA_SECTION_PASSTHROUGH_TIMEOUT_SEC). Everything else uses
    CIVILAI_DATA_PASSTHROUGH_TIMEOUT_SEC / 30s.
    """
    normalized = data_path.lstrip("/")
    if any(
        normalized == suffix or normalized.startswith(f"{suffix}/")
        for suffix in _SITE_PASSTHROUGH_SUFFIXES
    ):
        return _read_timeout_env(
            "CIVILAI_DATA_SITE_PASSTHROUGH_TIMEOUT_SEC",
            _DEFAULT_SITE_PASSTHROUGH_TIMEOUT_SEC,
        )
    if _is_section_facts_path(normalized):
        return _read_timeout_env(
            "CIVILAI_DATA_SECTION_PASSTHROUGH_TIMEOUT_SEC",
            _DEFAULT_SECTION_PASSTHROUGH_TIMEOUT_SEC,
        )
    return _read_timeout_env(
        "CIVILAI_DATA_PASSTHROUGH_TIMEOUT_SEC",
        _DEFAULT_TIMEOUT_SEC,
    )


def llm_invoke_timeout_sec(*, step_key: str | None = None) -> float:
    """Match civil-ai-data OpenAI client budget (120s) plus web-search headroom."""
    if step_key == "draft":
        return _read_timeout_env(
            "CIVILAI_DATA_LLM_DRAFT_INVOKE_TIMEOUT_SEC",
            _DEFAULT_DRAFT_LLM_INVOKE_TIMEOUT_SEC,
        )
    return _read_timeout_env(
        "CIVILAI_DATA_LLM_INVOKE_TIMEOUT_SEC",
        _DEFAULT_LLM_INVOKE_TIMEOUT_SEC,
    )


def llm_api_base(facts_base: str | None = None) -> str:
    """Optional split base URL for experimental LLM invokes (dev: local API, facts stay on EC2)."""
    override = os.getenv("CIVILAI_DATA_LLM_API_BASE", "").strip()
    if override:
        return override.rstrip("/")
    return (facts_base or os.getenv("CIVILAI_DATA_API_BASE", "http://localhost:8000")).rstrip("/")


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
        base_url: str | None = None,
    ) -> Any:
        url = f"{(base_url or self.base_url).rstrip('/')}{path}"
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
            hint = (
                "CIVILAI_DATA_LLM_DRAFT_INVOKE_TIMEOUT_SEC"
                if path.endswith("/v1/experimental/llm/invoke")
                and effective_timeout >= _DEFAULT_DRAFT_LLM_INVOKE_TIMEOUT_SEC
                else "CIVILAI_DATA_LLM_INVOKE_TIMEOUT_SEC"
            )
            raise RuntimeError(
                f"Data API request timed out after {effective_timeout:.0f}s "
                f"({method} {path}). For LLM invokes, increase {hint} "
                "or disable web search."
            ) from exc

    def passthrough(
        self,
        method: str,
        data_path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Forward a read request to the data API and return the raw response.

        Unlike ``request``, this does NOT raise on non-2xx -- the caller mirrors the
        upstream status/body verbatim so the FE's status-based logic (409 ambiguous
        address, 404/503 -> skip section) keeps working through the proxy.

        Raises ``httpx.TimeoutException`` / ``httpx.TransportError`` so the route
        can map them to a clean 504/502 instead of an unhandled ASGI 500.
        """
        url = f"{self.base_url}/v1/{data_path.lstrip('/')}"
        effective_timeout = (
            passthrough_timeout_sec(data_path) if timeout is None else timeout
        )
        with httpx.Client(timeout=effective_timeout) as client:
            return client.request(
                method,
                url,
                headers=self._headers(),
                json=json,
                params=params,
            )

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

    def resolve_site_address(self, address: str) -> dict[str, Any]:
        """FE staged resolve — returns ``entity_id`` for a unique situs match."""
        return self.request(
            "POST",
            "/v1/fe/site/resolve-address",
            json={"address": address},
            timeout=passthrough_timeout_sec("fe/site/resolve-address"),
        )

    def get_site(self, entity_id: str) -> dict[str, Any]:
        return self.request("GET", f"/v1/fe/site/by-entity/{entity_id}")

    def invoke_llm(self, body: dict[str, Any], *, step_key: str | None = None) -> dict[str, Any]:
        return self.request(
            "POST",
            "/v1/experimental/llm/invoke",
            json=body,
            timeout=llm_invoke_timeout_sec(step_key=step_key),
            base_url=llm_api_base(self.base_url),
        )
