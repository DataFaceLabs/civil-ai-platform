"""Shared pytest helpers."""

from __future__ import annotations

from fastapi.testclient import TestClient

from civilai_platform.store import get_store
from tests.seed import seed_tenant_member


def bootstrap_client_user(
    client: TestClient,
    user_id: str,
    *,
    email: str | None = None,
    name: str = "Test Firm",
) -> dict:
    store = get_store()
    resolved_email = email or f"{user_id}@example.com"
    seed_tenant_member(
        store,
        user_id=user_id,
        email=resolved_email,
        tenant_name=name,
    )
    res = client.post(
        "/v1/dev/bootstrap",
        json={"name": name, "email": resolved_email},
        headers={"X-Dev-User-Id": user_id},
    )
    assert res.status_code == 200, res.text
    return res.json()
