from civilai_platform.models.api import MeResponse, TenantMembershipSummary, TenantResponse
from civilai_platform.models.entities import (
    MembershipStatus,
    Tenant,
    TenantStatus,
    UserProfile,
    new_id,
    utc_now,
)
from civilai_platform.models.api import TenantCreate, TenantUpdate
from civilai_platform.services.audit import record_audit
from civilai_platform.store.base import PlatformStore


def create_tenant(store: PlatformStore, data: TenantCreate) -> Tenant:
    now = utc_now()
    tenant = Tenant(
        tenant_id=new_id(),
        name=data.name,
        address=data.address,
        location=data.location,
        phone=data.phone,
        fax=data.fax,
        status=TenantStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    store.put_tenant(tenant)
    return tenant


def update_tenant(store: PlatformStore, tenant_id: str, data: TenantUpdate) -> Tenant:
    tenant = store.get_tenant(tenant_id)
    if not tenant:
        raise ValueError("Tenant not found")
    updates = data.model_dump(exclude_unset=True)
    updated = tenant.model_copy(update={**updates, "updated_at": utc_now()})
    store.put_tenant(updated)
    return updated


def get_me(store: PlatformStore, user_id: str) -> MeResponse:
    profile = store.get_user_profile(user_id)
    if not profile:
        profile = UserProfile(
            user_id=user_id,
            email=f"{user_id}@unknown.local",
            first_name="",
            last_name="",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    memberships = store.list_memberships_for_user(user_id)
    summaries: list[TenantMembershipSummary] = []
    for m in memberships:
        if m.status != MembershipStatus.ACTIVE:
            continue
        tenant = store.get_tenant(m.tenant_id)
        summaries.append(
            TenantMembershipSummary(
                tenant_id=m.tenant_id,
                tenant_name=tenant.name if tenant else m.tenant_id,
                role=m.role,
                status=m.status,
            )
        )
    return MeResponse(
        user_id=profile.user_id,
        email=profile.email,
        first_name=profile.first_name,
        last_name=profile.last_name,
        phone=profile.phone,
        memberships=summaries,
        is_platform_admin=store.is_platform_admin(user_id),
    )


def tenant_to_response(tenant: Tenant) -> TenantResponse:
    return TenantResponse.from_entity(tenant)


def update_me_profile(
    store: PlatformStore,
    user_id: str,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    phone: str | None = None,
) -> MeResponse:
    profile = store.get_user_profile(user_id)
    if not profile:
        raise ValueError("User profile not found")
    updates: dict = {"updated_at": utc_now()}
    if first_name is not None:
        updates["first_name"] = first_name
    if last_name is not None:
        updates["last_name"] = last_name
    if phone is not None:
        updates["phone"] = phone
    store.put_user_profile(profile.model_copy(update=updates))
    return get_me(store, user_id)
