#!/usr/bin/env python3
"""Ensure Platform tenant exists and attach all platform admins to it."""

from __future__ import annotations

import os
import sys

from civilai_platform.services.platform_tenant import (
    PLATFORM_TENANT_NAME,
    PLATFORM_TENANT_SLUG,
    backfill_platform_admin_memberships,
    ensure_platform_tenant,
)
from civilai_platform.store import get_store


def main() -> int:
    if os.path.isfile(".env.local"):
        # shell-friendly when run via: set -a && . ./.env.local && set +a
        pass
    store = get_store()
    tenant = ensure_platform_tenant(store)
    count = backfill_platform_admin_memberships(store)
    print(f"Platform tenant ready: {tenant.name} ({PLATFORM_TENANT_SLUG}) id={tenant.tenant_id}")
    print(f"Backfilled {count} platform admin membership(s)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
