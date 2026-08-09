"""Tests for ADR-0008 zoning_scenario project state persistence."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from civilai_platform.app import create_app
from civilai_platform.models.zoning_scenario import ZoningScenarioState
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


def _headers(user_id: str, tenant_id: str | None = None) -> dict[str, str]:
    h = {"X-Dev-User-Id": user_id}
    if tenant_id:
        h["X-Tenant-Id"] = tenant_id
    return h


def _create_project(client: TestClient, user_id: str = "zs-user") -> tuple[str, str, dict[str, str]]:
    boot = _bootstrap(client, user_id, email="zs@test.com", name="Zoning Scenario Firm")
    tenant_id = boot["memberships"][0]["tenant_id"]
    h = _headers(user_id, tenant_id)
    res = client.post(
        "/v1/projects",
        json={"name": "Zoning Scenario Project", "address": "100 Congress Ave, Austin, TX"},
        headers=h,
    )
    assert res.status_code in {200, 201}
    return tenant_id, res.json()["project_id"], h


def test_zoning_scenario_round_trip(client: TestClient) -> None:
    _tenant_id, project_id, h = _create_project(client)
    payload = {
        "schema_version": 1,
        "analysis_basis": "baseline",
        "baseline_jurisdiction_key": "coa_full",
        "effective_jurisdiction_key": "coa_full",
        "active_scenario_id": "sc-1",
        "scenarios": [
            {
                "scenario_id": "sc-1",
                "label": "Rezone to MF-4",
                "status": "draft",
                "created_at": "2026-08-06T12:00:00Z",
                "updated_at": "2026-08-06T12:00:00Z",
                "created_by_user_id": "zs-user",
                "intent": {
                    "proposed_zoning_code": "MF-4",
                    "keep_overlays": True,
                },
                "baseline": {
                    "fields": {
                        "ZONING_REGS": {
                            "value": "SF-2",
                            "status": "complete",
                            "origin": "lake",
                        }
                    },
                    "structured": {
                        "zoning_code": "SF-2",
                        "overlays": [],
                        "jurisdiction_key": "coa_full",
                    },
                },
                "proposed": {
                    "fields": {
                        "ZONING_REGS": {
                            "value": "MF-4 (pending compute)",
                            "status": "review",
                            "origin": "user",
                        }
                    },
                    "structured": {
                        "zoning_code": "MF-4",
                        "jurisdiction_key": "coa_full",
                    },
                },
                "comparisons": [],
                "risk_summary": {"overall": "unknown"},
                "computation": {"status": "idle"},
            }
        ],
    }
    patch = client.patch(
        f"/v1/projects/{project_id}/state",
        json={"zoning_scenario": payload},
        headers=h,
    )
    assert patch.status_code == 200, patch.text
    body = patch.json()
    assert body["zoning_scenario"]["active_scenario_id"] == "sc-1"
    assert body["zoning_scenario"]["scenarios"][0]["intent"]["proposed_zoning_code"] == "MF-4"

    reloaded = client.get(f"/v1/projects/{project_id}/state", headers=h)
    assert reloaded.status_code == 200
    zs = reloaded.json()["zoning_scenario"]
    assert zs["schema_version"] == 1
    assert zs["scenarios"][0]["baseline"]["structured"]["zoning_code"] == "SF-2"


def test_analysis_basis_proposed_rejects_draft_status(client: TestClient) -> None:
    _tenant_id, project_id, h = _create_project(client, user_id="zs-user-2")
    payload = {
        "schema_version": 1,
        "analysis_basis": "proposed",
        "active_scenario_id": "sc-1",
        "scenarios": [
            {
                "scenario_id": "sc-1",
                "label": "Rezone",
                "status": "draft",
                "created_at": "2026-08-06T12:00:00Z",
                "updated_at": "2026-08-06T12:00:00Z",
                "created_by_user_id": "zs-user-2",
                "intent": {"proposed_zoning_code": "MF-4", "keep_overlays": True},
            }
        ],
    }
    # FastAPI/Pydantic may reject on request body before service merge.
    patch = client.patch(
        f"/v1/projects/{project_id}/state",
        json={"zoning_scenario": payload},
        headers=h,
    )
    assert patch.status_code in {400, 422}


def test_mvp_rejects_two_scenarios() -> None:
    with pytest.raises(Exception):
        ZoningScenarioState.model_validate(
            {
                "schema_version": 1,
                "analysis_basis": "baseline",
                "scenarios": [
                    {
                        "scenario_id": "a",
                        "label": "A",
                        "status": "draft",
                        "created_at": "2026-08-06T12:00:00Z",
                        "updated_at": "2026-08-06T12:00:00Z",
                        "created_by_user_id": "u",
                        "intent": {"proposed_zoning_code": "MF-4"},
                    },
                    {
                        "scenario_id": "b",
                        "label": "B",
                        "status": "draft",
                        "created_at": "2026-08-06T12:00:00Z",
                        "updated_at": "2026-08-06T12:00:00Z",
                        "created_by_user_id": "u",
                        "intent": {"proposed_zoning_code": "MF-3"},
                    },
                ],
            }
        )
