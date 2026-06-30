from datetime import datetime

from pydantic import BaseModel, Field

from civilai_platform.models.entities import (
    Client,
    ClientContact,
    ClientNote,
    ContextDoc,
    FeasibilityDocumentRef,
    FieldValue,
    MembershipStatus,
    Project,
    ProjectState,
    Role,
    Section,
    Tenant,
    TenantMembership,
    TenantStatus,
    UserProfile,
)


class TenantCreate(BaseModel):
    name: str
    address: str = ""
    location: str = ""
    phone: str = ""
    fax: str = ""


class TenantUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    location: str | None = None
    phone: str | None = None
    fax: str | None = None
    status: TenantStatus | None = None
    feature_flags: dict[str, bool] | None = None
    enabled_data_sources: list[str] | None = None


class TenantResponse(BaseModel):
    tenant_id: str
    name: str
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


class UserCreate(BaseModel):
    email: str
    first_name: str
    last_name: str
    phone: str | None = None
    role: Role = Role.ANALYST
    password: str | None = None


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


class TenantMembershipSummary(BaseModel):
    tenant_id: str
    tenant_name: str
    role: Role
    status: MembershipStatus


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
    site_context: dict[str, FieldValue] | None = None
    tcad_prop_id: int | None = None
    client_contacts: list[ClientContact] | None = None
    client_notes: list[ClientNote] | None = None
    references: list[dict] | None = None
    feasibility_document: FeasibilityDocumentRef | None = None


class ProjectStateResponse(BaseModel):
    project_id: str
    tenant_id: str
    sections: list[Section]
    context_docs: list[ContextDoc]
    proposed_use: str | None
    parcel: dict | None
    site_context: dict[str, FieldValue] | None
    tcad_prop_id: int | None
    client_contacts: list[ClientContact]
    client_notes: list[ClientNote]
    references: list[dict]
    feasibility_document: FeasibilityDocumentRef | None
    updated_at: datetime

    @classmethod
    def from_entity(cls, s: ProjectState) -> "ProjectStateResponse":
        return cls(**s.model_dump())


class ArtifactPresignRequest(BaseModel):
    filename: str
    content_type: str
    kind: str = Field(description="upload | feasibility_html")


class ArtifactPresignResponse(BaseModel):
    upload_url: str
    s3_key: str
    expires_in: int


MeResponse.model_rebuild()
