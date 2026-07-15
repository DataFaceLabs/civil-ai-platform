from datetime import datetime
from typing import Any

from civilai_platform.models.api import (
    ProjectActivityCreate,
    ProjectActivityResponse,
    ProjectActivityUpdate,
)
from civilai_platform.models.entities import ProjectActivity, new_id, utc_now
from civilai_platform.store.base import PlatformStore


def _actor_name(store: PlatformStore, actor_user_id: str) -> str:
    profile = store.get_user_profile(actor_user_id)
    if not profile:
        return "Unknown user"
    full_name = f"{profile.first_name} {profile.last_name}".strip()
    return full_name or profile.email


def record_project_activity(
    store: PlatformStore,
    *,
    tenant_id: str,
    project_id: str,
    actor_user_id: str,
    event_type: str,
    content: str,
    section_id: str | None = None,
    mentions: list[str] | None = None,
    detail: dict[str, Any] | None = None,
    event_id: str | None = None,
    created_at: datetime | None = None,
) -> ProjectActivity:
    if not store.get_project(tenant_id, project_id):
        raise ValueError("Project not found")
    now = utc_now()
    event = ProjectActivity(
        event_id=event_id or new_id(),
        tenant_id=tenant_id,
        project_id=project_id,
        actor_user_id=actor_user_id,
        actor_name=_actor_name(store, actor_user_id),
        event_type=event_type.strip(),
        section_id=section_id,
        content=content.strip(),
        mentions=mentions or [],
        detail=detail or {},
        created_at=created_at or now,
        updated_at=now,
    )
    store.put_project_activity(event)
    return event


def create_project_activity(
    store: PlatformStore,
    *,
    tenant_id: str,
    project_id: str,
    actor_user_id: str,
    data: ProjectActivityCreate,
) -> ProjectActivityResponse:
    existing = (
        store.get_project_activity(tenant_id, project_id, data.event_id) if data.event_id else None
    )
    if existing:
        return ProjectActivityResponse.from_entity(existing)
    event = record_project_activity(
        store,
        tenant_id=tenant_id,
        project_id=project_id,
        actor_user_id=actor_user_id,
        event_id=data.event_id,
        event_type=data.event_type,
        section_id=data.section_id,
        content=data.content,
        mentions=data.mentions,
        detail=data.detail,
        created_at=data.created_at,
    )
    return ProjectActivityResponse.from_entity(event)


def list_project_activity(
    store: PlatformStore,
    *,
    tenant_id: str,
    project_id: str,
    limit: int,
) -> list[ProjectActivityResponse]:
    if not store.get_project(tenant_id, project_id):
        raise ValueError("Project not found")
    events = store.list_project_activity(tenant_id, project_id, limit=limit)
    events.reverse()
    return [ProjectActivityResponse.from_entity(event) for event in events]


def update_project_activity(
    store: PlatformStore,
    *,
    tenant_id: str,
    project_id: str,
    event_id: str,
    actor_user_id: str,
    allow_any_actor: bool,
    data: ProjectActivityUpdate,
) -> ProjectActivityResponse:
    event = store.get_project_activity(tenant_id, project_id, event_id)
    if not event:
        raise ValueError("Activity event not found")
    if event.event_type != "note_added":
        raise PermissionError("Only notes can be updated")
    if event.actor_user_id != actor_user_id and not allow_any_actor:
        raise PermissionError("Only the note author can update this note")
    updated = event.model_copy(
        update={
            "content": data.content.strip(),
            "mentions": data.mentions,
            "updated_at": utc_now(),
        }
    )
    store.put_project_activity(updated)
    return ProjectActivityResponse.from_entity(updated)


def delete_project_activity(
    store: PlatformStore,
    *,
    tenant_id: str,
    project_id: str,
    event_id: str,
    actor_user_id: str,
    allow_any_actor: bool,
) -> None:
    event = store.get_project_activity(tenant_id, project_id, event_id)
    if not event:
        return
    if event.event_type != "note_added":
        raise PermissionError("Only notes can be deleted")
    if event.actor_user_id != actor_user_id and not allow_any_actor:
        raise PermissionError("Only the note author can delete this note")
    store.delete_project_activity(tenant_id, project_id, event_id)
