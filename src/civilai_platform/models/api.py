from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from civilai_platform.models.entities import (
    Client,
    ClientContact,
    ClientNote,
    ContextDoc,
    FeasibilityDocumentRef,
    FieldValue,
    LlmBaselineTemplate,
    MembershipStatus,
    Project,
    ProjectState,
    Role,
    Section,
    Tenant,
    TenantLlmConfig,
    TenantMembership,
    TenantStatus,
    UserProfile,
    VerificationStep,
)


class TenantCreate(BaseModel):
    name: str
    url_slug: str | None = None
    address: str = ""
    location: str = ""
    phone: str = ""
    fax: str = ""


class AdminTenantCreate(TenantCreate):
    """Platform admin creates tenant and invites the initial tenant admin."""

    admin_email: str
    admin_first_name: str
    admin_last_name: str


class TenantUpdate(BaseModel):
    name: str | None = None
    url_slug: str | None = None
    address: str | None = None
    location: str | None = None
    phone: str | None = None
    fax: str | None = None
    logo_s3_key: str | None = None
    status: TenantStatus | None = None
    feature_flags: dict[str, bool] | None = None
    enabled_data_sources: list[str] | None = None


class TenantResponse(BaseModel):
    tenant_id: str
    name: str
    url_slug: str
    address: str
    location: str
    phone: str
    fax: str
    logo_s3_key: str | None
    status: TenantStatus
    feature_flags: dict[str, bool]
    enabled_data_sources: list[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, t: Tenant) -> "TenantResponse":
        return cls(**t.model_dump())


class PublicTenantResponse(BaseModel):
    tenant_id: str
    name: str
    url_slug: str
    logo_url: str | None = None


class TenantMembershipSummary(BaseModel):
    tenant_id: str
    tenant_name: str
    tenant_slug: str
    role: Role
    status: MembershipStatus


class LlmConfigResponse(BaseModel):
    version: int
    baseline_version_at_copy: int | None = None
    config: dict[str, Any]
    updated_at: datetime | None = None


class LlmConfigUpdate(BaseModel):
    config: dict[str, Any]


class TenantLlmInvokeRequest(BaseModel):
    step_key: str
    user_prompt: str
    field_context: dict[str, str] = Field(default_factory=dict)
    search_context_hint: str = ""


class LogoPresignResponse(BaseModel):
    upload_url: str
    s3_key: str
    expires_in: int


class LogoPresignRequest(BaseModel):
    filename: str
    content_type: str


class PlatformAdminResponse(BaseModel):
    user_id: str
    email: str
    first_name: str
    last_name: str
    phone: str | None = None


class PlatformAdminCreate(BaseModel):
    email: str
    first_name: str
    last_name: str
    phone: str | None = None
    password: str | None = None
    invite: bool = True


class PlatformAdminUpdate(BaseModel):
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None


class AdminUserRowResponse(BaseModel):
    user_id: str
    email: str
    first_name: str
    last_name: str
    phone: str | None = None
    role: Role
    status: MembershipStatus
    tenant_id: str
    tenant_name: str
    tenant_slug: str
    is_platform_admin: bool = False
    joined_at: datetime


class AdminUserListResponse(BaseModel):
    users: list[AdminUserRowResponse]
    total: int
    limit: int


class TenantPurgeConfirm(BaseModel):
    confirmation_email: str
    authorization_code: str


class TenantPurgeRequestResponse(BaseModel):
    message: str
    authorization_code: str | None = None


class UserCreate(BaseModel):
    email: str
    first_name: str
    last_name: str
    phone: str | None = None
    role: Role = Role.ANALYST
    password: str | None = None
    invite: bool = True


class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    role: Role | None = None
    status: MembershipStatus | None = None


class UserResponse(BaseModel):
    user_id: str
    email: str
    first_name: str
    last_name: str
    phone: str | None
    role: Role
    status: MembershipStatus
    joined_at: datetime


class MeResponse(BaseModel):
    user_id: str
    email: str
    first_name: str
    last_name: str
    phone: str | None
    memberships: list["TenantMembershipSummary"] = Field(default_factory=list)
    is_platform_admin: bool = False


class MeUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None


class ClientCreate(BaseModel):
    name: str
    address: str = ""
    location: str = ""
    contacts: list[ClientContact] = Field(default_factory=list)
    notes: list[ClientNote] = Field(default_factory=list)


class ClientUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    location: str | None = None
    contacts: list[ClientContact] | None = None
    notes: list[ClientNote] | None = None


class ClientResponse(BaseModel):
    client_id: str
    tenant_id: str
    name: str
    address: str
    location: str
    contacts: list[ClientContact]
    notes: list[ClientNote]
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, c: Client) -> "ClientResponse":
        return cls(**c.model_dump())


class ProjectCreate(BaseModel):
    name: str
    address: str
    jurisdiction: str = ""
    client_id: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    jurisdiction: str | None = None
    client_id: str | None = None
    owner_user_id: str | None = None


class ProjectResponse(BaseModel):
    project_id: str
    tenant_id: str
    name: str
    address: str
    jurisdiction: str
    owner_user_id: str
    client_id: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, p: Project) -> "ProjectResponse":
        return cls(**p.model_dump())


class ProjectStatePatch(BaseModel):
    sections: list[Section] | None = None
    context_docs: list[ContextDoc] | None = None
    proposed_use: str | None = None
    parcel: dict | None = None
    site_payload: dict | None = None
    site_context: dict[str, FieldValue] | None = None
    tcad_prop_id: int | None = None
    client_contacts: list[ClientContact] | None = None
    client_notes: list[ClientNote] | None = None
    references: list[dict] | None = None
    feasibility_document: FeasibilityDocumentRef | None = None
    verification_steps: list[VerificationStep] | None = None


class ProjectStateResponse(BaseModel):
    project_id: str
    tenant_id: str
    sections: list[Section]
    context_docs: list[ContextDoc]
    proposed_use: str | None
    parcel: dict | None
    site_payload: dict | None
    site_context: dict[str, FieldValue] | None
    tcad_prop_id: int | None
    client_contacts: list[ClientContact]
    client_notes: list[ClientNote]
    references: list[dict]
    feasibility_document: FeasibilityDocumentRef | None
    verification_steps: list[VerificationStep]
    updated_at: datetime

    @classmethod
    def from_entity(cls, s: ProjectState) -> "ProjectStateResponse":
        return cls(**s.model_dump())


class AgentRunCreate(BaseModel):
    request: str = Field(min_length=1)
    entity_id: str | None = None
    active_section_id: str | None = None
    workflow: str | None = None
    field_context: dict[str, str] = Field(default_factory=dict)
    proposed_use: str | None = None


class AgentRunResponse(BaseModel):
    run_id: str
    tenant_id: str
    project_id: str
    status: str
    workflow: str | None
    request: str
    entity_id: str | None
    active_section_id: str | None
    message: str | None
    artifacts: list[dict]
    trace_summary: dict
    guardrail_warnings: list[str]
    error: str | None
    s3_prefix: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_entity(cls, run: "AgentRun") -> "AgentRunResponse":
        from civilai_platform.models.entities import AgentRun

        assert isinstance(run, AgentRun)
        return cls(
            run_id=run.run_id,
            tenant_id=run.tenant_id,
            project_id=run.project_id,
            status=run.status.value,
            workflow=run.workflow,
            request=run.request,
            entity_id=run.entity_id,
            active_section_id=run.active_section_id,
            message=run.message,
            artifacts=run.artifacts,
            trace_summary=run.trace_summary,
            guardrail_warnings=run.guardrail_warnings,
            error=run.error,
            s3_prefix=run.s3_prefix,
            created_at=run.created_at,
            updated_at=run.updated_at,
            completed_at=run.completed_at,
        )


class ArtifactPresignRequest(BaseModel):
    filename: str
    content_type: str
    kind: str = Field(description="upload | feasibility_html")


class ArtifactPresignResponse(BaseModel):
    upload_url: str
    s3_key: str
    expires_in: int


MeResponse.model_rebuild()
