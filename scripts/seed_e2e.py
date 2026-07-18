#!/usr/bin/env python3
"""Seed deterministic E2E accounts into a platform file store.

The Playwright harness (civil-ai-fe) starts the platform against a fresh file store, so
there is no pre-existing account for `POST /v1/dev/bootstrap` to attach to. This script
creates those accounts up front. Seeded ``user_id``s are derived from the login email with
the *same* slug rule the FE uses (``devUserIdFromEmail`` in ``src/lib/platform/config.ts``),
so logging in through the UI with ``--email`` resolves to the account seeded here.

Two separate identities, not one user with both roles:

- The tenant admin (``--email``) is a plain member of the seeded tenant. Used by the
  ``/login`` (no tenant slug) flow for workspace/project specs.
- The platform admin (``--platform-admin-email``) is required for anything gated behind
  ``require_platform_admin`` (e.g. ``POST /v1/tenant/llm/invoke`` -- the section-draft LLM
  call). ``ensure_platform_admin_membership`` calls ``purge_non_platform_memberships``,
  which strips any direct membership in the seeded tenant from that user -- giving one user
  both roles breaks the plain ``/login`` flow, because platform-admin session routing
  (``resolvePlatformAdminTargetTenant`` with no explicit tenant slug) sends them to their
  own "platform" home tenant instead. The platform admin must log in via the
  tenant-scoped route (``/fstudio/<slug>/login``), which passes an explicit tenant slug and
  does not require a direct membership row (``dev_bootstrap`` bypasses the "must have a
  membership" check for platform admins).

Usage:
    uv run python scripts/seed_e2e.py --store-path /tmp/e2e-store \
        --email admin@e2e.test --platform-admin-email platform-admin@e2e.test
"""

from __future__ import annotations

import argparse
import re

from civilai_platform.models.api import TenantCreate
from civilai_platform.models.entities import (
    MembershipStatus,
    Role,
    TenantMembership,
    UserProfile,
    utc_now,
)
from civilai_platform.services import platform_tenant as platform_tenant_svc
from civilai_platform.services import tenant as tenant_svc
from civilai_platform.store.file import FileStore


def dev_user_id_from_email(email: str) -> str:
    """Mirror of the FE ``devUserIdFromEmail`` slug rule (config.ts)."""
    normalized = email.strip().lower()
    safe = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:48]
    return f"dev-{safe or 'user'}"


def _put_profile(store: FileStore, *, user_id: str, email: str) -> None:
    now = utc_now()
    local_part = email.split("@", 1)[0].replace(".", " ").replace("_", " ").split()
    first = local_part[0].title() if local_part else "E2E"
    last = " ".join(p.title() for p in local_part[1:]) if len(local_part) > 1 else "Admin"
    store.put_user_profile(
        UserProfile(
            user_id=user_id,
            email=email.strip().lower(),
            first_name=first,
            last_name=last,
            created_at=now,
            updated_at=now,
        )
    )


def seed(
    store_path: str, email: str, tenant_name: str, *, platform_admin_email: str | None = None
) -> tuple[str, str, str]:
    store = FileStore(store_path)
    user_id = dev_user_id_from_email(email)

    tenant = tenant_svc.create_tenant(
        store,
        TenantCreate(name=tenant_name, address="", location="", phone="", fax=""),
    )
    _put_profile(store, user_id=user_id, email=email)
    store.put_membership(
        TenantMembership(
            tenant_id=tenant.tenant_id,
            user_id=user_id,
            role=Role.ADMIN,
            status=MembershipStatus.ACTIVE,
            joined_at=utc_now(),
        )
    )

    if platform_admin_email:
        admin_user_id = dev_user_id_from_email(platform_admin_email)
        _put_profile(store, user_id=admin_user_id, email=platform_admin_email)
        platform_tenant_svc.ensure_platform_admin_membership(store, admin_user_id)

    return user_id, tenant.tenant_id, tenant.url_slug


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-path", required=True, help="FileStore root directory.")
    parser.add_argument("--email", default="admin@e2e.test", help="Tenant admin login email.")
    parser.add_argument("--tenant-name", default="E2E Test Firm")
    parser.add_argument(
        "--platform-admin-email",
        default="platform-admin@e2e.test",
        help="Separate platform-admin identity (required for gated LLM routes). "
        "Pass an empty string to skip seeding it.",
    )
    args = parser.parse_args()

    user_id, tenant_id, slug = seed(
        args.store_path,
        args.email,
        args.tenant_name,
        platform_admin_email=args.platform_admin_email or None,
    )
    print(f"seeded user_id={user_id} tenant_id={tenant_id} slug={slug} email={args.email}")
    if args.platform_admin_email:
        print(f"seeded platform admin email={args.platform_admin_email}")


if __name__ == "__main__":
    main()
