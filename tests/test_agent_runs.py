"""Tests for agent-runs API."""

import pytest
from fastapi.testclient import TestClient

from civilai_platform.app import create_app
from civilai_platform.store import get_store
from tests.conftest import bootstrap_client_user


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIVILAI_DEV_AUTH", "true")
    monkeypatch.setenv("CIVILAI_STORE_BACKEND", "memory")
    monkeypatch.setenv("CIVILAI_ARTIFACT_BACKEND", "memory")
    monkeypatch.setenv("CIVILAI_AGENT_DRY_RUN", "true")
    get_store.cache_clear()


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


def test_agent_run_create_and_get(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIVILAI_DEV_DATA_API_BASE", "http://dev-data.test:8001")
    monkeypatch.setenv("CIVILAI_DEV_DATA_ORIGINS", "https://develop.example.com")
    selected_bases: list[str | None] = []

    def _fake_agent(context_payload: dict, *, dry_run: bool) -> dict:
        assert dry_run is True
        selected_bases.append(context_payload.get("_data_api_base"))
        return {
            "message": "Draft complete.",
            "artifacts": [],
            "trace_summary": {"tools_used": []},
            "guardrail_warnings": [],
        }

    monkeypatch.setattr(
        "civilai_platform.services.agent_run._invoke_strands_agent",
        _fake_agent,
    )
    user_id = "user-agent"
    bootstrap = bootstrap_client_user(
        client,
        user_id,
        email="agent@example.com",
        name="Agent Firm",
    )
    tenant_id = bootstrap["memberships"][0]["tenant_id"]
    headers = {
        "X-Dev-User-Id": user_id,
        "X-Tenant-Id": tenant_id,
        "Origin": "https://develop.example.com",
    }

    project = client.post(
        "/v1/projects",
        json={"name": "Test Site", "address": "123 Main St"},
        headers=headers,
    )
    assert project.status_code == 201
    project_id = project.json()["project_id"]

    run = client.post(
        f"/v1/projects/{project_id}/agent-runs",
        json={
            "request": "Summarize zoning constraints.",
            "entity_id": "ent-123",
            "active_section_id": "zoning",
            "workflow": "minimal_qa",
        },
        headers=headers,
    )
    assert run.status_code == 201
    body = run.json()
    assert body["status"] == "succeeded"
    assert body["run_id"]
    assert body["message"]
    assert body["s3_prefix"].endswith("/")

    chat_run = client.post(
        f"/v1/projects/{project_id}/agent-runs",
        json={
            "request": "What should I verify for utilities?",
            "active_section_id": "utilities",
            "workflow": "assistant_chat",
            "thread_memory": "Earlier: analyst asked about water.",
            "section_body_plain": "Draft utilities paragraph.",
        },
        headers=headers,
    )
    assert chat_run.status_code == 201
    chat_body = chat_run.json()
    assert chat_body["status"] == "succeeded"
    assert chat_body["workflow"] == "assistant_chat"
    assert chat_body["message"]
    assert selected_bases == ["http://dev-data.test:8001", "http://dev-data.test:8001"]

    fetched = client.get(
        f"/v1/projects/{project_id}/agent-runs/{body['run_id']}",
        headers=headers,
    )
    assert fetched.status_code == 200
    assert fetched.json()["run_id"] == body["run_id"]


def test_section_draft_resolves_prompt_lab_config_before_agent(client: TestClient) -> None:
    user_id = "user-agent-prompt"
    bootstrap = bootstrap_client_user(
        client,
        user_id,
        email="agent-prompt@example.com",
        name="Prompt Firm",
    )
    tenant_id = bootstrap["memberships"][0]["tenant_id"]
    headers = {"X-Dev-User-Id": user_id, "X-Tenant-Id": tenant_id}
    project = client.post(
        "/v1/projects",
        json={"name": "Prompt Site", "address": "123 Main St"},
        headers=headers,
    )
    project_id = project.json()["project_id"]

    run = client.post(
        f"/v1/projects/{project_id}/agent-runs",
        json={
            "request": "Generate the zoning section draft.",
            "user_guidance": "",
            "mode": "generate",
            "entity_id": "ent-123",
            "active_section_id": "zoning",
            "workflow": "section_draft",
            "field_context": {
                "ZONING_REGS": "MF-4 permits multifamily uses.",
                "PLATTING_STATUS": "Platted",
                "IMPERVIOUS_REGS": "Maximum 70 percent",
                "WATER_SERVICE": "Austin Water",
            },
        },
        headers=headers,
    )

    assert run.status_code == 201
    body = run.json()
    assert body["status"] == "succeeded"
    assert 'You are drafting the "Zoning" portion' in body["request"]
    assert "MF-4 permits multifamily uses." in body["request"]
    assert "Generate the zoning section draft." not in body["request"]
    assert 'You are drafting the "Zoning" portion' in body["message"]
    field_context = body["trace_summary"]["field_context"]
    assert field_context["ZONING_REGS"] == "MF-4 permits multifamily uses."
    assert field_context["PLATTING_STATUS"] == "Platted"
    assert field_context["IMPERVIOUS_REGS"] == "Maximum 70 percent"
    assert field_context["PROPERTY_ADDRESS"] == "123 Main St"
    assert "WATER_SERVICE" not in field_context
    activity = client.get(
        f"/v1/projects/{project_id}/activity",
        headers=headers,
    )
    assert activity.status_code == 200
    draft_events = [
        event
        for event in activity.json()
        if event["event_type"] == "section_draft_created"
    ]
    assert len(draft_events) == 1
    assert draft_events[0]["event_id"] == body["run_id"]
    assert draft_events[0]["section_id"] == "zoning"


def test_section_draft_resolves_entity_id_from_project_address(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Projects saved without site_payload.entity_id still draft when address is unique."""
    captured: dict[str, object] = {}

    def _fake_agent(context_payload: dict, *, dry_run: bool) -> dict:
        captured["entity_id"] = context_payload.get("entity_id")
        return {
            "message": "Draft complete.",
            "artifacts": [],
            "trace_summary": {"tools_used": []},
            "guardrail_warnings": [],
        }

    class _FakeProxy:
        def __init__(self, *, base_url: str | None = None) -> None:
            self.base_url = base_url

        def resolve_site_address(self, address: str) -> dict:
            assert "Spyglass" in address
            return {"entity_id": "186e4007-021c-b65d-a67a-0ac73dec97a9"}

    monkeypatch.setattr(
        "civilai_platform.services.agent_run._invoke_strands_agent",
        _fake_agent,
    )
    monkeypatch.setattr(
        "civilai_platform.services.data_proxy.DataProxyClient",
        _FakeProxy,
    )

    user_id = "user-agent-entity"
    bootstrap = bootstrap_client_user(
        client,
        user_id,
        email="agent-entity@example.com",
        name="Entity Firm",
    )
    tenant_id = bootstrap["memberships"][0]["tenant_id"]
    headers = {"X-Dev-User-Id": user_id, "X-Tenant-Id": tenant_id}
    project = client.post(
        "/v1/projects",
        json={"name": "Spyglass", "address": "1300 Spyglass Dr, Austin, TX 78746"},
        headers=headers,
    )
    assert project.status_code == 201
    project_id = project.json()["project_id"]

    run = client.post(
        f"/v1/projects/{project_id}/agent-runs",
        json={
            "request": "Generate the parcel section draft.",
            "workflow": "section_draft",
            "active_section_id": "parcel",
            "mode": "generate",
            "field_context": {"PROPERTY_ACRES": "17.28"},
        },
        headers=headers,
    )
    assert run.status_code == 201
    assert run.json()["status"] == "succeeded"
    assert captured["entity_id"] == "186e4007-021c-b65d-a67a-0ac73dec97a9"
