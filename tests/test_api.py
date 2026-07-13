import os

import pytest
from fastapi.testclient import TestClient

from civilai_platform.app import create_app
from civilai_platform.models.api import AdminTenantCreate, TenantCreate, UserCreate
from civilai_platform.models.entities import Role
from civilai_platform.services import platform_tenant as platform_tenant_svc
from civilai_platform.services import tenant as tenant_svc
from civilai_platform.services import user as user_svc
from civilai_platform.store.memory import MemoryStore
from civilai_platform.store import get_store
from tests.conftest import bootstrap_client_user as _bootstrap


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIVILAI_DEV_AUTH", "true")
    monkeypatch.setenv("CIVILAI_STORE_BACKEND", "memory")
    monkeypatch.setenv("CIVILAI_ARTIFACT_BACKEND", "memory")
    get_store.cache_clear()


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


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
    me = _bootstrap(client, user_id, email="alice@atxcivil.com", name="ATX Civil")
    assert me["user_id"] == user_id
    assert len(me["memberships"]) == 1
    tenant_id = me["memberships"][0]["tenant_id"]

    res2 = client.get("/v1/me", headers=_headers(user_id, tenant_id))
    assert res2.status_code == 200
    assert res2.json()["email"] == "alice@atxcivil.com"


def test_dev_bootstrap_rejects_without_membership(client: TestClient) -> None:
    res = client.post(
        "/v1/dev/bootstrap",
        json={"name": "Nobody", "email": "nobody@example.com"},
        headers=_headers("nobody-user"),
    )
    assert res.status_code == 403


def test_patch_me(client: TestClient) -> None:
    boot = _bootstrap(client, "me-user", email="me@test.com", name="Me Test")
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
    boot = _bootstrap(client, admin, name="ATX Civil")
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
    assert client_section["fields"]["CLIENT_COMPANY"]["value"] == "Jay Beard"

    patch = client.patch(
        f"/v1/projects/{project_id}/state",
        json={"proposed_use": "Industrial warehouse"},
        headers=h,
    )
    assert patch.status_code == 200
    assert patch.json()["proposed_use"] == "Industrial warehouse"


def test_project_state_round_trips_field_provenance_and_site_payload(client: TestClient) -> None:
    admin = "prov-admin"
    boot = _bootstrap(client, admin, name="Provenance Firm")
    tenant_id = boot["memberships"][0]["tenant_id"]
    h = _headers(admin, tenant_id)

    project_id = client.post(
        "/v1/projects",
        json={"name": "Trappers Trail", "address": "20401 Trappers Trail, Manor, TX"},
        headers=h,
    ).json()["project_id"]

    site_payload = {
        "parcel": [
            {
                "code": "PROPERTY_ADDRESS",
                "value": "20401 Trappers Trail, Manor, TX",
                "data_status": "complete",
                "provenance": [
                    {
                        "source": "County Appraisal District parcel record",
                        "source_id": "tcad",
                        "citation": "https://traviscad.org/propertysearch?query=870361",
                    }
                ],
                "source_links": [
                    {
                        "name": "County Appraisal District parcel record",
                        "description": "Normalized situs address from unified parcel layer.",
                        "href": "https://traviscad.org/propertysearch?query=870361",
                        "source_type": "county_appraisal",
                        "source_id": "county_cad",
                    }
                ],
            }
        ]
    }
    patch_body = {
        "sections": [
            {
                "id": "parcel-section",
                "title": "Parcel",
                "step_key": "parcel",
                "fields": {
                    "PROPERTY_ADDRESS": {
                        "value": "20401 Trappers Trail, Manor, TX",
                        "status": "review",
                        "data_status": "complete",
                        "system_populated": True,
                        "provenance": site_payload["parcel"][0]["provenance"],
                        "source_links": site_payload["parcel"][0]["source_links"],
                    }
                },
            }
        ],
        "site_payload": site_payload,
    }

    patch = client.patch(f"/v1/projects/{project_id}/state", json=patch_body, headers=h)
    assert patch.status_code == 200
    body = patch.json()
    assert body["site_payload"] == site_payload

    address_field = body["sections"][0]["fields"]["PROPERTY_ADDRESS"]
    assert address_field["provenance"][0]["source_id"] == "tcad"
    assert address_field["source_links"][0]["source_id"] == "county_cad"

    reloaded = client.get(f"/v1/projects/{project_id}/state", headers=h)
    assert reloaded.status_code == 200
    reloaded_body = reloaded.json()
    assert reloaded_body["site_payload"] == site_payload
    reloaded_address = reloaded_body["sections"][0]["fields"]["PROPERTY_ADDRESS"]
    assert reloaded_address["provenance"][0]["citation"].startswith("https://traviscad.org")
    assert reloaded_address["source_links"][0]["href"].startswith("https://traviscad.org")


