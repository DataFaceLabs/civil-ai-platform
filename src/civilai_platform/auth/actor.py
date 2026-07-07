"""Tenant-scoped actor identity for platform administrators."""

from civilai_platform.auth.context import AuthContext
from civilai_platform.services.platform_tenant import is_platform_admin_user, is_platform_tenant_id
from civilai_platform.store.base import PlatformStore

PLATFORM_ACTING_ACTOR_ID = "platform-admin"
PLATFORM_ACTING_ACTOR_LABEL = "Platform Admin"


def is_acting_on_tenant(store: PlatformStore, ctx: AuthContext) -> bool:
    return bool(
        ctx.is_platform_admin
        and ctx.tenant_id
        and not is_platform_tenant_id(store, ctx.tenant_id)
    )


def tenant_actor_user_id(store: PlatformStore, ctx: AuthContext) -> str:
    if is_acting_on_tenant(store, ctx):
        return PLATFORM_ACTING_ACTOR_ID
    return ctx.user_id


def tenant_audit_detail(
    store: PlatformStore,
    ctx: AuthContext,
    detail: dict | None = None,
) -> dict:
    payload = dict(detail or {})
    if is_acting_on_tenant(store, ctx):
        payload["actor_display_name"] = PLATFORM_ACTING_ACTOR_LABEL
        payload["acting_platform_admin_user_id"] = ctx.user_id
    return payload
