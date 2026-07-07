"""Reserved Platform tenant for system administrators."""

from civilai_platform.models.entities import (
    MembershipStatus,
    Role,
    Tenant,
    TenantMembership,
    TenantStatus,
    new_id,
    utc_now,
)
from civilai_platform.services import llm_config as llm_config_svc
from civilai_platform.store.base import PlatformStore

PLATFORM_TENANT_SLUG = "platform"
PLATFORM_TENANT_NAME = "Platform"


def get_platform_tenant(store: PlatformStore) -> Tenant | None:
    return store.get_tenant_by_slug(PLATFORM_TENANT_SLUG)


def is_platform_tenant(tenant: Tenant) -> bool:
    return tenant.url_slug == PLATFORM_TENANT_SLUG


def is_platform_tenant_id(store: PlatformStore, tenant_id: str) -> bool:
    tenant = store.get_tenant(tenant_id)
    return tenant is not None and is_platform_tenant(tenant)


def ensure_platform_tenant(store: PlatformStore) -> Tenant:
    existing = get_platform_tenant(store)
    if existing:
        return existing
    now = utc_now()
    tenant = Tenant(
        tenant_id=new_id(),
        name=PLATFORM_TENANT_NAME,
        url_slug=PLATFORM_TENANT_SLUG,
        address="",
        location="",
        phone="",
        fax="",
        status=TenantStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    store.put_tenant(tenant)
    llm_config_svc.copy_baseline_to_tenant(store, tenant.tenant_id)
    return tenant


def is_platform_admin_user(store: PlatformStore, user_id: str) -> bool:
    if store.is_platform_admin(user_id):
        return True
    platform = get_platform_tenant(store)
    if not platform:
        return False
    membership = store.get_membership(platform.tenant_id, user_id)
    return (
        membership is not None
        and membership.role == Role.PLATFORM_ADMIN
        and membership.status in (MembershipStatus.ACTIVE, MembershipStatus.INVITED)
    )


def purge_non_platform_memberships(store: PlatformStore, user_id: str) -> int:
    """Platform admins belong only to the reserved Platform tenant."""
    platform = get_platform_tenant(store)
    if not platform:
        return 0
    removed = 0
    for membership in store.list_memberships_for_user(user_id):
        if membership.tenant_id == platform.tenant_id:
            continue
        store.delete_membership(membership.tenant_id, user_id)
        removed += 1
    return removed


def ensure_platform_admin_membership(store: PlatformStore, user_id: str) -> TenantMembership:
    tenant = ensure_platform_tenant(store)
    existing = store.get_membership(tenant.tenant_id, user_id)
    if existing:
        updates: dict = {}
        if existing.role != Role.PLATFORM_ADMIN:
            updates["role"] = Role.PLATFORM_ADMIN
        if existing.status != MembershipStatus.ACTIVE:
            updates["status"] = MembershipStatus.ACTIVE
        if updates:
            existing = existing.model_copy(update=updates)
            store.put_membership(existing)
        store.set_platform_admin(user_id, True)
        purge_non_platform_memberships(store, user_id)
        return existing
    now = utc_now()
    membership = TenantMembership(
        tenant_id=tenant.tenant_id,
        user_id=user_id,
        role=Role.PLATFORM_ADMIN,
        status=MembershipStatus.ACTIVE,
        joined_at=now,
    )
    store.put_membership(membership)
    store.set_platform_admin(user_id, True)
    purge_non_platform_memberships(store, user_id)
    return membership


def backfill_platform_admin_memberships(store: PlatformStore) -> int:
    ensure_platform_tenant(store)
    count = 0
    for user_id in store.list_platform_admin_user_ids():
        ensure_platform_admin_membership(store, user_id)
        count += 1
    return count
