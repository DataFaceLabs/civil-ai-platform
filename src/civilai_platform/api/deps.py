from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from civilai_platform.auth.authz import (
    AuthError,
    require_membership,
    require_platform_admin,
    require_tenant,
    resolve_auth_context,
)
from civilai_platform.auth.context import AuthContext
from civilai_platform.models.entities import Role
from civilai_platform.store import get_store


def _auth_error(exc: AuthError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc))


async def get_auth_context(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
    x_dev_user_id: Annotated[str | None, Header(alias="X-Dev-User-Id")] = None,
    x_dev_tenant_id: Annotated[str | None, Header(alias="X-Dev-Tenant-Id")] = None,
) -> AuthContext:
    try:
        return resolve_auth_context(
            authorization,
            x_tenant_id,
            dev_user_id=x_dev_user_id,
            dev_tenant_id=x_dev_tenant_id,
        )
    except AuthError as exc:
        raise _auth_error(exc) from exc


def tenant_ctx(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
) -> AuthContext:
    require_tenant(ctx)
    require_membership(ctx, Role.VIEWER)
    return ctx


def tenant_admin_ctx(ctx: Annotated[AuthContext, Depends(get_auth_context)]) -> AuthContext:
    require_tenant(ctx)
    require_membership(ctx, Role.ADMIN)
    return ctx


def admin_ctx(ctx: Annotated[AuthContext, Depends(get_auth_context)]) -> AuthContext:
    require_platform_admin(ctx)
    return ctx


def platform_admin_tenant_ctx(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
) -> AuthContext:
    require_platform_admin(ctx)
    require_tenant(ctx)
    return ctx


def get_store_dep():
    return get_store()
