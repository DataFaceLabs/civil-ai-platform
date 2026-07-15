import pytest
from fastapi.testclient import TestClient

from civilai_platform.app import create_app
from civilai_platform.store import get_store
from tests.conftest import bootstrap_client_user


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIVILAI_DEV_AUTH", "true")
    monkeypatch.setenv("CIVILAI_STORE_BACKEND", "memory")
    get_store.cache_clear()


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


def test_project_activity_lifecycle(client: TestClient) -> None:
    user_id = "activity-user"
    bootstrap = bootstrap_client_user(
        client,
        user_id,
        email="activity@example.com",
        name="Activity Firm",
    )
    tenant_id = bootstrap["memberships"][0]["tenant_id"]
    headers = {"X-Dev-User-Id": user_id, "X-Tenant-Id": tenant_id}
    project = client.post(
        "/v1/projects",
        json={"name": "Activity Site", "address": "123 Main St"},
        headers=headers,
    )
    assert project.status_code == 201
    project_id = project.json()["project_id"]

    initial = client.get(f"/v1/projects/{project_id}/activity", headers=headers)
    assert initial.status_code == 200
    assert [event["event_type"] for event in initial.json()] == ["project_created"]
    assert initial.json()[0]["actor_name"] == "Test User"

    payload = {
        "event_id": "note-1",
        "event_type": "note_added",
        "section_id": "zoning",
        "content": "Please review @reviewer@example.com",
        "mentions": ["reviewer@example.com"],
        "created_at": "2026-07-14T12:00:00Z",
    }
    created = client.post(
        f"/v1/projects/{project_id}/activity",
        json=payload,
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["event_id"] == "note-1"

    duplicate = client.post(
        f"/v1/projects/{project_id}/activity",
        json={**payload, "content": "Should not overwrite"},
        headers=headers,
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["content"] == payload["content"]

    updated = client.patch(
        f"/v1/projects/{project_id}/activity/note-1",
        json={"content": "Reviewed", "mentions": []},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == "Reviewed"

    deleted = client.delete(
        f"/v1/projects/{project_id}/activity/note-1",
        headers=headers,
    )
    assert deleted.status_code == 204
    remaining = client.get(f"/v1/projects/{project_id}/activity", headers=headers)
    assert [event["event_type"] for event in remaining.json()] == ["project_created"]
