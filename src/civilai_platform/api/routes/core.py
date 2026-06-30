from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from civilai_platform.api.deps import admin_ctx, get_auth_context, get_store_dep, tenant_admin_ctx, tenant_ctx
from civilai_platform.auth.context import AuthContext
from civilai_platform.models.api import MeResponse, MeUpdate, TenantCreate, TenantResponse, TenantUpdate
from civilai_platform.models.entities import Role, TenantMembership, MembershipStatus, UserProfile, utc_now, new_id
from civilai_platform.services import tenant as tenant_svc
from civilai_platform.services.audit import record_audit
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
    record_audit(
        tenant_id=tenant_id,
        actor_user_id=ctx.user_id,
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
    return [tenant_svc.tenant_to_response(t) for t in store.list_tenants()]


@router.post("/v1/admin/tenants", response_model=TenantResponse, status_code=201)
def create_admin_tenant(
    body: TenantCreate,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> TenantResponse:
    tenant = tenant_svc.create_tenant(store, body)
    record_audit(
        tenant_id=tenant.tenant_id,
        actor_user_id=ctx.user_id,
        action="tenant.create",
        resource_type="tenant",
        resource_id=tenant.tenant_id,
    )
    return tenant_svc.tenant_to_response(tenant)


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
        raise HTTPException(404, str(exc)) from exc
    return tenant_svc.tenant_to_response(updated)


@router.delete("/v1/admin/tenants/{tenant_id}", status_code=204)
def delete_admin_tenant(
    tenant_id: str,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> None:
    if not store.get_tenant(tenant_id):
        raise HTTPException(404, "Tenant not found")
    store.delete_tenant(tenant_id)


@router.post("/v1/dev/bootstrap", response_model=MeResponse)
def dev_bootstrap(
    body: dict,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> MeResponse:
    """Dev-only: create tenant + admin membership for first-time local login."""
    from civilai_platform.settings import get_settings

    if not get_settings().dev_auth:
        raise HTTPException(403, "Dev bootstrap disabled")
    name = str(body.get("name", "My Firm")).strip() or "My Firm"
    email = str(body.get("email", f"{ctx.user_id}@local.dev"))
    parts = name.split(" ", 1)
    first = parts[0]
    last = parts[1] if len(parts) > 1 else ""
    now = utc_now()
    profile = store.get_user_profile(ctx.user_id)
    if not profile:
        profile = UserProfile(
            user_id=ctx.user_id,
            email=email,
            first_name=first,
            last_name=last,
            created_at=now,
            updated_at=now,
        )
        store.put_user_profile(profile)
    memberships = store.list_memberships_for_user(ctx.user_id)
    if not memberships:
        tenant = tenant_svc.create_tenant(
            store,
            TenantCreate(name=name, address="", location="", phone="", fax=""),
        )
        store.put_membership(
            TenantMembership(
                tenant_id=tenant.tenant_id,
                user_id=ctx.user_id,
                role=Role.ADMIN,
                status=MembershipStatus.ACTIVE,
                joined_at=now,
            )
        )
        store.set_platform_admin(ctx.user_id, True)
        record_audit(
            tenant_id=tenant.tenant_id,
            actor_user_id=ctx.user_id,
            action="tenant.create",
            resource_type="tenant",
            resource_id=tenant.tenant_id,
        )
    return tenant_svc.get_me(store, ctx.user_id)
