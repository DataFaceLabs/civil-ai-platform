from datetime import datetime

from civilai_platform.models.entities import (
    AgentRun,
    AuditEvent,
    Client,
    Project,
    ProjectState,
    Tenant,
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
        self._audit: list[AuditEvent] = []
        self._platform_admins: set[str] = set()
        self._agent_runs: dict[tuple[str, str, str], AgentRun] = {}

    def put_tenant(self, tenant: Tenant) -> None:
        self._tenants[tenant.tenant_id] = tenant

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        return self._tenants.get(tenant_id)

    def list_tenants(self) -> list[Tenant]:
        return list(self._tenants.values())

    def delete_tenant(self, tenant_id: str) -> None:
        self._tenants.pop(tenant_id, None)

    def put_user_profile(self, profile: UserProfile) -> None:
        self._profiles[profile.user_id] = profile

    def get_user_profile(self, user_id: str) -> UserProfile | None:
        return self._profiles.get(user_id)

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

    def put_project_state(self, state: ProjectState) -> None:
        self._states[(state.tenant_id, state.project_id)] = state

    def get_project_state(self, tenant_id: str, project_id: str) -> ProjectState | None:
        return self._states.get((tenant_id, project_id))

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
