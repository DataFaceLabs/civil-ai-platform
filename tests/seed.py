"""Shared test seed helpers for platform API tests."""

from __future__ import annotations

from civilai_platform.models.api import TenantCreate
from civilai_platform.models.entities import (
    MembershipStatus,
    Role,
    TenantMembership,
    UserProfile,
    utc_now,
)
from civilai_platform.services import tenant as tenant_svc
from civilai_platform.store.base import PlatformStore


def seed_tenant_member(
    store: PlatformStore,
    *,
    user_id: str,
    email: str,
    first_name: str = "Test",
    last_name: str = "User",
    tenant_name: str = "Test Firm",
) -> tuple[str, str]:
    """Create a tenant, user profile, and active admin membership for dev bootstrap tests."""
    tenant = tenant_svc.create_tenant(
        store,
        TenantCreate(name=tenant_name, address="", location="", phone="", fax=""),
    )
    now = utc_now()
    store.put_user_profile(
        UserProfile(
            user_id=user_id,
            email=email,
            first_name=first_name,
            last_name=last_name,
            created_at=now,
            updated_at=now,
        )
    )
    store.put_membership(
        TenantMembership(
            tenant_id=tenant.tenant_id,
            user_id=user_id,
            role=Role.ADMIN,
            status=MembershipStatus.ACTIVE,
            joined_at=now,
        )
    )
    return tenant.tenant_id, tenant.url_slug
