#!/usr/bin/env python3
"""Backfill url_slug for tenants created before slug support."""

from __future__ import annotations

import argparse

from civilai_platform.store import get_store
from civilai_platform.utils.slug import slugify, unique_slug


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill tenant url_slug values")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    args = parser.parse_args()

    store = get_store()
    existing_slugs = set(store.list_tenant_slugs())
    updated = 0

    for tenant in store.list_tenants():
        if tenant.url_slug:
            existing_slugs.add(tenant.url_slug)
            continue
        slug = unique_slug(slugify(tenant.name), existing_slugs)
        existing_slugs.add(slug)
        print(f"{tenant.tenant_id}: {tenant.name!r} -> {slug}")
        if not args.dry_run:
            store.put_tenant(tenant.model_copy(update={"url_slug": slug}))
        updated += 1

    print(f"{'Would update' if args.dry_run else 'Updated'} {updated} tenant(s)")


if __name__ == "__main__":
    main()
