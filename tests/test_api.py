import os

import pytest
from fastapi.testclient import TestClient

from civilai_platform.app import create_app
from civilai_platform.models.api import TenantCreate
from civilai_platform.models.entities import Role
from civilai_platform.services import tenant as tenant_svc
from civilai_platform.store.memory import MemoryStore
from civilai_platform.store import get_store


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIVILAI_DEV_AUTH", "true")
    monkeypatch.setenv("CIVILAI_STORE_BACKEND", "memory")
    monkeypatch.setenv("CIVILAI_ARTIFACT_BACKEND", "memory")
    get_store.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


def _headers(user_id: str, tenant_id: str | None = None) -> dict[str, str]:
    h = {"X-Dev-User-Id": user_id}
    if tenant_id:
        h["X-Tenant-Id"] = tenant_id
    return h


def test_health(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_bootstrap_and_me(client: TestClient) -> None:
    user_id = "user-alice"
    res = client.post(
        "/v1/dev/bootstrap",
        json={"name": "ATX Civil", "email": "alice@atxcivil.com"},
        headers=_headers(user_id),
    )
    assert res.status_code == 200
    me = res.json()
    assert me["user_id"] == user_id
    assert len(me["memberships"]) == 1
    tenant_id = me["memberships"][0]["tenant_id"]

    res2 = client.get("/v1/me", headers=_headers(user_id, tenant_id))
    assert res2.status_code == 200
    assert res2.json()["email"] == "alice@atxcivil.com"


def test_patch_me(client: TestClient) -> None:
    boot = client.post(
        "/v1/dev/bootstrap",
        json={"name": "Me Test", "email": "me@test.com"},
        headers=_headers("me-user"),
    ).json()
    tenant = boot["memberships"][0]["tenant_id"]
    res = client.patch(
        "/v1/me",
        json={"first_name": "Updated", "phone": "555-0100"},
        headers=_headers("me-user", tenant),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["first_name"] == "Updated"
    assert body["phone"] == "555-0100"


def test_tenant_user_client_project_flow(client: TestClient) -> None:
    admin = "admin-1"
    boot = client.post(
        "/v1/dev/bootstrap",
        json={"name": "ATX Civil"},
        headers=_headers(admin),
    ).json()
    tenant_id = boot["memberships"][0]["tenant_id"]
    h = _headers(admin, tenant_id)

    user = client.post(
        "/v1/users",
        json={
            "email": "bob@atxcivil.com",
            "first_name": "Bob",
            "last_name": "Smith",
            "role": "Analyst",
        },
        headers=h,
    )
    assert user.status_code == 201

    cl = client.post(
        "/v1/clients",
        json={"name": "Jay Beard", "address": "123 Main", "location": "Austin, TX"},
        headers=h,
    )
    assert cl.status_code == 201
    client_id = cl.json()["client_id"]

    proj = client.post(
        "/v1/projects",
        json={
            "name": "Trappers Trail",
            "address": "123 Trappers Trail",
            "jurisdiction": "Travis County",
            "client_id": client_id,
        },
        headers=h,
    )
    assert proj.status_code == 201
    project_id = proj.json()["project_id"]
    assert proj.json()["owner_user_id"] == admin

    state = client.get(f"/v1/projects/{project_id}/state", headers=h)
    assert state.status_code == 200
    sections = state.json()["sections"]
    client_section = next(s for s in sections if s["step_key"] == "client")
    assert client_section["fields"]["CLIENT_NAME"]["value"] == "Jay Beard"

    patch = client.patch(
        f"/v1/projects/{project_id}/state",
        json={"proposed_use": "Industrial warehouse"},
        headers=h,
    )
    assert patch.status_code == 200
    assert patch.json()["proposed_use"] == "Industrial warehouse"


def test_cross_tenant_access_denied(client: TestClient) -> None:
    a = client.post("/v1/dev/bootstrap", json={"name": "Firm A"}, headers=_headers("user-a")).json()
    b = client.post("/v1/dev/bootstrap", json={"name": "Firm B"}, headers=_headers("user-b")).json()
    tenant_a = a["memberships"][0]["tenant_id"]
    tenant_b = b["memberships"][0]["tenant_id"]

    proj = client.post(
        "/v1/projects",
        json={"name": "Secret", "address": "x"},
        headers=_headers("user-a", tenant_a),
    ).json()
    project_id = proj["project_id"]

    res = client.get(
        f"/v1/projects/{project_id}",
        headers=_headers("user-b", tenant_b),
    )
    assert res.status_code == 404


def test_platform_admin_tenant_crud(client: TestClient) -> None:
    store = get_store()
    store.set_platform_admin("plat-admin", True)
    h = _headers("plat-admin")
    created = client.post(
        "/v1/admin/tenants",
        json={"name": "New Tenant"},
        headers=h,
    )
    assert created.status_code == 201
    tenant_id = created.json()["tenant_id"]
    listed = client.get("/v1/admin/tenants", headers=h)
    assert listed.status_code == 200
    assert any(t["tenant_id"] == tenant_id for t in listed.json())


def test_audit_on_project_create() -> None:
    store = get_store()
    tenant = tenant_svc.create_tenant(store, TenantCreate(name="T"))
    from civilai_platform.models.entities import MembershipStatus, TenantMembership, UserProfile, utc_now
    from civilai_platform.services import project as project_svc
    from civilai_platform.models.api import ProjectCreate

    uid = "u1"
    store.put_user_profile(
        UserProfile(
            user_id=uid,
            email="u@t.com",
            first_name="U",
            last_name="1",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    store.put_membership(
        TenantMembership(
            tenant_id=tenant.tenant_id,
            user_id=uid,
            role=Role.ADMIN,
            status=MembershipStatus.ACTIVE,
            joined_at=utc_now(),
        )
    )
    project_svc.create_project(
        store,
        tenant_id=tenant.tenant_id,
        owner_user_id=uid,
        actor_user_id=uid,
        data=ProjectCreate(name="P", address="A"),
    )
    events = store.list_audit_events(tenant.tenant_id)
    assert any(e.action == "project.create" for e in events)
