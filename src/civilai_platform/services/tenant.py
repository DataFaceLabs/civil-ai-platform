from civilai_platform.models.api import AdminTenantCreate, TenantCreate, TenantUpdate
from civilai_platform.models.entities import Role, Tenant, TenantStatus, new_id, utc_now
from civilai_platform.services import llm_config as llm_config_svc
from civilai_platform.services.audit import record_audit
from civilai_platform.store.base import PlatformStore
from civilai_platform.utils.slug import slugify, unique_slug


def _resolve_slug(store: PlatformStore, name: str, requested: str | None) -> str:
    base = slugify(requested or name)
    return unique_slug(base, store.list_tenant_slugs())


def create_tenant(store: PlatformStore, data: TenantCreate) -> Tenant:
    now = utc_now()
    url_slug = _resolve_slug(store, data.name, data.url_slug)
    tenant = Tenant(
        tenant_id=new_id(),
        name=data.name,
        url_slug=url_slug,
        address=data.address,
        location=data.location,
        phone=data.phone,
        fax=data.fax,
        status=TenantStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    store.put_tenant(tenant)
    llm_config_svc.copy_baseline_to_tenant(store, tenant.tenant_id)
    return tenant


def create_tenant_with_admin(
    store: PlatformStore,
    data: AdminTenantCreate,
    *,
    actor_user_id: str,
) -> tuple[Tenant, "UserResponse"]:
    from civilai_platform.models.api import UserCreate, UserResponse
    from civilai_platform.models.entities import Role
    from civilai_platform.services import user as user_svc

    tenant = create_tenant(store, data)
    admin = user_svc.create_user(
        store,
        tenant_id=tenant.tenant_id,
        actor_user_id=actor_user_id,
        data=UserCreate(
            email=data.admin_email,
            first_name=data.admin_first_name,
            last_name=data.admin_last_name,
            role=Role.ADMIN,
            invite=True,
        ),
    )
    record_audit(
        tenant_id=tenant.tenant_id,
        actor_user_id=actor_user_id,
        action="tenant.create",
        resource_type="tenant",
        resource_id=tenant.tenant_id,
        detail={"url_slug": tenant.url_slug, "admin_user_id": admin.user_id},
    )
    return tenant, admin


def update_tenant(store: PlatformStore, tenant_id: str, data: TenantUpdate) -> Tenant:
    from civilai_platform.services.platform_tenant import is_platform_tenant_id

    tenant = store.get_tenant(tenant_id)
    if not tenant:
        raise ValueError("Tenant not found")
    updates = data.model_dump(exclude_unset=True)
    if is_platform_tenant_id(store, tenant_id):
        blocked = {"status", "url_slug", "name"}
        if blocked.intersection(updates):
            raise ValueError("The Platform tenant cannot be modified")
    if "url_slug" in updates and updates["url_slug"] is not None:
        slug = slugify(updates["url_slug"])
        existing = store.get_tenant_by_slug(slug)
        if existing and existing.tenant_id != tenant_id:
            raise ValueError("URL slug already in use")
        updates["url_slug"] = slug
    updated = tenant.model_copy(update={**updates, "updated_at": utc_now()})
    store.put_tenant(updated)
    return updated


from civilai_platform.models.api import MeResponse, TenantMembershipSummary, TenantResponse
from civilai_platform.models.entities import MembershipStatus, UserProfile


def get_me(store: PlatformStore, user_id: str) -> MeResponse:
    from civilai_platform.services import platform_tenant as platform_tenant_svc

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
    is_platform_admin = platform_tenant_svc.is_platform_admin_user(store, user_id)
    if is_platform_admin:
        platform_tenant_svc.ensure_platform_admin_membership(store, user_id)

    memberships = store.list_memberships_for_user(user_id)
    summaries: list[TenantMembershipSummary] = []
    for m in memberships:
        if is_platform_admin and not platform_tenant_svc.is_platform_tenant_id(store, m.tenant_id):
            continue
        if m.status != MembershipStatus.ACTIVE:
            continue
        tenant = store.get_tenant(m.tenant_id)
        if not tenant:
            continue
        if not is_platform_admin and tenant.status != TenantStatus.ACTIVE:
            continue
        summaries.append(
            TenantMembershipSummary(
                tenant_id=m.tenant_id,
                tenant_name=tenant.name,
                tenant_slug=tenant.url_slug,
                role=m.role,
                status=m.status,
            )
        )

    summaries.sort(
        key=lambda row: (
            row.tenant_slug != platform_tenant_svc.PLATFORM_TENANT_SLUG,
            row.tenant_name.lower(),
        )
    )
    return MeResponse(
        user_id=profile.user_id,
        email=profile.email,
        first_name=profile.first_name,
        last_name=profile.last_name,
        phone=profile.phone,
        memberships=summaries,
        is_platform_admin=is_platform_admin,
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
