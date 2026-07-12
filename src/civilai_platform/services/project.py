from civilai_platform.models.api import (
    ProjectCreate,
    ProjectResponse,
    ProjectStatePatch,
    ProjectStateResponse,
    ProjectUpdate,
)
from civilai_platform.models.entities import (
    Project,
    ProjectState,
    ProjectStatus,
    Section,
    new_id,
    utc_now,
)
from civilai_platform.services import agent_corpus
from civilai_platform.services.audit import record_audit
from civilai_platform.services.client import sync_client_fields_to_sections
from civilai_platform.store.base import PlatformStore

WORKFLOW_STEPS = [
    ("client", "Client"),
    ("parcel", "Parcel"),
    ("zoning", "Zoning"),
    ("environmental", "Environmental"),
    ("utilities", "Utilities"),
    ("access", "Access"),
    ("exhibits", "Insights"),
    ("draft", "Draft"),
]


def _default_sections() -> list[Section]:
    return [
        Section(id=new_id(), title=title, step_key=key, fields={})
        for key, title in WORKFLOW_STEPS
    ]


def create_project(
    store: PlatformStore,
    *,
    tenant_id: str,
    owner_user_id: str,
    actor_user_id: str,
    data: ProjectCreate,
) -> ProjectResponse:
    now = utc_now()
    project_id = new_id()
    project = Project(
        project_id=project_id,
        tenant_id=tenant_id,
        name=data.name,
        address=data.address,
        jurisdiction=data.jurisdiction,
        owner_user_id=owner_user_id,
        client_id=data.client_id,
        status=ProjectStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    sections = _default_sections()
    if data.client_id:
        client = store.get_client(tenant_id, data.client_id)
        if client:
            sections = sync_client_fields_to_sections(client, sections)
    state = ProjectState(
        project_id=project_id,
        tenant_id=tenant_id,
        sections=sections,
        updated_at=now,
    )
    store.put_project(project)
    store.put_project_state(state)
    record_audit(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="project.create",
        resource_type="project",
        resource_id=project_id,
    )
    return ProjectResponse.from_entity(project)


def update_project(
    store: PlatformStore,
    *,
    tenant_id: str,
    project_id: str,
    actor_user_id: str,
    data: ProjectUpdate,
) -> ProjectResponse:
    project = store.get_project(tenant_id, project_id)
    if not project:
        raise ValueError("Project not found")
    updates = data.model_dump(exclude_unset=True)
    updated = project.model_copy(update={**updates, "updated_at": utc_now()})
    store.put_project(updated)
    if data.client_id:
        client = store.get_client(tenant_id, data.client_id)
        state = store.get_project_state(tenant_id, project_id)
        if client and state:
            sections = sync_client_fields_to_sections(client, state.sections)
            store.put_project_state(state.model_copy(update={"sections": sections, "updated_at": utc_now()}))
    record_audit(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="project.update",
        resource_type="project",
        resource_id=project_id,
    )
    return ProjectResponse.from_entity(updated)


def delete_project(
    store: PlatformStore,
    *,
    tenant_id: str,
    project_id: str,
    actor_user_id: str,
) -> None:
    if not store.get_project(tenant_id, project_id):
        raise ValueError("Project not found")
    store.delete_project(tenant_id, project_id)
    record_audit(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="project.delete",
        resource_type="project",
        resource_id=project_id,
    )


def list_projects(store: PlatformStore, tenant_id: str) -> list[ProjectResponse]:
    return [ProjectResponse.from_entity(p) for p in store.list_projects(tenant_id)]


def get_project_state(store: PlatformStore, tenant_id: str, project_id: str) -> ProjectStateResponse:
    state = store.get_project_state(tenant_id, project_id)
    if not state:
        raise ValueError("Project state not found")
    return ProjectStateResponse.from_entity(state)


def _merge_project_state(state: ProjectState, patch: ProjectStatePatch) -> ProjectState:
    """Re-validate nested section/field models after patch (model_copy keeps raw dicts)."""
    merged = state.model_dump()
    merged.update(patch.model_dump(exclude_unset=True))
    merged["updated_at"] = utc_now()
    return ProjectState.model_validate(merged)


def _entity_id_from_state(state: ProjectState) -> str | None:
    parcel = state.parcel if isinstance(state.parcel, dict) else {}
    return parcel.get("entity_id") or parcel.get("entityId")


def patch_project_state(
    store: PlatformStore,
    *,
    tenant_id: str,
    project_id: str,
    actor_user_id: str,
    patch: ProjectStatePatch,
    actor_role: str | None = None,
) -> ProjectStateResponse:
    state = store.get_project_state(tenant_id, project_id)
    if not state:
        raise ValueError("Project state not found")
    updated = _merge_project_state(state, patch)
    store.put_project_state(updated)
    # Best-effort capture of every section milestone (edit/approve/reopen). Diffs the
    # pre-save sections against the saved ones; never blocks the save.
    agent_corpus.capture_section_transitions(
        tenant_id=tenant_id,
        project_id=project_id,
        entity_id=_entity_id_from_state(state),
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        old_sections=state.sections,
        new_sections=updated.sections,
    )
    project = store.get_project(tenant_id, project_id)
    if project:
        store.put_project(project.model_copy(update={"updated_at": utc_now()}))
    record_audit(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="project.state.patch",
        resource_type="project",
        resource_id=project_id,
    )
    return ProjectStateResponse.from_entity(updated)
