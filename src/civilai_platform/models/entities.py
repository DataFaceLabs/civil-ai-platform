from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class Role(StrEnum):
    PLATFORM_ADMIN = "PlatformAdmin"
    ADMIN = "Admin"
    ANALYST = "Analyst"
    REVIEWER = "Reviewer"
    VIEWER = "Viewer"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    DISABLED = "disabled"


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class AgentRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LlmInvokeJobStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


ROLE_RANK: dict[Role, int] = {
    Role.PLATFORM_ADMIN: 100,
    Role.ADMIN: 80,
    Role.ANALYST: 60,
    Role.REVIEWER: 40,
    Role.VIEWER: 20,
}


def role_at_least(actual: Role, minimum: Role) -> bool:
    return ROLE_RANK[actual] >= ROLE_RANK[minimum]


class Tenant(BaseModel):
    tenant_id: str
    name: str
    url_slug: str
    address: str = ""
    location: str = ""
    phone: str = ""
    fax: str = ""
    logo_s3_key: str | None = None
    status: TenantStatus = TenantStatus.ACTIVE
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    enabled_data_sources: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class LlmBaselineTemplate(BaseModel):
    version: int
    config: dict[str, Any]
    updated_at: datetime
    updated_by_user_id: str | None = None


class TenantLlmConfig(BaseModel):
    tenant_id: str
    baseline_version_at_copy: int
    config: dict[str, Any]
    updated_at: datetime


class UserProfile(BaseModel):
    user_id: str
    email: str
    first_name: str
    last_name: str
    phone: str | None = None
    created_at: datetime
    updated_at: datetime


class TenantMembership(BaseModel):
    tenant_id: str
    user_id: str
    role: Role
    status: MembershipStatus = MembershipStatus.ACTIVE
    joined_at: datetime


class ClientContact(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: str
    phone: str
    phone2: str | None = None
    fax: str | None = None


class ClientNote(BaseModel):
    id: str
    text: str
    created_at: str
    author_name: str


class Client(BaseModel):
    client_id: str
    tenant_id: str
    name: str
    address: str = ""
    location: str = ""
    contacts: list[ClientContact] = Field(default_factory=list)
    notes: list[ClientNote] = Field(default_factory=list)
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime


class Project(BaseModel):
    project_id: str
    tenant_id: str
    name: str
    address: str
    jurisdiction: str
    owner_user_id: str
    client_id: str | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    created_at: datetime
    updated_at: datetime


class FieldProvenance(BaseModel):
    source: str
    source_id: str | None = None
    citation: str | None = None
    retrieved_at: str | None = None


class FieldSourceLink(BaseModel):
    name: str
    description: str
    href: str | None = None
    source_type: str
    source_id: str | None = None


class FieldCodeSemantic(BaseModel):
    code: str
    ui_label: str
    ui_detail: str
    # Data API uses vocabulary confidence labels (e.g. bootstrap, pending), not only floats.
    confidence: str | float
    external_sources: list[FieldSourceLink] = Field(default_factory=list)


class FieldCandidate(BaseModel):
    value: Any | None = None
    label: str | None = None


class FieldValue(BaseModel):
    value: str = ""
    status: str = "empty"
    data_status: str | None = None
    system_populated: bool | None = None
    provenance: list[FieldProvenance] = Field(default_factory=list)
    candidates: list[FieldCandidate] = Field(default_factory=list)
    source_links: list[FieldSourceLink] = Field(default_factory=list)
    code_semantics: list[FieldCodeSemantic] = Field(default_factory=list)


class Section(BaseModel):
    id: str
    title: str
    body: str = ""
    history: list[str] = Field(default_factory=list)
    step_key: str
    status: str = "draft"
    approved_at: str | None = None
    fields: dict[str, FieldValue] = Field(default_factory=dict)


class ContextDoc(BaseModel):
    id: str
    name: str
    size: int
    s3_key: str | None = None


class MapExhibit(BaseModel):
    id: str
    # Legacy fixed-slot identifier. User-named exhibits created by the current FE
    # omit it, so it must be optional or state saves that include a new exhibit fail.
    slot: str | None = None
    name: str
    size: int
    mime_type: str | None = None
    s3_key: str | None = None
    # Persisted preview thumbnail (data URL) generated client-side from the uploaded
    # file, so the exhibit grid can render without re-fetching the artifact each load.
    thumbnail_data_url: str | None = None


class FeasibilityDocumentRef(BaseModel):
    status: str
    saved_at: str
    source_fingerprint: str
    html_s3_key: str | None = None


class VerificationStep(BaseModel):
    id: str
    text: str
    checked: bool = False
    step_key: str


class ProjectState(BaseModel):
    project_id: str
    tenant_id: str
    sections: list[Section] = Field(default_factory=list)
    context_docs: list[ContextDoc] = Field(default_factory=list)
    map_exhibits: list[MapExhibit] = Field(default_factory=list)
    proposed_use: str | None = None
    parcel: dict[str, Any] | None = None
    site_payload: dict[str, Any] | None = None
    site_context: dict[str, FieldValue] | None = None
    tcad_prop_id: int | None = None
    client_contacts: list[ClientContact] = Field(default_factory=list)
    client_notes: list[ClientNote] = Field(default_factory=list)
    references: list[dict[str, Any]] = Field(default_factory=list)
    feasibility_document: FeasibilityDocumentRef | None = None
    verification_steps: list[VerificationStep] = Field(default_factory=list)
    updated_at: datetime


class AuditEvent(BaseModel):
    event_id: str
    tenant_id: str
    actor_user_id: str
    action: str
    resource_type: str
    resource_id: str
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ProjectActivity(BaseModel):
    event_id: str
    tenant_id: str
    project_id: str
    actor_user_id: str
    actor_name: str
    event_type: str
    section_id: str | None = None
    content: str
    mentions: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AgentRun(BaseModel):
    run_id: str
    tenant_id: str
    project_id: str
    actor_user_id: str
    status: AgentRunStatus = AgentRunStatus.QUEUED
    workflow: str | None = None
    request: str
    entity_id: str | None = None
    active_section_id: str | None = None
    message: str | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    trace_summary: dict[str, Any] = Field(default_factory=dict)
    guardrail_warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    s3_prefix: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class LlmInvokeJob(BaseModel):
    """Async tenant LLM invoke (API Gateway ~29s cap — draft assembly routinely exceeds it)."""

    job_id: str
    tenant_id: str
    actor_user_id: str
    step_key: str
    status: LlmInvokeJobStatus = LlmInvokeJobStatus.RUNNING
    # Request fields needed to re-run invoke_tenant_section_llm in the worker.
    user_prompt: str
    field_context: dict[str, str] = Field(default_factory=dict)
    search_context_hint: str = ""
    invoke_mode: str = "section"
    web_search_enabled: bool | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
