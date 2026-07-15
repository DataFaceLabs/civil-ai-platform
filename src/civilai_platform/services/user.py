from civilai_platform.models.api import (
    AdminUserRowResponse,
    PlatformAdminCreate,
    PlatformAdminResponse,
    PlatformAdminUpdate,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from civilai_platform.models.entities import (
    MembershipStatus,
    Role,
    TenantMembership,
    UserProfile,
    new_id,
    utc_now,
)
from civilai_platform.services import platform_tenant as platform_tenant_svc
from civilai_platform.services.audit import record_audit
from civilai_platform.services.cognito import CognitoProvisionError, get_cognito_provisioner
from civilai_platform.store.base import PlatformStore


class UserConflictError(ValueError):
    pass


def _assert_single_tenant_membership(store: PlatformStore, user_id: str, tenant_id: str) -> None:
    from civilai_platform.services.platform_tenant import is_platform_tenant_id

    memberships = store.list_memberships_for_user(user_id)
    for m in memberships:
        if m.tenant_id == tenant_id:
            continue
        if is_platform_tenant_id(store, m.tenant_id) or is_platform_tenant_id(store, tenant_id):
            continue
        raise UserConflictError("User already belongs to another tenant")


def create_user(
    store: PlatformStore,
    *,
    tenant_id: str,
    actor_user_id: str,
    data: UserCreate,
) -> UserResponse:
    """Create (or re-invite) a tenant user.

    Re-inviting a previously deleted user must succeed: tenant delete only removes
    membership and disables Cognito, leaving an orphaned profile + Cognito account.
    """
    temporary_password: str | None = None
    existing_profile = _profile_by_email(store, data.email)
    if existing_profile:
        _assert_single_tenant_membership(store, existing_profile.user_id, tenant_id)
        existing_membership = store.get_membership(tenant_id, existing_profile.user_id)
        if existing_membership:
            raise UserConflictError("User already belongs to this tenant")
        user_id = existing_profile.user_id
        now = utc_now()
        profile = existing_profile.model_copy(
            update={
                "first_name": data.first_name,
                "last_name": data.last_name,
                "phone": data.phone,
                "updated_at": now,
            }
        )
        store.put_user_profile(profile)
        if data.invite and not data.password:
            # Cognito account is typically disabled after tenant delete — re-enable
            # and rotate the temporary password so the invite is usable.
            _, temporary_password = get_cognito_provisioner().reinvite_existing_user(
                email=data.email,
                first_name=data.first_name,
                last_name=data.last_name,
                send_email=True,
            )
    else:
        try:
            cognito_sub, temporary_password = get_cognito_provisioner().provision_user(
                email=data.email,
                first_name=data.first_name,
                last_name=data.last_name,
                password=data.password,
                invite=data.invite,
            )
        except CognitoProvisionError as exc:
            raise UserConflictError(str(exc)) from exc
        user_id = cognito_sub or new_id()
        now = utc_now()
        # Re-invite via Cognito UsernameExists returns the existing sub — reuse
        # the orphaned profile when present instead of overwriting created_at.
        existing_by_id = store.get_user_profile(user_id)
        if existing_by_id:
            profile = existing_by_id.model_copy(
                update={
                    "email": data.email,
                    "first_name": data.first_name,
                    "last_name": data.last_name,
                    "phone": data.phone,
                    "updated_at": now,
                }
            )
        else:
            profile = UserProfile(
                user_id=user_id,
                email=data.email,
                first_name=data.first_name,
                last_name=data.last_name,
                phone=data.phone,
                created_at=now,
                updated_at=now,
            )
        store.put_user_profile(profile)

    now = utc_now()
    status = (
        MembershipStatus.INVITED if data.invite and not data.password else MembershipStatus.ACTIVE
    )
    membership = TenantMembership(
        tenant_id=tenant_id,
        user_id=user_id,
        role=data.role,
        status=status,
        joined_at=now,
    )
    store.put_membership(membership)
    record_audit(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="user.create",
        resource_type="user",
        resource_id=user_id,
    )
    return _to_response(profile, membership, temporary_password=temporary_password)


def update_user(
    store: PlatformStore,
    *,
    tenant_id: str,
    user_id: str,
    actor_user_id: str,
    data: UserUpdate,
) -> UserResponse:
    profile = store.get_user_profile(user_id)
    membership = store.get_membership(tenant_id, user_id)
    if not profile or not membership:
        raise ValueError("User not found")
    if data.first_name is not None:
        profile = profile.model_copy(
            update={"first_name": data.first_name, "updated_at": utc_now()}
        )
    if data.last_name is not None:
        profile = profile.model_copy(update={"last_name": data.last_name, "updated_at": utc_now()})
    if data.phone is not None:
        profile = profile.model_copy(update={"phone": data.phone, "updated_at": utc_now()})
    if data.role is not None:
        membership = membership.model_copy(update={"role": data.role})
    if data.status is not None:
        membership = membership.model_copy(update={"status": data.status})
        if data.status == MembershipStatus.DISABLED:
            get_cognito_provisioner().disable_user(email=profile.email)
    store.put_user_profile(profile)
    store.put_membership(membership)
    record_audit(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="user.update",
        resource_type="user",
        resource_id=user_id,
    )
    return _to_response(profile, membership)


def delete_user(
    store: PlatformStore,
    *,
    tenant_id: str,
    user_id: str,
    actor_user_id: str,
) -> None:
    profile = store.get_user_profile(user_id)
    membership = store.get_membership(tenant_id, user_id)
    if not membership:
        raise ValueError("User not found")
    store.delete_membership(tenant_id, user_id)
    if profile:
        get_cognito_provisioner().disable_user(email=profile.email)
    record_audit(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="user.delete",
        resource_type="user",
        resource_id=user_id,
    )


def list_users(store: PlatformStore, tenant_id: str) -> list[UserResponse]:
    memberships = store.list_memberships_for_tenant(tenant_id)
    out: list[UserResponse] = []
    for m in memberships:
        profile = store.get_user_profile(m.user_id)
        if profile:
            out.append(_to_response(profile, m))
    return out


def list_platform_admins(store: PlatformStore) -> list[PlatformAdminResponse]:
    out: list[PlatformAdminResponse] = []
    for user_id in store.list_platform_admin_user_ids():
        profile = store.get_user_profile(user_id)
        if not profile:
            continue
        out.append(
            PlatformAdminResponse(
                user_id=profile.user_id,
                email=profile.email,
                first_name=profile.first_name,
                last_name=profile.last_name,
                phone=profile.phone,
            )
        )
    return out


def list_all_users_for_admin(
    store: PlatformStore,
    *,
    limit: int = 100,
    q: str | None = None,
) -> tuple[list[AdminUserRowResponse], int]:
    out: list[AdminUserRowResponse] = []
    seen: set[tuple[str, str]] = set()

    for tenant in store.list_tenants():
        for membership in store.list_memberships_for_tenant(tenant.tenant_id):
            key = (tenant.tenant_id, membership.user_id)
            if key in seen:
                continue
            seen.add(key)
            profile = store.get_user_profile(membership.user_id)
            if not profile:
                continue
            out.append(
                AdminUserRowResponse(
                    user_id=profile.user_id,
                    email=profile.email,
                    first_name=profile.first_name,
                    last_name=profile.last_name,
                    phone=profile.phone,
                    role=membership.role,
                    status=membership.status,
                    tenant_id=tenant.tenant_id,
                    tenant_name=tenant.name,
                    tenant_slug=tenant.url_slug,
                    is_platform_admin=store.is_platform_admin(profile.user_id),
                    joined_at=membership.joined_at,
                )
            )

    platform_tenant = platform_tenant_svc.get_platform_tenant(store)
    for user_id in store.list_platform_admin_user_ids():
        profile = store.get_user_profile(user_id)
        if not profile:
            continue
        tenant_id = platform_tenant.tenant_id if platform_tenant else "platform"
        if any(row.user_id == user_id and row.tenant_id == tenant_id for row in out):
            continue
        memberships = store.list_memberships_for_user(user_id)
        membership = next((m for m in memberships if m.tenant_id == tenant_id), None)
        out.append(
            AdminUserRowResponse(
                user_id=profile.user_id,
                email=profile.email,
                first_name=profile.first_name,
                last_name=profile.last_name,
                phone=profile.phone,
                role=membership.role if membership else Role.PLATFORM_ADMIN,
                status=membership.status if membership else MembershipStatus.ACTIVE,
                tenant_id=tenant_id,
                tenant_name=platform_tenant.name
                if platform_tenant
                else platform_tenant_svc.PLATFORM_TENANT_NAME,
                tenant_slug=platform_tenant.url_slug
                if platform_tenant
                else platform_tenant_svc.PLATFORM_TENANT_SLUG,
                is_platform_admin=True,
                joined_at=membership.joined_at if membership else profile.created_at,
            )
        )

    out.sort(key=lambda row: row.joined_at, reverse=True)

    if q:
        needle = q.strip().lower()
        if needle:
            out = [
                row
                for row in out
                if needle in row.tenant_name.lower()
                or needle in row.tenant_slug.lower()
                or needle in row.email.lower()
                or needle in f"{row.first_name} {row.last_name}".strip().lower()
            ]

    total = len(out)
    return out[:limit], total


def create_platform_admin(
    store: PlatformStore,
    *,
    actor_user_id: str,
    data: PlatformAdminCreate,
) -> PlatformAdminResponse:
    temporary_password: str | None = None
    existing = _profile_by_email(store, data.email)
    if existing:
        user_id = existing.user_id
        profile = existing
    else:
        cognito_sub, temporary_password = get_cognito_provisioner().provision_user(
            email=data.email,
            first_name=data.first_name,
            last_name=data.last_name,
            password=data.password,
            invite=data.invite,
        )
        user_id = cognito_sub or new_id()
        now = utc_now()
        profile = UserProfile(
            user_id=user_id,
            email=data.email,
            first_name=data.first_name,
            last_name=data.last_name,
            phone=data.phone,
            created_at=now,
            updated_at=now,
        )
        store.put_user_profile(profile)
    store.set_platform_admin(user_id, True)
    platform_tenant_svc.ensure_platform_admin_membership(store, user_id)
    if data.invite and not data.password:
        platform = platform_tenant_svc.get_platform_tenant(store)
        if platform:
            current = store.get_membership(platform.tenant_id, user_id)
            if current and current.status == MembershipStatus.ACTIVE:
                store.put_membership(
                    current.model_copy(update={"status": MembershipStatus.INVITED})
                )
    record_audit(
        tenant_id="platform",
        actor_user_id=actor_user_id,
        action="platform_admin.create",
        resource_type="user",
        resource_id=user_id,
    )
    return PlatformAdminResponse(
        user_id=profile.user_id,
        email=profile.email,
        first_name=profile.first_name,
        last_name=profile.last_name,
        phone=profile.phone,
        temporary_password=temporary_password,
    )


def update_platform_admin(
    store: PlatformStore,
    *,
    user_id: str,
    actor_user_id: str,
    data: PlatformAdminUpdate,
) -> PlatformAdminResponse:
    if not store.is_platform_admin(user_id):
        raise ValueError("User is not a platform admin")
    profile = store.get_user_profile(user_id)
    if not profile:
        raise ValueError("User not found")
    updates: dict = {"updated_at": utc_now()}
    if data.first_name is not None:
        updates["first_name"] = data.first_name
    if data.last_name is not None:
        updates["last_name"] = data.last_name
    if data.phone is not None:
        updates["phone"] = data.phone
    if data.email is not None:
        updates["email"] = data.email
    profile = profile.model_copy(update=updates)
    store.put_user_profile(profile)
    record_audit(
        tenant_id="platform",
        actor_user_id=actor_user_id,
        action="platform_admin.update",
        resource_type="user",
        resource_id=user_id,
    )
    return PlatformAdminResponse(
        user_id=profile.user_id,
        email=profile.email,
        first_name=profile.first_name,
        last_name=profile.last_name,
        phone=profile.phone,
    )


def invalidate_platform_admin_invite(
    store: PlatformStore,
    *,
    user_id: str,
    actor_user_id: str,
) -> None:
    if not store.is_platform_admin(user_id):
        raise ValueError("User is not a platform admin")
    platform = platform_tenant_svc.get_platform_tenant(store)
    if not platform:
        raise ValueError("Platform tenant not configured")
    membership = store.get_membership(platform.tenant_id, user_id)
    if not membership or membership.status != MembershipStatus.INVITED:
        raise ValueError("User does not have a pending invite")
    profile = store.get_user_profile(user_id)
    store.put_membership(membership.model_copy(update={"status": MembershipStatus.DISABLED}))
    store.set_platform_admin(user_id, False)
    if profile:
        get_cognito_provisioner().disable_user(email=profile.email)
    record_audit(
        tenant_id="platform",
        actor_user_id=actor_user_id,
        action="platform_admin.invalidate_invite",
        resource_type="user",
        resource_id=user_id,
    )


def delete_platform_admin(
    store: PlatformStore,
    *,
    user_id: str,
    actor_user_id: str,
) -> None:
    """Remove a platform admin, including disabled former admins after invite invalidate.

    Invalidate clears the platform-admin flag but leaves a DISABLED platform membership.
    Delete must still clean that up so Admin UI can remove orphaned rows.
    """
    platform = platform_tenant_svc.get_platform_tenant(store)
    membership = store.get_membership(platform.tenant_id, user_id) if platform else None
    is_admin = store.is_platform_admin(user_id)
    is_disabled_former = bool(membership and membership.status == MembershipStatus.DISABLED)
    if not is_admin and not is_disabled_former:
        return
    store.set_platform_admin(user_id, False)
    profile = store.get_user_profile(user_id)
    if platform:
        store.delete_membership(platform.tenant_id, user_id)
    remaining = store.list_memberships_for_user(user_id)
    if profile:
        if not remaining:
            store.delete_user_profile(user_id)
            get_cognito_provisioner().delete_user(email=profile.email)
        else:
            get_cognito_provisioner().disable_user(email=profile.email)
    record_audit(
        tenant_id="platform",
        actor_user_id=actor_user_id,
        action="platform_admin.delete",
        resource_type="user",
        resource_id=user_id,
    )


def profile_for_email(store: PlatformStore, email: str) -> UserProfile | None:
    return _profile_by_email(store, email)


def is_dev_user_id(user_id: str) -> bool:
    return user_id.startswith("dev-")


def activate_invited_memberships(store: PlatformStore, user_id: str) -> None:
    """Mark invited memberships active after a successful Cognito-authenticated session.

    Invite creates Cognito users in FORCE_CHANGE_PASSWORD and platform memberships as
    INVITED. After the user signs in (and changes their temp password), /v1/me must
    activate those memberships or the user appears to have no tenants.
    """
    for membership in store.list_memberships_for_user(user_id):
        if membership.status != MembershipStatus.INVITED:
            continue
        store.put_membership(membership.model_copy(update={"status": MembershipStatus.ACTIVE}))


def _profile_by_email(store: PlatformStore, email: str) -> UserProfile | None:
    """Resolve a profile by email, including orphaned (no-membership) users.

    Membership-only lookup misses users deleted from a tenant: delete removes the
    membership and disables Cognito but leaves the profile. Fall back to Cognito
    ``sub`` → profile PK when the membership scan finds nothing.
    """
    normalized = email.strip().lower()
    matches: list[UserProfile] = []
    seen: set[str] = set()
    for tenant in store.list_tenants():
        for m in store.list_memberships_for_tenant(tenant.tenant_id):
            if m.user_id in seen:
                continue
            seen.add(m.user_id)
            profile = store.get_user_profile(m.user_id)
            if profile and profile.email.strip().lower() == normalized:
                matches.append(profile)
    for user_id in store.list_platform_admin_user_ids():
        if user_id in seen:
            continue
        profile = store.get_user_profile(user_id)
        if profile and profile.email.strip().lower() == normalized:
            matches.append(profile)
    if matches:
        if len(matches) == 1:
            return matches[0]
        canonical = [p for p in matches if not is_dev_user_id(p.user_id)]
        return canonical[0] if canonical else matches[0]

    cognito_sub = get_cognito_provisioner().get_user_sub(email.strip())
    if not cognito_sub or cognito_sub in seen:
        return None
    orphaned = store.get_user_profile(cognito_sub)
    if orphaned and orphaned.email.strip().lower() == normalized:
        return orphaned
    return None


def _to_response(
    profile: UserProfile,
    membership: TenantMembership,
    *,
    temporary_password: str | None = None,
) -> UserResponse:
    return UserResponse(
        user_id=profile.user_id,
        email=profile.email,
        first_name=profile.first_name,
        last_name=profile.last_name,
        phone=profile.phone,
        role=membership.role,
        status=membership.status,
        joined_at=membership.joined_at,
        temporary_password=temporary_password,
    )
