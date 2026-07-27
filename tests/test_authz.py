"""AuthZ integration tests for tenant isolation and roles."""

import pytest
from fastapi.testclient import TestClient

from civilai_platform.app import create_app
from civilai_platform.models.entities import (
    MembershipStatus,
    Role,
    TenantMembership,
    UserProfile,
    utc_now,
)
from civilai_platform.store import get_store
from tests.conftest import bootstrap_client_user


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIVILAI_DEV_AUTH", "true")
    monkeypatch.setenv("CIVILAI_STORE_BACKEND", "memory")
    get_store.cache_clear()


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


def _h(user: str, tenant: str | None = None) -> dict[str, str]:
    out = {"X-Dev-User-Id": user}
    if tenant:
        out["X-Tenant-Id"] = tenant
    return out


def test_viewer_cannot_patch_project_state(client: TestClient) -> None:
    admin = bootstrap_client_user(client, "admin-a", name="Firm")
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


def _add_member(tenant: str, user_id: str, role: Role) -> None:
    store = get_store()
    store.put_user_profile(
        UserProfile(
            user_id=user_id,
            email=f"{user_id}@t.com",
            first_name="M",
            last_name="1",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    store.put_membership(
        TenantMembership(
            tenant_id=tenant,
            user_id=user_id,
            role=role,
            status=MembershipStatus.ACTIVE,
            joined_at=utc_now(),
        )
    )


def test_non_admin_member_can_read_user_directory(client: TestClient) -> None:
    """Regression: GET /v1/users was Admin-gated, which locked non-Admins out of the app.

    The FE hydrates this directory during session bootstrap (and uses it for @mentions and
    assignee labels), so a 403 here failed login before any session existed -- the user saw a
    bare "Insufficient role" screen and could never reach the product.
    """
    admin = bootstrap_client_user(client, "dir-admin", name="Dir Firm")
    tenant = admin["memberships"][0]["tenant_id"]
    _add_member(tenant, "dir-analyst", Role.ANALYST)
    _add_member(tenant, "dir-viewer", Role.VIEWER)

    for member in ("dir-analyst", "dir-viewer"):
        res = client.get("/v1/users", headers=_h(member, tenant))
        assert res.status_code == 200, f"{member} could not read the directory"
        assert {u["user_id"] for u in res.json()} >= {"dir-admin", member}
        # A one-time invite password must never be readable by a non-Admin.
        assert all(u["temporary_password"] is None for u in res.json())


def test_non_admin_member_cannot_write_users(client: TestClient) -> None:
    """Read was relaxed to Viewer; every mutation must still require Admin."""
    admin = bootstrap_client_user(client, "w-admin", name="Write Firm")
    tenant = admin["memberships"][0]["tenant_id"]
    _add_member(tenant, "w-analyst", Role.ANALYST)

    created = client.post(
        "/v1/users",
        json={"email": "new@t.com", "first_name": "N", "last_name": "U", "invite": False},
        headers=_h("w-admin", tenant),
    )
    assert created.status_code == 201

    assert (
        client.post(
            "/v1/users",
            json={"email": "x@t.com", "first_name": "X", "last_name": "U", "invite": False},
            headers=_h("w-analyst", tenant),
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/v1/users/{created.json()['user_id']}",
            json={"role": "Admin"},
            headers=_h("w-analyst", tenant),
        ).status_code
        == 403
    )


def test_non_member_still_cannot_read_user_directory(client: TestClient) -> None:
    """Relaxing the role must not relax tenant isolation."""
    admin = bootstrap_client_user(client, "iso-admin", name="Iso Firm")
    tenant = admin["memberships"][0]["tenant_id"]
    outsider = bootstrap_client_user(client, "iso-outsider", name="Other Firm")
    assert outsider["memberships"][0]["tenant_id"] != tenant

    assert client.get("/v1/users", headers=_h("iso-outsider", tenant)).status_code == 403


def test_audit_events_recorded(client: TestClient) -> None:
    me = bootstrap_client_user(client, "audit-user", name="Audit Firm")
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
