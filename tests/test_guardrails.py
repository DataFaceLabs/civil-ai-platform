"""Tests for Facts Guard Rails (GR-0)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from civilai_platform.app import create_app
from civilai_platform.services import guardrails as guardrails_svc
from civilai_platform.services.guardrails_merge import (
    FieldGuardRail,
    GuardRailsScopePayload,
    merge_guardrails,
)
from civilai_platform.store import get_store
from civilai_platform.store.memory import MemoryStore


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIVILAI_DEV_AUTH", "true")
    monkeypatch.setenv("CIVILAI_STORE_BACKEND", "memory")
    get_store.cache_clear()


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def store() -> MemoryStore:
    return get_store()  # type: ignore[return-value]


def _headers(user_id: str, tenant_id: str | None = None) -> dict[str, str]:
    h = {"X-Dev-User-Id": user_id}
    if tenant_id:
        h["X-Tenant-Id"] = tenant_id
    return h


def test_merge_most_specific_field_wins() -> None:
    layers = [
        GuardRailsScopePayload(
            scope_key="_default",
            fields={
                "MAX_BUILDING_HEIGHT": FieldGuardRail(
                    source_tier=["lake", "dsi"],
                    llm_extract_allowed=False,
                )
            },
        ),
        GuardRailsScopePayload(
            scope_key="jurisdiction:seattle",
            fields={
                "MAX_BUILDING_HEIGHT": FieldGuardRail(
                    source_tier=["lake", "dsi", "topic_hydrate"],
                    llm_extract_allowed=True,
                )
            },
        ),
    ]
    effective = merge_guardrails(layers, catalog_ready=True)
    assert effective.fields["MAX_BUILDING_HEIGHT"].llm_extract_allowed is True
    assert "topic_hydrate" in effective.fields["MAX_BUILDING_HEIGHT"].source_tier


def test_catalog_gate_strips_topic_hydrate_when_not_ready(store: MemoryStore) -> None:
    guardrails_svc.seed_zoning_guardrails_from_yaml(store, refresh=True)
    gated = guardrails_svc.resolve_guardrails(
        store,
        state_abbr="WA",
        county_fips="53033",
        jurisdiction_key="seattle",
        catalog_ready=False,
    )
    assert gated.topic_hydrate_enabled is False
    assert gated.topics["height_far"]["enabled"] is False

    ready = guardrails_svc.resolve_guardrails(
        store,
        state_abbr="WA",
        county_fips="53033",
        jurisdiction_key="seattle",
        catalog_ready=True,
    )
    assert ready.topic_hydrate_enabled is True
    assert ready.topics["height_far"]["enabled"] is True


def test_seattle_seed_marks_ic_not_applicable(store: MemoryStore) -> None:
    guardrails_svc.seed_zoning_guardrails_from_yaml(store, refresh=True)
    effective = guardrails_svc.resolve_guardrails(
        store,
        state_abbr="WA",
        county_fips="53033",
        jurisdiction_key="seattle",
        catalog_ready=True,
    )
    assert effective.fields["IMPERVIOUS_COVER_LIMIT"]["not_applicable"] is True
    assert "GREEN_FACTOR_MIN" in effective.fields
    assert effective.fields["GREEN_FACTOR_MIN"]["show_when_populated"] is True
    assert "jurisdiction:seattle" in effective.applied_scopes


def test_admin_guardrails_crud(client: TestClient, store: MemoryStore) -> None:
    from civilai_platform.services import platform_tenant as platform_tenant_svc

    store.set_platform_admin("gr-admin", True)
    platform_tenant_svc.ensure_platform_admin_membership(store, "gr-admin")
    h = _headers("gr-admin")

    list_res = client.get("/v1/admin/guardrails/zoning/scopes", headers=h)
    assert list_res.status_code == 200
    assert list_res.json()["scopes"] == []

    put_res = client.put(
        "/v1/admin/guardrails/zoning/scopes/jurisdiction:testville",
        headers=h,
        json={
            "schema_version": 1,
            "fields": {
                "MAX_BUILDING_HEIGHT": {
                    "source_tier": ["lake", "dsi"],
                    "llm_extract_allowed": False,
                }
            },
            "topics": {},
        },
    )
    assert put_res.status_code == 200
    assert put_res.json()["scope_key"] == "jurisdiction:testville"

    get_res = client.get(
        "/v1/admin/guardrails/zoning/scopes/jurisdiction:testville",
        headers=h,
    )
    assert get_res.status_code == 200

    del_res = client.delete(
        "/v1/admin/guardrails/zoning/scopes/jurisdiction:testville",
        headers=h,
    )
    assert del_res.status_code == 204


def test_resolve_requires_tenant_membership(client: TestClient, store: MemoryStore) -> None:
    from tests.seed import seed_tenant_member

    guardrails_svc.seed_zoning_guardrails_from_yaml(store, refresh=True)
    tenant_id, _ = seed_tenant_member(
        store,
        user_id="gr-viewer",
        email="viewer@example.com",
    )

    res = client.get(
        "/v1/guardrails/resolve",
        headers=_headers("gr-viewer", tenant_id),
        params={"jurisdiction_key": "seattle", "catalog_ready": "true"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["topic_hydrate_enabled"] is True
    assert "guardrails_version" in body


def test_resolve_catalog_ready_from_data_api(client: TestClient, store: MemoryStore) -> None:
    from tests.seed import seed_tenant_member

    guardrails_svc.seed_zoning_guardrails_from_yaml(store, refresh=True)
    tenant_id, _ = seed_tenant_member(
        store,
        user_id="gr-viewer-2",
        email="v2@example.com",
    )
    h = _headers("gr-viewer-2", tenant_id)

    with patch(
        "civilai_platform.services.guardrails.jurisdiction_catalog_ready",
        return_value=True,
    ):
        res = client.get(
            "/v1/guardrails/resolve",
            headers=h,
            params={"jurisdiction_key": "seattle"},
        )
    assert res.status_code == 200
    assert res.json()["topic_hydrate_enabled"] is True
