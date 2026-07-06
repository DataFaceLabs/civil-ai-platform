#!/usr/bin/env python3
"""Seed five test companies (five contacts each) with intentional duplicates.

Writes directly to the configured platform store (DynamoDB/file/memory) by default,
so the API server does not need to be running. Use --via-api to seed through HTTP.

Usage:
  cd civil-ai-platform && set -a && . ./.env.local && set +a && \\
    uv run python scripts/seed_test_companies.py

  # Seed into your current FE dev tenant:
  uv run python scripts/seed_test_companies.py \\
    --dev-user-id dev-cruz-lares-29e7e5ff --tenant-id <your-tenant-uuid>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from uuid import uuid4

DEFAULT_API = os.environ.get("CIVILAI_PLATFORM_API", "http://localhost:8001")
DEFAULT_DEV_USER = "dev-client-catalog-seed"


def _c(first: str, last: str, email: str, phone: str) -> dict:
    return {
        "id": str(uuid4()),
        "first_name": first,
        "last_name": last,
        "email": email,
        "phone": phone,
    }


# Five companies × five contacts. Shared names are deliberate.
COMPANIES: list[dict] = [
    {
        "name": "Beard Nursery LLC",
        "address": "20401 Trappers Trail",
        "location": "Manor, Texas 78653",
        "contacts": [
            _c("Jay", "Beard", "jay@beardnursery.test", "512-555-0101"),
            _c("Maria", "Santos", "maria@beardnursery.test", "512-555-0102"),
            _c("Chris", "Johnson", "chris.johnson@beardnursery.test", "512-555-0103"),
            _c("Alex", "Kim", "alex@beardnursery.test", "512-555-0104"),
            _c("Taylor", "Reed", "taylor@beardnursery.test", "512-555-0105"),
        ],
    },
    {
        "name": "Lone Star Civil LLC",
        "address": "1200 Congress Ave",
        "location": "Austin, Texas 78701",
        "contacts": [
            _c("Jordan", "Lee", "jordan.lee@lonestarcivil.test", "512-555-0201"),
            _c("Sam", "Patel", "sam.patel@lonestarcivil.test", "512-555-0202"),
            _c("Riley", "Nguyen", "riley@lonestarcivil.test", "512-555-0203"),
            _c("Morgan", "Davis", "morgan@lonestarcivil.test", "512-555-0204"),
            _c("Casey", "Wright", "casey@lonestarcivil.test", "512-555-0205"),
        ],
    },
    {
        "name": "Acme Development",
        "address": "500 Industrial Blvd",
        "location": "Round Rock, Texas 78664",
        "contacts": [
            _c("Jordan", "Lee", "jordan.lee@acme-roundrock.test", "512-555-0301"),
            _c("Nina", "Brooks", "nina@acme-roundrock.test", "512-555-0302"),
            _c("Evan", "Cole", "evan@acme-roundrock.test", "512-555-0303"),
            _c("Dana", "Price", "dana@acme-roundrock.test", "512-555-0304"),
            _c("Quinn", "Hayes", "quinn@acme-roundrock.test", "512-555-0305"),
        ],
    },
    {
        "name": "Acme Development",
        "address": "900 Warehouse Row",
        "location": "Georgetown, Texas 78626",
        "contacts": [
            _c("Sam", "Patel", "sam.patel@acme-georgetown.test", "512-555-0401"),
            _c("Avery", "Lopez", "avery@acme-georgetown.test", "512-555-0402"),
            _c("Blake", "Turner", "blake@acme-georgetown.test", "512-555-0403"),
            _c("Jamie", "Foster", "jamie@acme-georgetown.test", "512-555-0404"),
            _c("Drew", "Bennett", "drew@acme-georgetown.test", "512-555-0405"),
        ],
    },
    {
        "name": "Hill Country Engineering",
        "address": "88 Ranch Road 12",
        "location": "Dripping Springs, Texas 78620",
        "contacts": [
            _c("Chris", "Johnson", "chris.johnson@hillcountry.test", "512-555-0501"),
            _c("Jordan", "Lee", "jordan.lee@hillcountry.test", "512-555-0502"),
            _c("Parker", "Scott", "parker@hillcountry.test", "512-555-0503"),
            _c("Reese", "Adams", "reese@hillcountry.test", "512-555-0504"),
            _c("Skyler", "Murphy", "skyler@hillcountry.test", "512-555-0505"),
        ],
    },
]

UPSERT_EXTRA_CONTACT = _c(
    "Pat",
    "Morrison",
    "pat.morrison@acme-georgetown.test",
    "512-555-0499",
)


def _print_summary(dev_user_id: str, tenant_id: str, created_ids: list[str], upsert_id: str, upsert_contacts: int) -> None:
    if upsert_id != created_ids[3]:
        print("WARNING: upsert returned a different client_id than the original Georgetown record")
    if upsert_contacts != 6:
        print("WARNING: expected 6 contacts after upsert merge")

    unique_ids = len(set(created_ids))
    print(f"\nSeeded {len(COMPANIES)} companies ({unique_ids} unique client_ids before upsert).")
    print("Duplicate-name contacts to try in the UI Name field:")
    print("  - Jordan Lee (3 companies)")
    print("  - Chris Johnson (2 companies)")
    print("  - Sam Patel (2 companies)")
    print("Duplicate company names (different addresses):")
    print("  - Acme Development @ Round Rock vs Georgetown")
    print("\nTo use in the FE, set localStorage civilai:platformDevUserId to:")
    print(f"  {dev_user_id}")
    print(f"Tenant id: {tenant_id}")
    print("Or pass --tenant-id to seed your current firm instead.")


def _company_to_create(company: dict):
    from civilai_platform.models.api import ClientCreate
    from civilai_platform.models.entities import ClientContact

    return ClientCreate(
        name=company["name"],
        address=company["address"],
        location=company["location"],
        contacts=[ClientContact(**contact) for contact in company["contacts"]],
        notes=[],
    )


def bootstrap_tenant_store(store, dev_user_id: str, firm_name: str) -> str:
    from civilai_platform.models.api import TenantCreate
    from civilai_platform.models.entities import (
        MembershipStatus,
        Role,
        TenantMembership,
        UserProfile,
        utc_now,
    )
    from civilai_platform.services import tenant as tenant_svc

    me = tenant_svc.get_me(store, dev_user_id)
    if me.memberships:
        return me.memberships[0].tenant_id

    now = utc_now()
    email = f"{dev_user_id}@local.dev"
    parts = firm_name.split(" ", 1)
    profile = store.get_user_profile(dev_user_id)
    if not profile:
        store.put_user_profile(
            UserProfile(
                user_id=dev_user_id,
                email=email,
                first_name=parts[0],
                last_name=parts[1] if len(parts) > 1 else "",
                created_at=now,
                updated_at=now,
            )
        )

    tenant = tenant_svc.create_tenant(
        store,
        TenantCreate(name=firm_name, address="", location="", phone="", fax=""),
    )
    store.put_membership(
        TenantMembership(
            tenant_id=tenant.tenant_id,
            user_id=dev_user_id,
            role=Role.ADMIN,
            status=MembershipStatus.ACTIVE,
            joined_at=now,
        )
    )
    store.set_platform_admin(dev_user_id, True)
    return tenant.tenant_id


def seed_via_store(dev_user_id: str, tenant_id: str | None, firm_name: str) -> int:
    from civilai_platform.services import client as client_svc
    from civilai_platform.store import get_store

    store = get_store()
    if not tenant_id:
        print(f"Bootstrapping dev user {dev_user_id!r} in store …")
        tenant_id = bootstrap_tenant_store(store, dev_user_id, firm_name)

    backend = os.environ.get("CIVILAI_STORE_BACKEND", "memory")
    print(f"Tenant: {tenant_id}")
    print(f"Dev user: {dev_user_id}")
    print(f"Store backend: {backend}\n")

    created_ids: list[str] = []
    for company in COMPANIES:
        result = client_svc.create_client(
            store,
            tenant_id=tenant_id,
            actor_user_id=dev_user_id,
            data=_company_to_create(company),
        )
        created_ids.append(result.client_id)
        print(
            f"✓ {company['name']} @ {company['address']} "
            f"→ {result.client_id} ({len(result.contacts)} contacts)"
        )

    georgetown = COMPANIES[3]
    upserted = client_svc.create_client(
        store,
        tenant_id=tenant_id,
        actor_user_id=dev_user_id,
        data=_company_to_create({**georgetown, "contacts": [UPSERT_EXTRA_CONTACT]}),
    )
    print(
        f"\nUpsert check: Acme Development @ Georgetown → {upserted.client_id} "
        f"({len(upserted.contacts)} contacts; expected 6)"
    )
    _print_summary(dev_user_id, tenant_id, created_ids, upserted.client_id, len(upserted.contacts))
    return 0


def _request(
    method: str,
    url: str,
    *,
    dev_user_id: str,
    tenant_id: str | None = None,
    body: dict | None = None,
) -> dict:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Dev-User-Id": dev_user_id,
    }
    if tenant_id:
        headers["X-Tenant-Id"] = tenant_id
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            raw = res.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        raise RuntimeError(f"{method} {url} -> {exc.code}: {detail}") from exc


def bootstrap_api(api_base: str, dev_user_id: str, firm_name: str) -> str:
    me = _request(
        "POST",
        f"{api_base}/v1/dev/bootstrap",
        dev_user_id=dev_user_id,
        body={"name": firm_name, "email": f"{dev_user_id}@local.dev"},
    )
    memberships = me.get("memberships") or []
    if not memberships:
        raise RuntimeError("Bootstrap returned no tenant memberships")
    return memberships[0]["tenant_id"]


def create_client_api(api_base: str, dev_user_id: str, tenant_id: str, company: dict) -> dict:
    return _request(
        "POST",
        f"{api_base}/v1/clients",
        dev_user_id=dev_user_id,
        tenant_id=tenant_id,
        body={
            "name": company["name"],
            "address": company["address"],
            "location": company["location"],
            "contacts": company["contacts"],
            "notes": [],
        },
    )


def seed_via_api(api_base: str, dev_user_id: str, tenant_id: str | None, firm_name: str) -> int:
    if not tenant_id:
        print(f"Bootstrapping dev user {dev_user_id!r} via API …")
        tenant_id = bootstrap_api(api_base, dev_user_id, firm_name)
    print(f"Tenant: {tenant_id}")
    print(f"Dev user: {dev_user_id}")
    print(f"API: {api_base}\n")

    created_ids: list[str] = []
    for company in COMPANIES:
        result = create_client_api(api_base, dev_user_id, tenant_id, company)
        client_id = result["client_id"]
        created_ids.append(client_id)
        print(
            f"✓ {company['name']} @ {company['address']} "
            f"→ {client_id} ({len(result.get('contacts') or [])} contacts)"
        )

    georgetown = COMPANIES[3]
    upsert_body = {
        "name": georgetown["name"],
        "address": georgetown["address"],
        "location": georgetown["location"],
        "contacts": [UPSERT_EXTRA_CONTACT],
        "notes": [],
    }
    upserted = create_client_api(api_base, dev_user_id, tenant_id, upsert_body)
    upsert_id = upserted["client_id"]
    upsert_contacts = len(upserted.get("contacts") or [])
    print(
        f"\nUpsert check: Acme Development @ Georgetown → {upsert_id} "
        f"({upsert_contacts} contacts; expected 6)"
    )
    _print_summary(dev_user_id, tenant_id, created_ids, upsert_id, upsert_contacts)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed test companies and contacts")
    parser.add_argument("--api", default=DEFAULT_API, help="Platform API base URL (--via-api only)")
    parser.add_argument("--dev-user-id", default=DEFAULT_DEV_USER)
    parser.add_argument("--tenant-id", default=None, help="Existing tenant; bootstrap if omitted")
    parser.add_argument("--firm-name", default="Client Catalog Test Firm")
    parser.add_argument("--via-api", action="store_true", help="Seed through HTTP (requires make api)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        payload = {
            "companies": len(COMPANIES),
            "contacts": sum(len(c["contacts"]) for c in COMPANIES),
        }
        print(json.dumps(payload, indent=2))
        return 0

    if args.via_api:
        return seed_via_api(args.api.rstrip("/"), args.dev_user_id, args.tenant_id, args.firm_name)
    return seed_via_store(args.dev_user_id, args.tenant_id, args.firm_name)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as exc:
        print(f"Cannot reach platform API: {exc}", file=sys.stderr)
        print("Omit --via-api to write directly to the store, or start: make api", file=sys.stderr)
        raise SystemExit(1) from exc
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
