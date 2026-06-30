from civilai_platform.models.api import UserCreate, UserResponse, UserUpdate
from civilai_platform.models.entities import (
    MembershipStatus,
    Role,
    TenantMembership,
    UserProfile,
    new_id,
    utc_now,
)
from civilai_platform.services.audit import record_audit
from civilai_platform.services.cognito import get_cognito_provisioner
from civilai_platform.store.base import PlatformStore


def create_user(
    store: PlatformStore,
    *,
    tenant_id: str,
    actor_user_id: str,
    data: UserCreate,
) -> UserResponse:
    cognito_sub = get_cognito_provisioner().provision_user(
        email=data.email,
        first_name=data.first_name,
        last_name=data.last_name,
        password=data.password,
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
    membership = TenantMembership(
        tenant_id=tenant_id,
        user_id=user_id,
        role=data.role,
        status=MembershipStatus.ACTIVE,
        joined_at=now,
    )
    store.put_user_profile(profile)
    store.put_membership(membership)
    record_audit(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="user.create",
        resource_type="user",
        resource_id=user_id,
    )
    return _to_response(profile, membership)


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
        profile = profile.model_copy(update={"first_name": data.first_name, "updated_at": utc_now()})
    if data.last_name is not None:
        profile = profile.model_copy(update={"last_name": data.last_name, "updated_at": utc_now()})
    if data.phone is not None:
        profile = profile.model_copy(update={"phone": data.phone, "updated_at": utc_now()})
    if data.role is not None:
        membership = membership.model_copy(update={"role": data.role})
    if data.status is not None:
        membership = membership.model_copy(update={"status": data.status})
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
    if not store.get_membership(tenant_id, user_id):
        raise ValueError("User not found")
    store.delete_membership(tenant_id, user_id)
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


def _to_response(profile: UserProfile, membership: TenantMembership) -> UserResponse:
    return UserResponse(
        user_id=profile.user_id,
        email=profile.email,
        first_name=profile.first_name,
        last_name=profile.last_name,
        phone=profile.phone,
        role=membership.role,
        status=membership.status,
        joined_at=membership.joined_at,
    )
