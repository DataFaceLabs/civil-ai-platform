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


def test_agent_run_create_and_get(client: TestClient) -> None:
    user_id = "user-agent"
    bootstrap = bootstrap_client_user(
        client,
        user_id,
        email="agent@example.com",
        name="Agent Firm",
    )
    tenant_id = bootstrap["memberships"][0]["tenant_id"]
    headers = {"X-Dev-User-Id": user_id, "X-Tenant-Id": tenant_id}

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

    fetched = client.get(
        f"/v1/projects/{project_id}/agent-runs/{body['run_id']}",
        headers=headers,
    )
    assert fetched.status_code == 200
    assert fetched.json()["run_id"] == body["run_id"]
