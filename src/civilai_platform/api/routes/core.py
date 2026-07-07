from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from civilai_platform.api.deps import admin_ctx, get_auth_context, get_store_dep, tenant_admin_ctx, tenant_ctx
from civilai_platform.auth.context import AuthContext
from civilai_platform.models.api import MeResponse, MeUpdate, TenantCreate, TenantResponse, TenantUpdate
from civilai_platform.models.entities import Role, TenantMembership, MembershipStatus, UserProfile, TenantStatus, utc_now, new_id
from civilai_platform.services import tenant as tenant_svc
from civilai_platform.services.audit import record_audit, record_audit_for_ctx
from civilai_platform.store.base import PlatformStore

router = APIRouter(tags=["me", "tenant", "admin"])


@router.get("/v1/me", response_model=MeResponse)
def get_me(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> MeResponse:
    return tenant_svc.get_me(store, ctx.user_id)


@router.patch("/v1/me", response_model=MeResponse)
def patch_me(
    body: MeUpdate,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> MeResponse:
    try:
        return tenant_svc.update_me_profile(
            store,
            ctx.user_id,
            first_name=body.first_name,
            last_name=body.last_name,
            phone=body.phone,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/v1/tenant", response_model=TenantResponse)
def get_tenant(
    ctx: Annotated[AuthContext, Depends(tenant_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> TenantResponse:
    tenant_id = ctx.tenant_id
    assert tenant_id
    tenant = store.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    return tenant_svc.tenant_to_response(tenant)


@router.patch("/v1/tenant", response_model=TenantResponse)
def patch_tenant(
    body: TenantUpdate,
    ctx: Annotated[AuthContext, Depends(tenant_admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> TenantResponse:
    tenant_id = ctx.tenant_id
    assert tenant_id
    try:
        updated = tenant_svc.update_tenant(store, tenant_id, body)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    record_audit_for_ctx(
        ctx,
        action="tenant.update",
        resource_type="tenant",
        resource_id=tenant_id,
    )
    return tenant_svc.tenant_to_response(updated)


@router.get("/v1/admin/tenants", response_model=list[TenantResponse])
def list_admin_tenants(
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> list[TenantResponse]:
    _ = ctx
    return [tenant_svc.tenant_to_response(t) for t in store.list_tenants()]


@router.get("/v1/admin/tenants/{tenant_id}", response_model=TenantResponse)
def get_admin_tenant(
    tenant_id: str,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> TenantResponse:
    tenant = store.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    return tenant_svc.tenant_to_response(tenant)


@router.patch("/v1/admin/tenants/{tenant_id}", response_model=TenantResponse)
def patch_admin_tenant(
    tenant_id: str,
    body: TenantUpdate,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> TenantResponse:
    try:
        updated = tenant_svc.update_tenant(store, tenant_id, body)
    except ValueError as exc:
        msg = str(exc)
        if "slug" in msg.lower():
            raise HTTPException(409, msg) from exc
        raise HTTPException(404, msg) from exc
    if body.status == TenantStatus.SUSPENDED:
        record_audit(
            tenant_id=tenant_id,
            actor_user_id=ctx.user_id,
            action="tenant.suspend",
            resource_type="tenant",
            resource_id=tenant_id,
        )
    elif body.status == TenantStatus.ACTIVE:
        record_audit(
            tenant_id=tenant_id,
            actor_user_id=ctx.user_id,
            action="tenant.activate",
            resource_type="tenant",
            resource_id=tenant_id,
        )
    return tenant_svc.tenant_to_response(updated)


@router.delete("/v1/admin/tenants/{tenant_id}", status_code=405)
def delete_admin_tenant(
    tenant_id: str,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> None:
    _ = ctx, store, tenant_id
    raise HTTPException(
        405,
        "Permanent tenant removal requires email authorization. "
        "POST /v1/admin/tenants/{tenant_id}/purge-request then /purge.",
    )


@router.post("/v1/dev/bootstrap", response_model=MeResponse)
def dev_bootstrap(
    body: dict,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> MeResponse:
    """Dev-only: resolve user by email and attach session to an existing membership."""
    from civilai_platform.settings import get_settings
    from civilai_platform.services import platform_tenant as platform_tenant_svc
    from civilai_platform.services import user as user_svc

    if not get_settings().dev_auth:
        raise HTTPException(403, "Dev bootstrap disabled")
    platform_tenant_svc.ensure_platform_tenant(store)
    email = str(body.get("email", f"{ctx.user_id}@local.dev")).strip().lower()
    tenant_slug = str(body.get("tenant_slug", "")).strip()
    now = utc_now()

    existing = user_svc.profile_for_email(store, email)
    user_id = existing.user_id if existing else ctx.user_id
    profile = store.get_user_profile(user_id)
    if not profile:
        local_part = email.split("@", 1)[0].replace(".", " ").replace("_", " ").strip()
        parts = local_part.split()
        first = parts[0].title() if parts else "User"
        last = " ".join(p.title() for p in parts[1:]) if len(parts) > 1 else ""
        profile = UserProfile(
            user_id=user_id,
            email=email,
            first_name=first,
            last_name=last,
            created_at=now,
            updated_at=now,
        )
        store.put_user_profile(profile)
    elif profile.email.strip().lower() != email:
        profile = profile.model_copy(update={"email": email, "updated_at": now})
        store.put_user_profile(profile)

    user_svc.activate_invited_memberships(store, user_id)
    is_platform_admin = platform_tenant_svc.is_platform_admin_user(store, user_id)
    if is_platform_admin:
        platform_tenant_svc.ensure_platform_admin_membership(store, user_id)
    memberships = store.list_memberships_for_user(user_id)

    if tenant_slug:
        tenant = store.get_tenant_by_slug(tenant_slug)
        if not tenant:
            raise HTTPException(404, "Organization not found")
        if tenant.status != TenantStatus.ACTIVE and not is_platform_admin:
            raise HTTPException(404, "Organization not found or inactive")
        if memberships and not any(m.tenant_id == tenant.tenant_id for m in memberships):
            if not is_platform_admin:
                raise HTTPException(
                    403,
                    "Your account is not registered for this organization.",
                )

    if not memberships and not is_platform_admin:
        raise HTTPException(
            403,
            "No account found for this email. Ask your tenant admin to invite you.",
        )
    return tenant_svc.get_me(store, user_id)