def test_project_state_accepts_string_code_semantic_confidence(client: TestClient) -> None:
    admin = "semantic-admin"
    boot = _bootstrap(client, admin, name="Semantic Firm")
    tenant_id = boot["memberships"][0]["tenant_id"]
    h = _headers(admin, tenant_id)

    project_id = client.post(
        "/v1/projects",
        json={"name": "ETJ Site", "address": "209 Norwood West, Austin TX"},
        headers=h,
    ).json()["project_id"]

    patch_body = {
        "site_context": {
            "IN_ETJ": {
                "value": "Yes",
                "status": "review",
                "code_semantics": [
                    {
                        "code": "IN_ETJ",
                        "ui_label": "Extraterritorial jurisdiction",
                        "ui_detail": "Bootstrap vocabulary label",
                        "confidence": "bootstrap",
                    }
                ],
            }
        }
    }
    patch = client.patch(f"/v1/projects/{project_id}/state", json=patch_body, headers=h)
    assert patch.status_code == 200
    assert patch.json()["site_context"]["IN_ETJ"]["code_semantics"][0]["confidence"] == "bootstrap"


def test_project_state_patch_keeps_nested_models(client: TestClient) -> None:
    from civilai_platform.models.entities import ClientContact, FieldValue, Section
    from civilai_platform.services import project as project_svc
    from civilai_platform.store import get_store

    admin = "nested-models-admin"
    boot = _bootstrap(client, admin, name="Nested Models Firm")
    tenant_id = boot["memberships"][0]["tenant_id"]
    h = _headers(admin, tenant_id)

    project_id = client.post(
        "/v1/projects",
        json={"name": "Parcel Site", "address": "13903 FM 812, Austin TX"},
        headers=h,
    ).json()["project_id"]

    patch_body = {
        "sections": [
            {
                "id": "parcel-section",
                "title": "Parcel",
                "step_key": "parcel",
                "fields": {
                    "PROPERTY_ADDRESS": {
                        "value": "13903 FM 812, Austin TX",
                        "status": "review",
                    }
                },
            }
        ],
        "site_context": {
            "COUNTY": {"value": "Travis", "status": "review"},
        },
        "client_contacts": [
            {
                "id": "contact-1",
                "first_name": "Jane",
                "last_name": "Doe",
                "email": "jane@example.com",
                "phone": "512-555-0100",
            }
        ],
    }
    patch = client.patch(f"/v1/projects/{project_id}/state", json=patch_body, headers=h)
    assert patch.status_code == 200

    state = get_store().get_project_state(tenant_id, project_id)
    assert state is not None
    assert all(isinstance(section, Section) for section in state.sections)
    assert all(isinstance(value, FieldValue) for value in (state.site_context or {}).values())
    assert all(isinstance(contact, ClientContact) for contact in state.client_contacts)

    # Exercise the same path the API uses when returning patched state.
    response = project_svc.get_project_state(get_store(), tenant_id, project_id)
    assert response.sections[0].fields["PROPERTY_ADDRESS"].value == "13903 FM 812, Austin TX"


def test_cross_tenant_access_denied(client: TestClient) -> None:
    a = _bootstrap(client, "user-a", name="Firm A")
    b = _bootstrap(client, "user-b", name="Firm B")
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
    platform_tenant_svc.ensure_platform_admin_membership(store, "plat-admin")
    h = _headers("plat-admin")
    created = client.post(
        "/v1/admin/tenants",
        json={
            "name": "New Tenant",
            "admin_email": "admin@newtenant.com",
            "admin_first_name": "New",
            "admin_last_name": "Admin",
        },
        headers=h,
    )
    assert created.status_code == 201
    tenant_id = created.json()["tenant"]["tenant_id"]
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


def test_public_tenant_by_slug(client: TestClient) -> None:
    boot = _bootstrap(client, "slug-user", name="ATX Civil Engineering")
    slug = boot["memberships"][0].get("tenant_slug") or "atx-civil-engineering"
    res = client.get(f"/v1/public/tenants/{slug}")
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "ATX Civil Engineering"
    assert body["url_slug"] == slug


def test_single_tenant_membership_enforced(client: TestClient) -> None:
    a = _bootstrap(client, "user-a2", name="Firm A")
    b = _bootstrap(client, "user-b2", name="Firm B")
    tenant_a = a["memberships"][0]["tenant_id"]
    tenant_b = b["memberships"][0]["tenant_id"]
    h_a = _headers("user-a2", tenant_a)
    created = client.post(
        "/v1/users",
        json={
            "email": "shared@test.com",
            "first_name": "Shared",
            "last_name": "User",
            "role": "Analyst",
        },
        headers=h_a,
    )
    assert created.status_code == 201
    h_b = _headers("user-b2", tenant_b)
    conflict = client.post(
        "/v1/users",
        json={
            "email": "shared@test.com",
            "first_name": "Shared",
            "last_name": "User",
            "role": "Analyst",
        },
        headers=h_b,
    )
    assert conflict.status_code == 409


def test_tenant_llm_config(client: TestClient) -> None:
    boot = _bootstrap(client, "llm-admin", name="LLM Firm")
    tenant_id = boot["memberships"][0]["tenant_id"]
    h = _headers("llm-admin", tenant_id)
    denied = client.get("/v1/tenant/llm-config", headers=h)
    assert denied.status_code == 403

    store = get_store()
    store.set_platform_admin("llm-admin", True)
    platform_tenant_svc.ensure_platform_admin_membership(store, "llm-admin")
    res = client.get("/v1/tenant/llm-config", headers=h)
    assert res.status_code == 200
    assert res.json()["config"]["modelPreset"] == "haiku"


