from datetime import datetime

from civilai_platform.models.entities import (
    AgentRun,
    AuditEvent,
    Client,
    LlmBaselineTemplate,
    Project,
    ProjectActivity,
    ProjectState,
    Tenant,
    TenantLlmConfig,
    TenantMembership,
    UserProfile,
)
from civilai_platform.store.base import PlatformStore


class MemoryStore(PlatformStore):
    def __init__(self) -> None:
        self._tenants: dict[str, Tenant] = {}
        self._profiles: dict[str, UserProfile] = {}
        self._memberships: dict[tuple[str, str], TenantMembership] = {}
        self._clients: dict[tuple[str, str], Client] = {}
        self._projects: dict[tuple[str, str], Project] = {}
        self._states: dict[tuple[str, str], ProjectState] = {}
        self._project_activity: dict[tuple[str, str, str], ProjectActivity] = {}
        self._audit: list[AuditEvent] = []
        self._platform_admins: set[str] = set()
        self._agent_runs: dict[tuple[str, str, str], AgentRun] = {}
        self._slug_index: dict[str, str] = {}
        self._llm_baseline: LlmBaselineTemplate | None = None
        self._tenant_llm: dict[str, TenantLlmConfig] = {}

    def put_tenant(self, tenant: Tenant) -> None:
        existing = self._tenants.get(tenant.tenant_id)
        if existing and existing.url_slug != tenant.url_slug:
            self._slug_index.pop(existing.url_slug, None)
        self._tenants[tenant.tenant_id] = tenant
        self._slug_index[tenant.url_slug] = tenant.tenant_id

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        return self._tenants.get(tenant_id)

    def get_tenant_by_slug(self, url_slug: str) -> Tenant | None:
        tenant_id = self._slug_index.get(url_slug)
        if not tenant_id:
            return None
        return self._tenants.get(tenant_id)

    def list_tenant_slugs(self) -> set[str]:
        return set(self._slug_index.keys())

    def list_tenants(self) -> list[Tenant]:
        return list(self._tenants.values())

    def delete_tenant(self, tenant_id: str) -> None:
        tenant = self._tenants.pop(tenant_id, None)
        if tenant:
            self._slug_index.pop(tenant.url_slug, None)
        self._tenant_llm.pop(tenant_id, None)

    def purge_tenant_data(self, tenant_id: str) -> list[str]:
        user_ids = [m.user_id for m in self.list_memberships_for_tenant(tenant_id)]
        for membership in self.list_memberships_for_tenant(tenant_id):
            self.delete_membership(tenant_id, membership.user_id)
        for client in self.list_clients(tenant_id):
            self.delete_client(tenant_id, client.client_id)
        for project in self.list_projects(tenant_id):
            self.delete_project(tenant_id, project.project_id)
        self._agent_runs = {
            key: run
            for key, run in self._agent_runs.items()
            if key[0] != tenant_id
        }
        self._audit = [event for event in self._audit if event.tenant_id != tenant_id]
        self.delete_tenant(tenant_id)
        for user_id in user_ids:
            if not self.list_memberships_for_user(user_id):
                self.delete_user_profile(user_id)
                self._platform_admins.discard(user_id)
        return user_ids

    def get_llm_baseline(self) -> LlmBaselineTemplate | None:
        return self._llm_baseline

    def put_llm_baseline(self, baseline: LlmBaselineTemplate) -> None:
        self._llm_baseline = baseline

    def get_tenant_llm_config(self, tenant_id: str) -> TenantLlmConfig | None:
        return self._tenant_llm.get(tenant_id)

    def put_tenant_llm_config(self, config: TenantLlmConfig) -> None:
        self._tenant_llm[config.tenant_id] = config

    def list_platform_admin_user_ids(self) -> list[str]:
        return sorted(self._platform_admins)

    def put_user_profile(self, profile: UserProfile) -> None:
        self._profiles[profile.user_id] = profile

    def get_user_profile(self, user_id: str) -> UserProfile | None:
        return self._profiles.get(user_id)

    def delete_user_profile(self, user_id: str) -> None:
        self._profiles.pop(user_id, None)

    def put_membership(self, membership: TenantMembership) -> None:
        self._memberships[(membership.tenant_id, membership.user_id)] = membership

    def get_membership(self, tenant_id: str, user_id: str) -> TenantMembership | None:
        return self._memberships.get((tenant_id, user_id))

    def list_memberships_for_tenant(self, tenant_id: str) -> list[TenantMembership]:
        return [m for (tid, _), m in self._memberships.items() if tid == tenant_id]

    def list_memberships_for_user(self, user_id: str) -> list[TenantMembership]:
        return [m for (_, uid), m in self._memberships.items() if uid == user_id]

    def delete_membership(self, tenant_id: str, user_id: str) -> None:
        self._memberships.pop((tenant_id, user_id), None)

    def put_client(self, client: Client) -> None:
        self._clients[(client.tenant_id, client.client_id)] = client

    def get_client(self, tenant_id: str, client_id: str) -> Client | None:
        return self._clients.get((tenant_id, client_id))

    def list_clients(self, tenant_id: str) -> list[Client]:
        return [c for (tid, _), c in self._clients.items() if tid == tenant_id]

    def delete_client(self, tenant_id: str, client_id: str) -> None:
        self._clients.pop((tenant_id, client_id), None)

    def put_project(self, project: Project) -> None:
        self._projects[(project.tenant_id, project.project_id)] = project

    def get_project(self, tenant_id: str, project_id: str) -> Project | None:
        return self._projects.get((tenant_id, project_id))

    def list_projects(self, tenant_id: str) -> list[Project]:
        return [p for (tid, _), p in self._projects.items() if tid == tenant_id]

    def delete_project(self, tenant_id: str, project_id: str) -> None:
        self._projects.pop((tenant_id, project_id), None)
        self._states.pop((tenant_id, project_id), None)
        self._project_activity = {
            key: event
            for key, event in self._project_activity.items()
            if key[:2] != (tenant_id, project_id)
        }

    def put_project_state(self, state: ProjectState) -> None:
        self._states[(state.tenant_id, state.project_id)] = state

    def get_project_state(self, tenant_id: str, project_id: str) -> ProjectState | None:
        return self._states.get((tenant_id, project_id))

    def put_project_activity(self, event: ProjectActivity) -> None:
        self._project_activity[(event.tenant_id, event.project_id, event.event_id)] = event

    def get_project_activity(
        self, tenant_id: str, project_id: str, event_id: str
    ) -> ProjectActivity | None:
        return self._project_activity.get((tenant_id, project_id, event_id))

    def list_project_activity(
        self, tenant_id: str, project_id: str, limit: int = 200
    ) -> list[ProjectActivity]:
        events = [
            event
            for (tid, pid, _), event in self._project_activity.items()
            if tid == tenant_id and pid == project_id
        ]
        events.sort(key=lambda event: (event.created_at, event.event_id), reverse=True)
        return events[:limit]

    def delete_project_activity(self, tenant_id: str, project_id: str, event_id: str) -> None:
        self._project_activity.pop((tenant_id, project_id, event_id), None)

    def put_audit_event(self, event: AuditEvent) -> None:
        self._audit.append(event)

    def list_audit_events(
        self, tenant_id: str, since: datetime | None = None, limit: int = 100
    ) -> list[AuditEvent]:
        events = [e for e in self._audit if e.tenant_id == tenant_id]
        if since:
            events = [e for e in events if e.created_at >= since]
        events.sort(key=lambda e: e.created_at, reverse=True)
        return events[:limit]

    def is_platform_admin(self, user_id: str) -> bool:
        return user_id in self._platform_admins

    def set_platform_admin(self, user_id: str, is_admin: bool) -> None:
        if is_admin:
            self._platform_admins.add(user_id)
        else:
            self._platform_admins.discard(user_id)

    def put_agent_run(self, run: AgentRun) -> None:
        self._agent_runs[(run.tenant_id, run.project_id, run.run_id)] = run

    def get_agent_run(self, tenant_id: str, project_id: str, run_id: str) -> AgentRun | None:
        return self._agent_runs.get((tenant_id, project_id, run_id))

    def list_agent_runs(self, tenant_id: str, project_id: str, limit: int = 50) -> list[AgentRun]:
        runs = [
            r
            for (tid, pid, _), r in self._agent_runs.items()
            if tid == tenant_id and pid == project_id
        ]
        runs.sort(key=lambda r: r.created_at, reverse=True)
        return runs[:limit]
