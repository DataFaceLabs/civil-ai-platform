from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from civilai_platform.api.deps import admin_ctx, get_store_dep
from civilai_platform.auth.context import AuthContext
from civilai_platform.models.api import (
    AdminTenantCreate,
    AdminUserListResponse,
    AdminUserRowResponse,
    PlatformAdminCreate,
    PlatformAdminResponse,
    PlatformAdminUpdate,
    TenantPurgeConfirm,
    TenantPurgeRequestResponse,
    TenantResponse,
    UserCreate,
    UserResponse,
)
from civilai_platform.models.entities import Role
from civilai_platform.services import tenant as tenant_svc
from civilai_platform.services import tenant_purge as tenant_purge_svc
from civilai_platform.services import user as user_svc
from civilai_platform.services.audit import record_audit
from civilai_platform.store.base import PlatformStore

router = APIRouter(prefix="/v1/admin", tags=["admin"])


class AdminTenantCreateResponse(BaseModel):
    tenant: TenantResponse
    admin: UserResponse


@router.post("/tenants", response_model=AdminTenantCreateResponse, status_code=201)
def create_admin_tenant(
    body: AdminTenantCreate,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> AdminTenantCreateResponse:
    try:
        tenant, admin = tenant_svc.create_tenant_with_admin(
            store,
            body,
            actor_user_id=ctx.user_id,
        )
    except user_svc.UserConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    return AdminTenantCreateResponse(
        tenant=tenant_svc.tenant_to_response(tenant),
        admin=admin,
    )


@router.post("/tenants/{tenant_id}/invite-admin", response_model=UserResponse, status_code=201)
def invite_tenant_admin(
    tenant_id: str,
    body: UserCreate,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> UserResponse:
    if not store.get_tenant(tenant_id):
        raise HTTPException(404, "Tenant not found")
    payload = body.model_copy(update={"role": Role.ADMIN, "invite": True})
    try:
        return user_svc.create_user(
            store,
            tenant_id=tenant_id,
            actor_user_id=ctx.user_id,
            data=payload,
        )
    except user_svc.UserConflictError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/tenants/{tenant_id}/purge-request", response_model=TenantPurgeRequestResponse)
def request_tenant_purge(
    tenant_id: str,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> TenantPurgeRequestResponse:
    try:
        result = tenant_purge_svc.request_tenant_purge(
            store,
            tenant_id=tenant_id,
            actor_user_id=ctx.user_id,
            actor_email=ctx.email,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return TenantPurgeRequestResponse(**result)


@router.post("/tenants/{tenant_id}/purge", status_code=204)
def confirm_tenant_purge(
    tenant_id: str,
    body: TenantPurgeConfirm,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> None:
    try:
        user_ids = tenant_purge_svc.confirm_tenant_purge(
            store,
            tenant_id=tenant_id,
            actor_user_id=ctx.user_id,
            actor_email=body.confirmation_email,
            authorization_code=body.authorization_code,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    record_audit(
        tenant_id="platform",
        actor_user_id=ctx.user_id,
        action="tenant.purge",
        resource_type="tenant",
        resource_id=tenant_id,
        detail={"deleted_user_ids": user_ids},
    )


@router.get("/platform-admins", response_model=list[PlatformAdminResponse])
def list_platform_admins(
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> list[PlatformAdminResponse]:
    _ = ctx
    return user_svc.list_platform_admins(store)


@router.get("/users", response_model=AdminUserListResponse)
def list_all_users(
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> AdminUserListResponse:
    _ = ctx
    users, total = user_svc.list_all_users_for_admin(store, limit=limit, q=q)
    return AdminUserListResponse(users=users, total=total, limit=limit)


@router.post("/platform-admins", response_model=PlatformAdminResponse, status_code=201)
def create_platform_admin(
    body: PlatformAdminCreate,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> PlatformAdminResponse:
    try:
        return user_svc.create_platform_admin(
            store,
            actor_user_id=ctx.user_id,
            data=body,
        )
    except user_svc.UserConflictError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.patch("/platform-admins/{user_id}", response_model=PlatformAdminResponse)
def update_platform_admin(
    user_id: str,
    body: PlatformAdminUpdate,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> PlatformAdminResponse:
    try:
        return user_svc.update_platform_admin(
            store,
            user_id=user_id,
            actor_user_id=ctx.user_id,
            data=body,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/platform-admins/{user_id}", status_code=204)
def grant_platform_admin(
    user_id: str,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> None:
    if not store.get_user_profile(user_id):
        raise HTTPException(404, "User not found")
    store.set_platform_admin(user_id, True)
    from civilai_platform.services import platform_tenant as platform_tenant_svc

    platform_tenant_svc.ensure_platform_admin_membership(store, user_id)
    record_audit(
        tenant_id=ctx.tenant_id or "platform",
        actor_user_id=ctx.user_id,
        action="platform_admin.grant",
        resource_type="user",
        resource_id=user_id,
    )


@router.delete("/platform-admins/{user_id}", status_code=204)
def delete_platform_admin(
    user_id: str,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> None:
    user_svc.delete_platform_admin(
        store,
        user_id=user_id,
        actor_user_id=ctx.user_id,
    )


@router.post("/platform-admins/{user_id}/invalidate-invite", status_code=204)
def invalidate_platform_admin_invite(
    user_id: str,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> None:
    try:
        user_svc.invalidate_platform_admin_invite(
            store,
            user_id=user_id,
            actor_user_id=ctx.user_id,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
