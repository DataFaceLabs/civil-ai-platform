from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from civilai_platform.api.deps import get_store_dep, tenant_ctx
from civilai_platform.auth.context import AuthContext
from civilai_platform.models.api import UserCreate, UserResponse, UserUpdate
from civilai_platform.models.entities import Role
from civilai_platform.services import user as user_svc
from civilai_platform.store.base import PlatformStore

router = APIRouter(prefix="/v1/users", tags=["users"])


def _admin_tenant_ctx(ctx: Annotated[AuthContext, Depends(tenant_ctx)]) -> AuthContext:
    from civilai_platform.auth.authz import require_membership

    require_membership(ctx, Role.ADMIN)
    return ctx


@router.get("", response_model=list[UserResponse])
def list_users(
    ctx: Annotated[AuthContext, Depends(_admin_tenant_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> list[UserResponse]:
    assert ctx.tenant_id
    return user_svc.list_users(store, ctx.tenant_id)


@router.post("", response_model=UserResponse, status_code=201)
def create_user(
    body: UserCreate,
    ctx: Annotated[AuthContext, Depends(_admin_tenant_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> UserResponse:
    assert ctx.tenant_id
    return user_svc.create_user(
        store,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        data=body,
    )


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    body: UserUpdate,
    ctx: Annotated[AuthContext, Depends(_admin_tenant_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> UserResponse:
    assert ctx.tenant_id
    try:
        return user_svc.update_user(
            store,
            tenant_id=ctx.tenant_id,
            user_id=user_id,
            actor_user_id=ctx.user_id,
            data=body,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: str,
    ctx: Annotated[AuthContext, Depends(_admin_tenant_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> None:
    assert ctx.tenant_id
    try:
        user_svc.delete_user(
            store,
            tenant_id=ctx.tenant_id,
            user_id=user_id,
            actor_user_id=ctx.user_id,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
