#!/usr/bin/env python3
"""One-time ops: purge tenants that have zero projects (dev store only).

Skips the reserved Platform tenant. Uses store.purge_tenant_data (memberships,
clients, projects already empty, LLM config, slug, profiles with no remaining
memberships). Does not call Cognito by default.

Usage (from civil-ai-platform):

  set -a && . ./.env.local && set +a
  uv run python scripts/purge_tenants_without_projects.py          # dry-run
  uv run python scripts/purge_tenants_without_projects.py --apply  # delete
"""

from __future__ import annotations

import argparse
import os
import sys

from civilai_platform.services.platform_tenant import is_platform_tenant
from civilai_platform.settings import get_settings
from civilai_platform.store import get_store


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually purge orphan tenants. Without this flag, only lists them.",
    )
    parser.add_argument(
        "--allow-env",
        default="dev",
        help="Required CIVILAI_ENVIRONMENT value (default: dev). Refuse other envs.",
    )
    args = parser.parse_args()

    settings = get_settings()
    if settings.environment != args.allow_env:
        print(
            f"Refusing to run: CIVILAI_ENVIRONMENT={settings.environment!r} "
            f"(expected {args.allow_env!r}). Pass --allow-env only if intentional.",
            file=sys.stderr,
        )
        return 2

    store = get_store()
    tenants = store.list_tenants()
    orphans = []
    kept = 0
    skipped_platform = 0
    for tenant in tenants:
        if is_platform_tenant(tenant):
            skipped_platform += 1
            continue
        projects = store.list_projects(tenant.tenant_id)
        if projects:
            kept += 1
            continue
        orphans.append(tenant)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"[{mode}] store={settings.store_backend} env={settings.environment} "
        f"table={settings.dynamodb_table if settings.store_backend == 'dynamodb' else settings.file_store_path}"
    )
    print(
        f"tenants={len(tenants)} platform_skipped={skipped_platform} "
        f"with_projects={kept} orphans={len(orphans)}"
    )
    for tenant in sorted(orphans, key=lambda t: (t.url_slug or "", t.tenant_id)):
        members = len(store.list_memberships_for_tenant(tenant.tenant_id))
        print(
            f"  {'PURGE' if args.apply else 'WOULD_PURGE'} "
            f"slug={tenant.url_slug!r} name={tenant.name!r} "
            f"id={tenant.tenant_id} members={members}"
        )

    if not args.apply:
        print("Dry-run only. Re-run with --apply to purge.")
        return 0

    purged = 0
    for tenant in orphans:
        user_ids = store.purge_tenant_data(tenant.tenant_id)
        purged += 1
        print(
            f"  purged {tenant.url_slug!r} ({tenant.tenant_id}); "
            f"membership user_ids={len(user_ids)}"
        )

    remaining = store.list_tenants()
    print(f"Done. purged={purged} remaining_tenants={len(remaining)}")
    return 0


if __name__ == "__main__":
    # Allow `uv run python scripts/...` without requiring a prior shell source
    # when the process cwd already has .env.local (pydantic-settings loads it).
    if not os.environ.get("CIVILAI_STORE_BACKEND") and os.path.isfile(".env.local"):
        pass
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
