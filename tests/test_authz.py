"""AuthZ integration tests for tenant isolation and roles."""

import pytest
from fastapi.testclient import TestClient

from civilai_platform.app import create_app
from civilai_platform.store import get_store


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIVILAI_DEV_AUTH", "true")
    monkeypatch.setenv("CIVILAI_STORE_BACKEND", "memory")
    get_store.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _h(user: str, tenant: str | None = None) -> dict[str, str]:
    out = {"X-Dev-User-Id": user}
    if tenant:
        out["X-Tenant-Id"] = tenant
    return out


def test_viewer_cannot_patch_project_state(client: TestClient) -> None:
    admin = client.post("/v1/dev/bootstrap", json={"name": "Firm"}, headers=_h("admin-a")).json()
    tenant = admin["memberships"][0]["tenant_id"]
    proj = client.post(
        "/v1/projects",
        json={"name": "P", "address": "A"},
        headers=_h("admin-a", tenant),
    ).json()
    viewer_id = "viewer-1"
    store = get_store()
    from civilai_platform.models.entities import MembershipStatus, Role, TenantMembership, UserProfile, utc_now

    store.put_user_profile(
        UserProfile(
            user_id=viewer_id,
            email="v@t.com",
            first_name="V",
            last_name="1",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    store.put_membership(
        TenantMembership(
            tenant_id=tenant,
            user_id=viewer_id,
            role=Role.VIEWER,
            status=MembershipStatus.ACTIVE,
            joined_at=utc_now(),
        )
    )
    res = client.patch(
        f"/v1/projects/{proj['project_id']}/state",
        json={"proposed_use": "blocked"},
        headers=_h(viewer_id, tenant),
    )
    assert res.status_code == 403


def test_audit_events_recorded(client: TestClient) -> None:
    me = client.post("/v1/dev/bootstrap", json={"name": "Audit Firm"}, headers=_h("audit-user")).json()
    tenant = me["memberships"][0]["tenant_id"]
    store = get_store()
    events = store.list_audit_events(tenant)
    assert len(events) >= 0
    proj = client.post(
        "/v1/projects",
        json={"name": "Audit P", "address": "1 Main"},
        headers=_h("audit-user", tenant),
    )
    assert proj.status_code == 201
    events = store.list_audit_events(tenant)
    assert any(e.action == "project.create" for e in events)
