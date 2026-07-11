#!/usr/bin/env python3
"""Seed a deterministic tenant + admin member into a platform file store for E2E tests.

The Playwright harness (civil-ai-fe) starts the platform against a fresh file store, so
there is no pre-existing account for `POST /v1/dev/bootstrap` to attach to. This script
creates that account up front. The seeded ``user_id`` is derived from the login email with
the *same* slug rule the FE uses (``devUserIdFromEmail`` in ``src/lib/platform/config.ts``),
so logging in through the UI with ``--email`` resolves to the membership seeded here.

Usage:
    uv run python scripts/seed_e2e.py --store-path /tmp/e2e-store --email admin@e2e.test
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
from civilai_platform.services import tenant as tenant_svc
from civilai_platform.store.file import FileStore


def dev_user_id_from_email(email: str) -> str:
    """Mirror of the FE ``devUserIdFromEmail`` slug rule (config.ts)."""
    normalized = email.strip().lower()
    safe = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:48]
    return f"dev-{safe or 'user'}"


def seed(store_path: str, email: str, tenant_name: str) -> tuple[str, str, str]:
    store = FileStore(store_path)
    user_id = dev_user_id_from_email(email)

    tenant = tenant_svc.create_tenant(
        store,
        TenantCreate(name=tenant_name, address="", location="", phone="", fax=""),
    )
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
    store.put_membership(
        TenantMembership(
            tenant_id=tenant.tenant_id,
            user_id=user_id,
            role=Role.ADMIN,
            status=MembershipStatus.ACTIVE,
            joined_at=now,
        )
    )
    return user_id, tenant.tenant_id, tenant.url_slug


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-path", required=True, help="FileStore root directory.")
    parser.add_argument("--email", default="admin@e2e.test", help="Login email to seed.")
    parser.add_argument("--tenant-name", default="E2E Test Firm")
    args = parser.parse_args()

    user_id, tenant_id, slug = seed(args.store_path, args.email, args.tenant_name)
    print(f"seeded user_id={user_id} tenant_id={tenant_id} slug={slug} email={args.email}")


if __name__ == "__main__":
    main()