def test_platform_admin_llm_baseline(client: TestClient) -> None:
    store = get_store()
    store.set_platform_admin("baseline-admin", True)
    platform_membership = platform_tenant_svc.ensure_platform_admin_membership(
        store, "baseline-admin"
    )
    h = _headers("baseline-admin")
    res = client.get("/v1/admin/llm-baseline", headers=h)
    assert res.status_code == 200
    assert res.json()["config"]["version"] == 1

    tenant_before = client.get(
        "/v1/tenant/llm-config",
        headers=h | {"X-Tenant-Id": platform_membership.tenant_id},
    )
    assert tenant_before.status_code == 200
    assert tenant_before.json()["config"]["modelPreset"] == "haiku"

    baseline_cfg = res.json()["config"]
    baseline_cfg["modelPreset"] = "opus"
    updated = client.patch(
        "/v1/admin/llm-baseline",
        json={"config": baseline_cfg},
        headers=h,
    )
    assert updated.status_code == 200
    assert updated.json()["config"]["modelPreset"] == "opus"

    tenant_after = client.get(
        "/v1/tenant/llm-config",
        headers=h | {"X-Tenant-Id": platform_membership.tenant_id},
    )
    assert tenant_after.status_code == 200
    assert tenant_after.json()["config"]["modelPreset"] == "opus"


