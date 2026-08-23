"""Select the governed-data plane for a browser request.

On the customer Lambda, production is the fail-closed default; only an exact
configured Origin may select ``CIVILAI_DEV_DATA_API_BASE`` (typically ``:8001``).

The TPO develop Lambda does not use that Origin split: tofu sets
``CIVILAI_DATA_API_BASE`` to ``:8001`` and leaves the dev Origin list empty, so
this helper always returns the primary base.
"""

from __future__ import annotations

import os

from fastapi import Request


def _csv_env(name: str) -> set[str]:
    return {item.strip().rstrip("/") for item in os.getenv(name, "").split(",") if item.strip()}


def data_api_base_for_origin(origin: str | None) -> str:
    """Return the allowlisted dev data-API base, else the primary base.

    Args:
        origin: Browser ``Origin`` header, or ``None`` if absent.

    Returns:
        Trimmed data-API root URL with no trailing slash.
    """
    prod_base = os.getenv("CIVILAI_DATA_API_BASE", "http://localhost:8000").rstrip("/")
    dev_base = os.getenv("CIVILAI_DEV_DATA_API_BASE", "").strip().rstrip("/")
    normalized_origin = (origin or "").strip().rstrip("/")
    if dev_base and normalized_origin in _csv_env("CIVILAI_DEV_DATA_ORIGINS"):
        return dev_base
    return prod_base


def data_api_base_for_request(request: Request) -> str:
    """Resolve from the browser Origin header; absent/untrusted means prod."""
    return data_api_base_for_origin(request.headers.get("origin"))
