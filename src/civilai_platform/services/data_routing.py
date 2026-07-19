"""Select the governed-data plane for a browser request.

The UAT API is shared by the production and develop frontends. Production is
the fail-closed default; only an exact, configured browser Origin may select
the slower dev data plane.
"""

from __future__ import annotations

import os

from fastapi import Request


def _csv_env(name: str) -> set[str]:
    return {item.strip().rstrip("/") for item in os.getenv(name, "").split(",") if item.strip()}


def data_api_base_for_origin(origin: str | None) -> str:
    """Return dev base for an allowlisted Origin; otherwise return prod."""
    prod_base = os.getenv("CIVILAI_DATA_API_BASE", "http://localhost:8000").rstrip("/")
    dev_base = os.getenv("CIVILAI_DEV_DATA_API_BASE", "").strip().rstrip("/")
    normalized_origin = (origin or "").strip().rstrip("/")
    if dev_base and normalized_origin in _csv_env("CIVILAI_DEV_DATA_ORIGINS"):
        return dev_base
    return prod_base


def data_api_base_for_request(request: Request) -> str:
    """Resolve from the browser Origin header; absent/untrusted means prod."""
    return data_api_base_for_origin(request.headers.get("origin"))