def test_tenant_llm_invoke_uses_proxy(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    boot = _bootstrap(client, "invoke-user", name="Invoke Firm")
    tenant_id = boot["memberships"][0]["tenant_id"]
    h = _headers("invoke-user", tenant_id)
    store = get_store()
    store.set_platform_admin("invoke-user", True)
    platform_tenant_svc.ensure_platform_admin_membership(store, "invoke-user")

    def _fake_invoke(self, body, *, step_key=None, **_kwargs):  # noqa: ANN001
        assert body["user_prompt"]
        assert body["system_prompt"]
        return {
            "text": "Draft paragraph.",
            "model_id": body["model_id"],
            "latency_ms": 12,
            "guardrail_warnings": [],
            "parse_errors": [],
            "web_search_trace": [],
        }

    monkeypatch.setattr(
        "civilai_platform.services.data_proxy.DataProxyClient.invoke_llm",
        _fake_invoke,
    )
    res = client.post(
        "/v1/tenant/llm/invoke",
        json={
            "step_key": "zoning",
            "user_prompt": "Review zoning fields.",
            "field_context": {"ZONING_REGS": "R-1"},
            "search_context_hint": "city code",
        },
        headers=h,
    )
    assert res.status_code == 200
    assert "Draft" in res.json()["text"]


def test_tenant_llm_invoke_draft_mode_forces_text_and_higher_token_cap(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    boot = _bootstrap(client, "draft-invoke-user", name="Draft Invoke Firm")
    tenant_id = boot["memberships"][0]["tenant_id"]
    h = _headers("draft-invoke-user", tenant_id)
    store = get_store()
    store.set_platform_admin("draft-invoke-user", True)
    platform_tenant_svc.ensure_platform_admin_membership(store, "draft-invoke-user")

    captured: dict[str, object] = {}

    def _fake_invoke(self, body, *, step_key=None, **_kwargs):  # noqa: ANN001
        captured.update(body)
        return {
            "text": "## Parcel\n\nMerged draft body.",
            "model_id": body["model_id"],
            "latency_ms": 15,
            "guardrail_warnings": [],
            "parse_errors": [],
            "web_search_trace": [],
        }

    monkeypatch.setattr(
        "civilai_platform.services.data_proxy.DataProxyClient.invoke_llm",
        _fake_invoke,
    )
    res = client.post(
        "/v1/tenant/llm/invoke",
        json={
            "step_key": "draft",
            "user_prompt": "Polish merged sections.",
            "field_context": {"PROPERTY_ADDRESS": "123 Main St"},
        },
        headers=h,
    )
    assert res.status_code == 200
    assert captured["response_mode"] == "text"
    assert captured["guardrails"]["max_output_tokens"] == 4096
    assert captured["web_search"]["enabled"] is False


def test_tenant_llm_invoke_draft_disables_web_search_even_when_global_enabled(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    boot = _bootstrap(client, "draft-search-user", name="Draft Search Firm")
    tenant_id = boot["memberships"][0]["tenant_id"]
    h = _headers("draft-search-user", tenant_id)
    store = get_store()
    store.set_platform_admin("draft-search-user", True)
    platform_tenant_svc.ensure_platform_admin_membership(store, "draft-search-user")

    cfg = client.get("/v1/tenant/llm-config", headers=h).json()["config"]
    cfg["webSearch"]["enabled"] = True
    cfg["sections"]["draft"]["webSearchEnabled"] = True
    client.patch("/v1/tenant/llm-config", json={"config": cfg}, headers=h)

    captured: dict[str, object] = {}

    def _fake_invoke(self, body, *, step_key=None):  # noqa: ANN001
        captured.update(body)
        return {
            "text": "## Parcel\n\nMerged draft body.",
            "model_id": body["model_id"],
            "latency_ms": 15,
            "guardrail_warnings": [],
            "parse_errors": [],
            "web_search_trace": [],
        }

    monkeypatch.setattr(
        "civilai_platform.services.data_proxy.DataProxyClient.invoke_llm",
        _fake_invoke,
    )
    res = client.post(
        "/v1/tenant/llm/invoke",
        json={
            "step_key": "draft",
            "user_prompt": "Polish merged sections.",
            "field_context": {"PROPERTY_ADDRESS": "123 Main St"},
            "web_search_enabled": True,
        },
        headers=h,
    )
    assert res.status_code == 200
    assert captured["web_search"]["enabled"] is False


def test_tenant_llm_invoke_utilities_enables_web_search_by_default(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    boot = _bootstrap(client, "utilities-search-user", name="Utilities Search Firm")
    tenant_id = boot["memberships"][0]["tenant_id"]
    h = _headers("utilities-search-user", tenant_id)
    store = get_store()
    store.set_platform_admin("utilities-search-user", True)
    platform_tenant_svc.ensure_platform_admin_membership(store, "utilities-search-user")

    captured: dict[str, object] = {}

    def _fake_invoke(self, body, *, step_key=None, **_kwargs):  # noqa: ANN001
        captured.update(body)
        return {
            "text": "Utility narrative.",
            "model_id": body["model_id"],
            "latency_ms": 11,
            "guardrail_warnings": [],
            "parse_errors": [],
            "web_search_trace": [],
        }

    monkeypatch.setattr(
        "civilai_platform.services.data_proxy.DataProxyClient.invoke_llm",
        _fake_invoke,
    )
    # No web_search_enabled override: exercises the section baseline default.
    res = client.post(
        "/v1/tenant/llm/invoke",
        json={
            "step_key": "utilities",
            "user_prompt": "Review utility boundary fields.",
            "field_context": {"WATER_SERVICE": "City of Austin"},
        },
        headers=h,
    )
    assert res.status_code == 200
    assert captured["web_search"]["enabled"] is True
    # Baseline uses advanced search depth so Tavily returns richer page content.
    assert captured["web_search"]["search_depth"] == "advanced"


def test_tenant_llm_invoke_chat_mode_forces_text_and_disables_search(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    boot = _bootstrap(client, "chat-invoke-user", name="Chat Invoke Firm")
    tenant_id = boot["memberships"][0]["tenant_id"]
    h = _headers("chat-invoke-user", tenant_id)
    store = get_store()
    store.set_platform_admin("chat-invoke-user", True)
    platform_tenant_svc.ensure_platform_admin_membership(store, "chat-invoke-user")

    captured: dict[str, object] = {}

    def _fake_invoke(self, body, *, step_key=None, **_kwargs):  # noqa: ANN001
        captured.update(body)
        return {
            "text": "Plain chat answer.",
            "model_id": body["model_id"],
            "latency_ms": 8,
            "guardrail_warnings": [],
            "parse_errors": [],
            "web_search_trace": [],
        }

    monkeypatch.setattr(
        "civilai_platform.services.data_proxy.DataProxyClient.invoke_llm",
        _fake_invoke,
    )
    res = client.post(
        "/v1/tenant/llm/invoke",
        json={
            "step_key": "zoning",
            "user_prompt": "Quick zoning question.",
            "field_context": {"ZONING_REGS": "LI"},
            "invoke_mode": "chat",
        },
        headers=h,
    )
    assert res.status_code == 200
    assert captured["response_mode"] == "text"
    assert captured["web_search"]["enabled"] is False
    assert captured["guardrails"]["required_disclaimers"] == []


def test_tenant_llm_invoke_maps_openai_gpt55_preset(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    boot = _bootstrap(client, "gpt55-user", name="GPT55 Firm")
    tenant_id = boot["memberships"][0]["tenant_id"]
    h = _headers("gpt55-user", tenant_id)
    store = get_store()
    store.set_platform_admin("gpt55-user", True)
    platform_tenant_svc.ensure_platform_admin_membership(store, "gpt55-user")

    cfg = client.get("/v1/tenant/llm-config", headers=h).json()["config"]
    cfg["modelPreset"] = "gpt55"
    client.patch("/v1/tenant/llm-config", json={"config": cfg}, headers=h)

    captured: dict[str, object] = {}

    def _fake_invoke(self, body, *, step_key=None, **_kwargs):  # noqa: ANN001
        captured.update(body)
        return {
            "text": "Draft paragraph.",
            "model_id": body["model_id"],
            "latency_ms": 12,
            "guardrail_warnings": [],
            "parse_errors": [],
            "web_search_trace": [],
        }

    monkeypatch.setattr(
        "civilai_platform.services.data_proxy.DataProxyClient.invoke_llm",
        _fake_invoke,
    )
    res = client.post(
        "/v1/tenant/llm/invoke",
        json={
            "step_key": "zoning",
            "user_prompt": "Review zoning fields.",
            "field_context": {"ZONING_REGS": "R-1"},
        },
        headers=h,
    )
    assert res.status_code == 200
    assert captured["model_id"] == "gpt-5.5"


def test_tenant_llm_invoke_uses_section_model_override(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    boot = _bootstrap(client, "section-model-user", name="Section Model Firm")
    tenant_id = boot["memberships"][0]["tenant_id"]
    h = _headers("section-model-user", tenant_id)
    store = get_store()
    store.set_platform_admin("section-model-user", True)
    platform_tenant_svc.ensure_platform_admin_membership(store, "section-model-user")

    cfg = client.get("/v1/tenant/llm-config", headers=h).json()["config"]
    cfg["modelPreset"] = "haiku"
    cfg["sections"]["zoning"]["modelPreset"] = "opus"
    client.patch("/v1/tenant/llm-config", json={"config": cfg}, headers=h)

    captured: dict[str, object] = {}

    def _fake_invoke(self, body, *, step_key=None, **_kwargs):  # noqa: ANN001
        captured.update(body)
        return {
            "text": "Draft paragraph.",
            "model_id": body["model_id"],
            "latency_ms": 12,
            "guardrail_warnings": [],
            "parse_errors": [],
            "web_search_trace": [],
        }

    monkeypatch.setattr(
        "civilai_platform.services.data_proxy.DataProxyClient.invoke_llm",
        _fake_invoke,
    )
    res = client.post(
        "/v1/tenant/llm/invoke",
        json={
            "step_key": "zoning",
            "user_prompt": "Review zoning fields.",
            "field_context": {"ZONING_REGS": "R-1"},
        },
        headers=h,
    )
    assert res.status_code == 200
    assert captured["model_id"] == "us.anthropic.claude-opus-4-6-20260201-v1:0"


def test_tenant_llm_config_isolated(client: TestClient) -> None:
    a = _bootstrap(client, "llm-a", name="LLM A")
    b = _bootstrap(client, "llm-b", name="LLM B")
    tenant_a = a["memberships"][0]["tenant_id"]
    tenant_b = b["memberships"][0]["tenant_id"]
    store = get_store()
    store.set_platform_admin("llm-a", True)
    store.set_platform_admin("llm-b", True)
    platform_tenant_svc.ensure_platform_admin_membership(store, "llm-a")
    platform_tenant_svc.ensure_platform_admin_membership(store, "llm-b")
    h_a = _headers("llm-a", tenant_a)
    h_b = _headers("llm-b", tenant_b)

    cfg_a = client.get("/v1/tenant/llm-config", headers=h_a).json()["config"]
    cfg_a["modelPreset"] = "opus"
    client.patch("/v1/tenant/llm-config", json={"config": cfg_a}, headers=h_a)

    cfg_b = client.get("/v1/tenant/llm-config", headers=h_b).json()["config"]
    assert cfg_b["modelPreset"] == "haiku"


def test_create_tenant_copies_llm_baseline(store: MemoryStore) -> None:
    from civilai_platform.models.api import TenantCreate
    from civilai_platform.services import llm_config as llm_config_svc

    tenant = tenant_svc.create_tenant(store, TenantCreate(name="Baseline Copy Firm"))
    baseline = llm_config_svc.ensure_llm_baseline(store)
    tenant_cfg = store.get_tenant_llm_config(tenant.tenant_id)
    assert tenant_cfg is not None
    assert tenant_cfg.baseline_version_at_copy == baseline.version
    assert tenant_cfg.config["modelPreset"] == baseline.config["modelPreset"]


def test_restore_tenant_llm_baseline(client: TestClient) -> None:
    boot = _bootstrap(client, "restore-llm", name="Restore Firm")
    tenant_id = boot["memberships"][0]["tenant_id"]
    store = get_store()
    store.set_platform_admin("restore-llm", True)
    platform_tenant_svc.ensure_platform_admin_membership(store, "restore-llm")
    h = _headers("restore-llm", tenant_id)

    cfg = client.get("/v1/tenant/llm-config", headers=h).json()["config"]
    cfg["modelPreset"] = "opus"
    client.patch("/v1/tenant/llm-config", json={"config": cfg}, headers=h)
    assert client.get("/v1/tenant/llm-config", headers=h).json()["config"]["modelPreset"] == "opus"

    baseline = client.get("/v1/admin/llm-baseline", headers=_headers("restore-llm")).json()
    restored = client.post("/v1/tenant/llm-config/restore-baseline", headers=h)
    assert restored.status_code == 200
    body = restored.json()
    assert body["config"]["modelPreset"] == baseline["config"]["modelPreset"]
    assert body["baseline_version_at_copy"] == baseline["version"]


def test_suspended_tenant_blocks_public_login_and_api(client: TestClient) -> None:
    boot = _bootstrap(client, "suspend-user", email="suspend@firm.com", name="Suspend Firm")
    tenant_id = boot["memberships"][0]["tenant_id"]
    slug = boot["memberships"][0]["tenant_slug"]
    store = get_store()
    store.set_platform_admin("platform-admin", True)
    platform_tenant_svc.ensure_platform_admin_membership(store, "platform-admin")
    admin_h = _headers("platform-admin")

    client.patch(
        f"/v1/admin/tenants/{tenant_id}",
        json={"status": "suspended"},
        headers=admin_h,
    )
    assert client.get(f"/v1/public/tenants/{slug}").status_code == 404

    member_h = _headers("suspend-user", tenant_id)
    assert client.get("/v1/tenant", headers=member_h).status_code == 403

    assert client.get("/v1/tenant", headers=admin_h | {"X-Tenant-Id": tenant_id}).status_code == 200


def test_platform_admin_bootstrap_allows_tenant_slug_login(client: TestClient) -> None:
    from civilai_platform.models.entities import UserProfile, utc_now

    acme = _bootstrap(client, "acme-member", email="member@acme.com", name="Acme Civil")
    acme_slug = acme["memberships"][0]["tenant_slug"]
    store = get_store()
    store.set_platform_admin("platform-only-admin", True)
    store.put_user_profile(
        UserProfile(
            user_id="platform-only-admin",
            email="platform@civil.ai",
            first_name="Platform",
            last_name="Admin",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    platform_tenant_svc.ensure_platform_admin_membership(store, "platform-only-admin")
    res = client.post(
        "/v1/dev/bootstrap",
        json={"email": "platform@civil.ai", "tenant_slug": acme_slug},
        headers=_headers("dev-platform-civil-ai"),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["is_platform_admin"] is True
    assert not any(m["tenant_slug"] == acme_slug for m in body["memberships"])
    assert any(
        m["tenant_slug"] == platform_tenant_svc.PLATFORM_TENANT_SLUG for m in body["memberships"]
    )
    assert client.get(
        "/v1/tenant",
        headers=_headers("platform-only-admin", acme["memberships"][0]["tenant_id"]),
    ).status_code == 200


def test_platform_admin_acting_actor_on_project_create(client: TestClient) -> None:
    from civilai_platform.auth.actor import PLATFORM_ACTING_ACTOR_ID
    from civilai_platform.models.entities import UserProfile, utc_now

    acme = _bootstrap(client, "acme-member", email="member@acme.com", name="Acme Civil")
    acme_tenant_id = acme["memberships"][0]["tenant_id"]
    store = get_store()
    store.set_platform_admin("platform-only-admin", True)
    store.put_user_profile(
        UserProfile(
            user_id="platform-only-admin",
            email="platform@civil.ai",
            first_name="Platform",
            last_name="Admin",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    platform_tenant_svc.ensure_platform_admin_membership(store, "platform-only-admin")
    admin_h = _headers("platform-only-admin", acme_tenant_id)
    res = client.post(
        "/v1/projects",
        json={"name": "Acting Test", "address": "1 Main St", "jurisdiction": "Austin, TX"},
        headers=admin_h,
    )
    assert res.status_code == 201
    assert res.json()["owner_user_id"] == PLATFORM_ACTING_ACTOR_ID


def test_platform_admin_purge_non_platform_memberships(client: TestClient) -> None:
    from civilai_platform.models.entities import MembershipStatus, Role, TenantMembership, UserProfile, utc_now

    acme = _bootstrap(client, "acme-member", email="member@acme.com", name="Acme Civil")
    acme_tenant_id = acme["memberships"][0]["tenant_id"]
    store = get_store()
    now = utc_now()
    store.put_user_profile(
        UserProfile(
            user_id="cross-tenant-admin",
            email="cross@civil.ai",
            first_name="Cross",
            last_name="Admin",
            created_at=now,
            updated_at=now,
        )
    )
    store.put_membership(
        TenantMembership(
            tenant_id=acme_tenant_id,
            user_id="cross-tenant-admin",
            role=Role.ADMIN,
            status=MembershipStatus.ACTIVE,
            joined_at=now,
        )
    )
    store.set_platform_admin("cross-tenant-admin", True)
    platform_tenant_svc.ensure_platform_admin_membership(store, "cross-tenant-admin")

    memberships = store.list_memberships_for_user("cross-tenant-admin")
    assert len(memberships) == 1
    platform_tenant = platform_tenant_svc.get_platform_tenant(store)
    assert platform_tenant is not None
    assert memberships[0].tenant_id == platform_tenant.tenant_id

    me = client.get("/v1/me", headers=_headers("cross-tenant-admin")).json()
    assert me["is_platform_admin"] is True
    assert len(me["memberships"]) == 1
    assert me["memberships"][0]["tenant_slug"] == platform_tenant_svc.PLATFORM_TENANT_SLUG


def test_platform_admin_bootstrap_routes_to_platform_tenant(client: TestClient) -> None:
    from civilai_platform.models.entities import UserProfile, utc_now

    _bootstrap(client, "acme-member", email="member@acme.com", name="Acme Civil")
    store = get_store()
    store.set_platform_admin("platform-only-admin", True)
    store.put_user_profile(
        UserProfile(
            user_id="platform-only-admin",
            email="platform@civil.ai",
            first_name="Platform",
            last_name="Admin",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    platform_tenant_svc.ensure_platform_admin_membership(store, "platform-only-admin")
    res = client.post(
        "/v1/dev/bootstrap",
        json={
            "name": "Platform Admin",
            "email": "platform@civil.ai",
        },
        headers=_headers("dev-platform-civil-ai"),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["is_platform_admin"] is True
    assert body["user_id"] == "platform-only-admin"
    assert body["memberships"][0]["tenant_slug"] == platform_tenant_svc.PLATFORM_TENANT_SLUG

    platform_tenant = platform_tenant_svc.get_platform_tenant(store)
    assert platform_tenant is not None
    admin_h = _headers("platform-only-admin", platform_tenant.tenant_id)
    assert client.get("/v1/tenant", headers=admin_h).status_code == 200


def test_dev_bootstrap_resolves_invited_user_by_email(client: TestClient) -> None:
    from civilai_platform.models.entities import MembershipStatus, Role, TenantMembership, UserProfile, utc_now

    store = get_store()
    tenant = tenant_svc.create_tenant(
        store,
        TenantCreate(name="Invited Firm", address="", location="", phone="", fax=""),
    )
    invited_id = "invited-user-uuid"
    now = utc_now()
    store.put_user_profile(
        UserProfile(
            user_id=invited_id,
            email="tenantadmin@invited.com",
            first_name="Tenant",
            last_name="Admin",
            created_at=now,
            updated_at=now,
        )
    )
    store.put_membership(
        TenantMembership(
            tenant_id=tenant.tenant_id,
            user_id=invited_id,
            role=Role.ADMIN,
            status=MembershipStatus.ACTIVE,
            joined_at=now,
        )
    )
    res = client.post(
        "/v1/dev/bootstrap",
        json={
            "name": "Tenant Admin",
            "email": "tenantadmin@invited.com",
            "tenant_slug": tenant.url_slug,
        },
        headers=_headers("dev-tenantadmin-invited-com"),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["user_id"] == invited_id
    assert body["memberships"][0]["tenant_slug"] == tenant.url_slug


def test_dev_bootstrap_activates_invited_membership_without_tenant_slug(client: TestClient) -> None:
    from civilai_platform.models.entities import MembershipStatus, Role, TenantMembership, UserProfile, utc_now

    store = get_store()
    tenant = tenant_svc.create_tenant(
        store,
        TenantCreate(name="Invited Only Firm", address="", location="", phone="", fax=""),
    )
    invited_id = "invited-only-uuid"
    now = utc_now()
    store.put_user_profile(
        UserProfile(
            user_id=invited_id,
            email="invited.only@firm.com",
            first_name="Invited",
            last_name="Only",
            created_at=now,
            updated_at=now,
        )
    )
    store.put_membership(
        TenantMembership(
            tenant_id=tenant.tenant_id,
            user_id=invited_id,
            role=Role.ADMIN,
            status=MembershipStatus.INVITED,
            joined_at=now,
        )
    )
    res = client.post(
        "/v1/dev/bootstrap",
        json={"name": "Invited Only", "email": "invited.only@firm.com"},
        headers=_headers("dev-invited-only-firm-com"),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["user_id"] == invited_id
    assert len(body["memberships"]) == 1
    assert body["memberships"][0]["tenant_slug"] == tenant.url_slug
    assert body["memberships"][0]["status"] == "active"
    membership = store.get_membership(tenant.tenant_id, invited_id)
    assert membership is not None
    assert membership.status == MembershipStatus.ACTIVE


def test_dev_bootstrap_prefers_invited_user_over_dev_duplicate_email(client: TestClient) -> None:
    from civilai_platform.models.entities import MembershipStatus, Role, TenantMembership, UserProfile, utc_now

    store = get_store()
    invited_tenant = tenant_svc.create_tenant(
        store,
        TenantCreate(name="Canonical Firm", address="", location="", phone="", fax=""),
    )
    dev_tenant = tenant_svc.create_tenant(
        store,
        TenantCreate(name="Dev Bootstrap Firm", address="", location="", phone="", fax=""),
    )
    invited_id = "c83c1e1e-8751-4923-8b77-71f42b0615c4"
    dev_id = "dev-bbrennan83-gmail-com"
    now = utc_now()
    email = "bbrennan83@gmail.com"
    for user_id, first_name in ((invited_id, "Brian"), (dev_id, "Brian Dev")):
        store.put_user_profile(
            UserProfile(
                user_id=user_id,
                email=email,
                first_name=first_name,
                last_name="Brennan",
                created_at=now,
                updated_at=now,
            )
        )
    store.put_membership(
        TenantMembership(
            tenant_id=invited_tenant.tenant_id,
            user_id=invited_id,
            role=Role.ADMIN,
            status=MembershipStatus.INVITED,
            joined_at=now,
        )
    )
    store.put_membership(
        TenantMembership(
            tenant_id=dev_tenant.tenant_id,
            user_id=dev_id,
            role=Role.ADMIN,
            status=MembershipStatus.ACTIVE,
            joined_at=now,
        )
    )
    res = client.post(
        "/v1/dev/bootstrap",
        json={"name": "Brian Brennan", "email": email},
        headers=_headers(dev_id),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["user_id"] == invited_id
    assert len(body["memberships"]) == 1
    assert body["memberships"][0]["tenant_slug"] == invited_tenant.url_slug
    assert body["memberships"][0]["status"] == "active"


def test_tenant_purge_requires_email_authorization(client: TestClient) -> None:
    boot = _bootstrap(client, "purge-member", email="purge@firm.com", name="Purge Firm")
    tenant_id = boot["memberships"][0]["tenant_id"]
    store = get_store()
    store.set_platform_admin("purge-admin", True)
    platform_tenant_svc.ensure_platform_admin_membership(store, "purge-admin")
    profile = store.get_user_profile("purge-admin")
    if not profile:
        from civilai_platform.models.entities import UserProfile, utc_now

        store.put_user_profile(
            UserProfile(
                user_id="purge-admin",
                email="admin@civil.ai",
                first_name="Admin",
                last_name="User",
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
    admin_h = _headers("purge-admin")

    req = client.post(f"/v1/admin/tenants/{tenant_id}/purge-request", headers=admin_h)
    assert req.status_code == 200
    code = req.json()["authorization_code"]
    assert code

    bad = client.post(
        f"/v1/admin/tenants/{tenant_id}/purge",
        json={"confirmation_email": "wrong@example.com", "authorization_code": code},
        headers=admin_h,
    )
    assert bad.status_code == 400

    ok = client.post(
        f"/v1/admin/tenants/{tenant_id}/purge",
        json={"confirmation_email": "admin@civil.ai", "authorization_code": code},
        headers=admin_h,
    )
    assert ok.status_code == 204
    assert store.get_tenant(tenant_id) is None
    assert store.list_memberships_for_tenant(tenant_id) == []


def test_platform_admin_user_crud(client: TestClient) -> None:
    store = get_store()
    store.set_platform_admin("sys-admin", True)
    platform_tenant_svc.ensure_platform_admin_membership(store, "sys-admin")
    h = _headers("sys-admin")

    created = client.post(
        "/v1/admin/platform-admins",
        json={
            "email": "ops@civil.ai",
            "first_name": "Ops",
            "last_name": "User",
            "invite": True,
        },
        headers=h,
    )
    assert created.status_code == 201
    user_id = created.json()["user_id"]

    updated = client.patch(
        f"/v1/admin/platform-admins/{user_id}",
        json={"first_name": "Operations"},
        headers=h,
    )
    assert updated.status_code == 200
    assert updated.json()["first_name"] == "Operations"

    listed = client.get("/v1/admin/platform-admins", headers=h)
    assert any(row["user_id"] == user_id for row in listed.json())

    deleted = client.delete(f"/v1/admin/platform-admins/{user_id}", headers=h)
    assert deleted.status_code == 204
    assert not store.is_platform_admin(user_id)
    platform = platform_tenant_svc.get_platform_tenant(store)
    assert platform is not None
    assert store.get_membership(platform.tenant_id, user_id) is None
    assert store.get_user_profile(user_id) is None


def test_platform_admin_invalidate_invited_user(client: TestClient) -> None:
    store = get_store()
    store.set_platform_admin("sys-admin", True)
    platform_tenant_svc.ensure_platform_admin_membership(store, "sys-admin")
    h = _headers("sys-admin")

    created = client.post(
        "/v1/admin/platform-admins",
        json={
            "email": "pending@civil.ai",
            "first_name": "Pending",
            "last_name": "Admin",
            "invite": True,
        },
        headers=h,
    )
    assert created.status_code == 201
    user_id = created.json()["user_id"]
    platform = platform_tenant_svc.get_platform_tenant(store)
    assert platform is not None
    membership = store.get_membership(platform.tenant_id, user_id)
    assert membership is not None
    assert membership.status.value == "invited"

    invalidated = client.post(
        f"/v1/admin/platform-admins/{user_id}/invalidate-invite",
        headers=h,
    )
    assert invalidated.status_code == 204
    assert not store.is_platform_admin(user_id)
    membership = store.get_membership(platform.tenant_id, user_id)
    assert membership is not None
    assert membership.status.value == "disabled"
    assert store.get_user_profile(user_id) is not None


def test_platform_admin_list_all_users(client: TestClient) -> None:
    store = get_store()
    from civilai_platform.models.entities import UserProfile, utc_now

    now = utc_now()
    store.put_user_profile(
        UserProfile(
            user_id="sys-admin",
            email="sys@civil.ai",
            first_name="Sys",
            last_name="Admin",
            created_at=now,
            updated_at=now,
        )
    )
    store.set_platform_admin("sys-admin", True)
    platform_tenant_svc.ensure_platform_admin_membership(store, "sys-admin")
    h = _headers("sys-admin")

    _, _admin_a = tenant_svc.create_tenant_with_admin(
        store,
        AdminTenantCreate(
            name="Alpha Firm",
            admin_email="alpha-admin@example.com",
            admin_first_name="Alpha",
            admin_last_name="Admin",
        ),
        actor_user_id="sys-admin",
    )
    tenant_b, _ = tenant_svc.create_tenant_with_admin(
        store,
        AdminTenantCreate(
            name="Beta Firm",
            admin_email="beta-admin@example.com",
            admin_first_name="Beta",
            admin_last_name="Admin",
        ),
        actor_user_id="sys-admin",
    )
    user_svc.create_user(
        store,
        tenant_id=tenant_b.tenant_id,
        actor_user_id="sys-admin",
        data=UserCreate(
            email="analyst@example.com",
            first_name="Casey",
            last_name="Analyst",
            invite=True,
        ),
    )

    listed = client.get("/v1/admin/users", headers=h)
    assert listed.status_code == 200
    body = listed.json()
    rows = body["users"]
    assert body["limit"] == 100
    assert body["total"] >= len(rows)
    assert any(
        row["email"] == "alpha-admin@example.com" and row["tenant_name"] == "Alpha Firm"
        for row in rows
    )
    assert any(
        row["email"] == "analyst@example.com" and row["tenant_name"] == "Beta Firm"
        for row in rows
    )
    assert any(row["user_id"] == "sys-admin" and row["is_platform_admin"] for row in rows)
