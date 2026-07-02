from abc import ABC, abstractmethod
from datetime import datetime

from civilai_platform.models.entities import (
    AgentRun,
    AuditEvent,
    Client,
    Project,
    ProjectState,
    Role,
    Tenant,
    TenantMembership,
    UserProfile,
)


class PlatformStore(ABC):
    # --- Tenant ---
    @abstractmethod
    def put_tenant(self, tenant: Tenant) -> None: ...

    @abstractmethod
    def get_tenant(self, tenant_id: str) -> Tenant | None: ...

    @abstractmethod
    def list_tenants(self) -> list[Tenant]: ...

    @abstractmethod
    def delete_tenant(self, tenant_id: str) -> None: ...

    # --- User profile ---
    @abstractmethod
    def put_user_profile(self, profile: UserProfile) -> None: ...

    @abstractmethod
    def get_user_profile(self, user_id: str) -> UserProfile | None: ...

    # --- Membership ---
    @abstractmethod
    def put_membership(self, membership: TenantMembership) -> None: ...

    @abstractmethod
    def get_membership(self, tenant_id: str, user_id: str) -> TenantMembership | None: ...

    @abstractmethod
    def list_memberships_for_tenant(self, tenant_id: str) -> list[TenantMembership]: ...

    @abstractmethod
    def list_memberships_for_user(self, user_id: str) -> list[TenantMembership]: ...

    @abstractmethod
    def delete_membership(self, tenant_id: str, user_id: str) -> None: ...

    # --- Client ---
    @abstractmethod
    def put_client(self, client: Client) -> None: ...

    @abstractmethod
    def get_client(self, tenant_id: str, client_id: str) -> Client | None: ...

    @abstractmethod
    def list_clients(self, tenant_id: str) -> list[Client]: ...

    @abstractmethod
    def delete_client(self, tenant_id: str, client_id: str) -> None: ...

    # --- Project ---
    @abstractmethod
    def put_project(self, project: Project) -> None: ...

    @abstractmethod
    def get_project(self, tenant_id: str, project_id: str) -> Project | None: ...

    @abstractmethod
    def list_projects(self, tenant_id: str) -> list[Project]: ...

    @abstractmethod
    def delete_project(self, tenant_id: str, project_id: str) -> None: ...

    # --- Project state ---
    @abstractmethod
    def put_project_state(self, state: ProjectState) -> None: ...

    @abstractmethod
    def get_project_state(self, tenant_id: str, project_id: str) -> ProjectState | None: ...

    # --- Audit ---
    @abstractmethod
    def put_audit_event(self, event: AuditEvent) -> None: ...

    @abstractmethod
    def list_audit_events(
        self, tenant_id: str, since: datetime | None = None, limit: int = 100
    ) -> list[AuditEvent]: ...

    # --- Platform admin ---
    @abstractmethod
    def is_platform_admin(self, user_id: str) -> bool: ...

    @abstractmethod
    def set_platform_admin(self, user_id: str, is_admin: bool) -> None: ...

    # --- Agent runs ---
    @abstractmethod
    def put_agent_run(self, run: AgentRun) -> None: ...

    @abstractmethod
    def get_agent_run(self, tenant_id: str, project_id: str, run_id: str) -> AgentRun | None: ...

    @abstractmethod
    def list_agent_runs(self, tenant_id: str, project_id: str, limit: int = 50) -> list[AgentRun]: ...
