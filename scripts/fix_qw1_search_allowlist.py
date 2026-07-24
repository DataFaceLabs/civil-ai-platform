#!/usr/bin/env python3
"""Ops: replace open-web ``*.*`` search allowlists with Kyle's curated domains (QW1).

Updates:
  1. Platform LLM baseline ``webSearch.allowedDomains``
  2. Every tenant LLM config that still lists ``*.*`` (or ``--slugs`` only)

Surgical: only rewrites ``webSearch.allowedDomains`` (+ bumps baseline version).
Does **not** restore full baseline (preserves per-tenant prompt / section edits).

Usage (from civil-ai-platform):

  set -a && . ./.env.local && set +a   # optional; env vars below override
  export CIVILAI_STORE_BACKEND=dynamodb
  export CIVILAI_DYNAMODB_TABLE=civilai-app-uat
  export CIVILAI_ENVIRONMENT=uat

  uv run python scripts/fix_qw1_search_allowlist.py              # dry-run
  uv run python scripts/fix_qw1_search_allowlist.py --apply      # write
  uv run python scripts/fix_qw1_search_allowlist.py --apply --slugs austincivil,platform
"""

from __future__ import annotations

import argparse
import sys
from copy import deepcopy
from datetime import UTC, datetime

from civilai_platform.llm_defaults import ATX_CIVIL_SEARCH_DOMAINS
from civilai_platform.models.entities import LlmBaselineTemplate, TenantLlmConfig
from civilai_platform.settings import get_settings
from civilai_platform.store import get_store

OPEN_WEB_TOKEN = "*.*"
TARGET = list(ATX_CIVIL_SEARCH_DOMAINS)


def _domains(cfg: dict) -> list[str]:
    web = cfg.get("webSearch") if isinstance(cfg.get("webSearch"), dict) else {}
    raw = web.get("allowedDomains") or []
    return [str(d).strip() for d in raw if str(d).strip()]


def _set_domains(cfg: dict, domains: list[str]) -> dict:
    out = deepcopy(cfg)
    web = dict(out.get("webSearch") or {})
    web["allowedDomains"] = list(domains)
    out["webSearch"] = web
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes. Without this flag, only report what would change.",
    )
    parser.add_argument(
        "--allow-env",
        default="uat",
        help="Required CIVILAI_ENVIRONMENT value (default: uat).",
    )
    parser.add_argument(
        "--slugs",
        default="",
        help="Comma-separated url_slugs to patch. Empty = all tenants with *.*",
    )
    args = parser.parse_args()

    settings = get_settings()
    if settings.environment != args.allow_env:
        print(
            f"Refusing: CIVILAI_ENVIRONMENT={settings.environment!r} "
            f"(need --allow-env {args.allow_env!r} or matching env).",
            file=sys.stderr,
        )
        return 2
    if settings.store_backend != "dynamodb":
        print(
            f"Refusing: CIVILAI_STORE_BACKEND={settings.store_backend!r} (need dynamodb).",
            file=sys.stderr,
        )
        return 2

    store = get_store()
    slug_filter = {s.strip() for s in args.slugs.split(",") if s.strip()}

    baseline = store.get_llm_baseline()
    if not baseline:
        print("No LLM baseline found; seed it first (scripts/seed_llm_baseline.py).", file=sys.stderr)
        return 1

    base_domains = _domains(baseline.config)
    baseline_needs = OPEN_WEB_TOKEN in base_domains or base_domains != TARGET
    print(f"table={settings.dynamodb_table}  env={settings.environment}")
    print(f"baseline v{baseline.version} domains={base_domains}")
    print(f"target domains={TARGET}")
    if baseline_needs:
        print("→ baseline: UPDATE allowedDomains" + (" (apply)" if args.apply else " (dry-run)"))
        if args.apply:
            now = datetime.now(UTC)
            store.put_llm_baseline(
                LlmBaselineTemplate(
                    version=baseline.version + 1,
                    config=_set_domains(baseline.config, TARGET),
                    updated_at=now,
                    updated_by_user_id="ops:fix_qw1_search_allowlist",
                )
            )
            print(f"  wrote baseline v{baseline.version + 1}")
    else:
        print("→ baseline: already curated")

    tenants = store.list_tenants()
    patched = 0
    skipped = 0
    for tenant in tenants:
        if slug_filter and tenant.url_slug not in slug_filter:
            continue
        cfg_row = store.get_tenant_llm_config(tenant.tenant_id)
        if not cfg_row:
            skipped += 1
            continue
        domains = _domains(cfg_row.config)
        needs = OPEN_WEB_TOKEN in domains or (
            bool(slug_filter) and domains != TARGET
        )
        if not needs:
            skipped += 1
            continue
        print(
            f"→ tenant {tenant.url_slug}: {domains} → curated"
            + (" (apply)" if args.apply else " (dry-run)")
        )
        if args.apply:
            store.put_tenant_llm_config(
                TenantLlmConfig(
                    tenant_id=tenant.tenant_id,
                    baseline_version_at_copy=cfg_row.baseline_version_at_copy,
                    config=_set_domains(cfg_row.config, TARGET),
                    updated_at=datetime.now(UTC),
                )
            )
        patched += 1

    print(f"done: patched={patched} skipped={skipped} apply={args.apply}")
    if not args.apply and (baseline_needs or patched):
        print("Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
