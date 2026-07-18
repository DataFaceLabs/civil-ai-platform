from civilai_platform.auth.context import AuthContext
from civilai_platform.auth.jwt import AuthError, parse_bearer_token, validate_cognito_token
from civilai_platform.models.entities import MembershipStatus, Role, TenantStatus, role_at_least
from civilai_platform.services.platform_tenant import is_platform_admin_user
from civilai_platform.settings import get_settings
from civilai_platform.store import get_store
from civilai_platform.store.base import PlatformStore


def assert_tenant_active(store: PlatformStore, tenant_id: str, *, is_platform_admin: bool = False) -> None:
    tenant = store.get_tenant(tenant_id)
    if not tenant:
        raise AuthError("Tenant not found", 404)
    if not is_platform_admin and tenant.status != TenantStatus.ACTIVE:
        raise AuthError("Organization is inactive", 403)


def resolve_auth_context(
    authorization: str | None,
    tenant_header: str | None,
    dev_user_id: str | None = None,
    dev_tenant_id: str | None = None,
) -> AuthContext:
    settings = get_settings()
    store = get_store()

    if settings.dev_auth and dev_user_id:
        profile = store.get_user_profile(dev_user_id)
        email = profile.email if profile else f"{dev_user_id}@dev.local"
        tenant_id = dev_tenant_id or tenant_header
        role: Role | None = None
        is_platform_admin = is_platform_admin_user(store, dev_user_id)
        if tenant_id:
            membership = store.get_membership(tenant_id, dev_user_id)
            if membership and membership.status == MembershipStatus.ACTIVE:
                role = membership.role
            elif is_platform_admin:
                role = Role.PLATFORM_ADMIN
        return AuthContext(
            user_id=dev_user_id,
            email=email,
            tenant_id=tenant_id,
            role=role,
            is_platform_admin=is_platform_admin,
        )

    token = parse_bearer_token(authorization)
    if not token:
        raise AuthError("Missing authorization")
    claims = validate_cognito_token(token)
    user_id = str(claims.get("sub", ""))
    email = str(claims.get("email", ""))
    is_platform_admin = is_platform_admin_user(store, user_id)
    tenant_id = tenant_header or claims.get("custom:tenant_id")
    role = None
    if tenant_id:
        membership = store.get_membership(str(tenant_id), user_id)
        if membership and membership.status == MembershipStatus.ACTIVE:
            role = membership.role
        elif is_platform_admin:
            role = Role.PLATFORM_ADMIN
    return AuthContext(
        user_id=user_id,
        email=email,
        tenant_id=str(tenant_id) if tenant_id else None,
        role=role,
        is_platform_admin=is_platform_admin,
    )


def require_tenant(ctx: AuthContext) -> str:
    if not ctx.tenant_id:
        raise AuthError("X-Tenant-Id header required", 400)
    assert_tenant_active(get_store(), ctx.tenant_id, is_platform_admin=ctx.is_platform_admin)
    return ctx.tenant_id


def require_membership(ctx: AuthContext, minimum: Role = Role.VIEWER) -> None:
    if ctx.is_platform_admin:
        if ctx.tenant_id:
            tenant = get_store().get_tenant(ctx.tenant_id)
            if not tenant:
                raise AuthError("Tenant not found", 404)
        return
    if not ctx.tenant_id or not ctx.role:
        raise AuthError("Forbidden", 403)
    if not role_at_least(ctx.role, minimum):
        raise AuthError("Insufficient role", 403)


def require_platform_admin(ctx: AuthContext) -> None:
    if not ctx.is_platform_admin:
        raise AuthError("Platform admin required", 403)
