#!/usr/bin/env python3
"""Sync Prompt Lab baseline (+ optional tenants) from ``prompts/`` catalog.

Loads ``prompts/section_prompt_manifest.yaml`` and sibling ``*_LLM_Prompt.txt``
files via ``default_llm_lab_config()`` and writes them to DynamoDB so Develop
and UAT section templates and ``inputFieldCodes`` (Known Site Facts allowlists)
stay aligned with the repo.

Usage (from civil-ai-platform):

  export AWS_PROFILE=civilai
  export CIVILAI_STORE_BACKEND=dynamodb

  # Dry-run against UAT
  CIVILAI_DYNAMODB_TABLE=civilai-app-uat CIVILAI_ENVIRONMENT=uat \\
    uv run python scripts/sync_llm_baseline_from_prompts.py --allow-env uat

  # Apply to Develop + refresh tenant copies
  CIVILAI_DYNAMODB_TABLE=civilai-app-develop CIVILAI_ENVIRONMENT=develop \\
    uv run python scripts/sync_llm_baseline_from_prompts.py \\
      --allow-env develop --apply --restore-tenants
"""

from __future__ import annotations

import argparse
import sys
from copy import deepcopy
from datetime import UTC, datetime

from civilai_platform.llm_defaults import default_llm_lab_config
from civilai_platform.models.entities import LlmBaselineTemplate, TenantLlmConfig
from civilai_platform.prompt_catalog import catalog_section_keys
from civilai_platform.settings import get_settings
from civilai_platform.store import get_store

_CATALOG_SECTIONS = frozenset(catalog_section_keys())
_SYNC_KEYS = (
    "userPromptTemplate",
    "inputFieldCodes",
    "webSearchEnabled",
    "searchContextHint",
    "modelPreset",
    "guardrails",
)


def _merge_catalog_sections(existing: dict, catalog: dict) -> tuple[dict, list[str]]:
    """Return merged config and list of section keys that changed."""
    out = deepcopy(existing)
    sections = dict(out.get("sections") or {})
    catalog_sections = dict(catalog.get("sections") or {})
    changed: list[str] = []

    if (existing.get("sectionSystemPrompt") or "").strip() != (
        catalog.get("sectionSystemPrompt") or ""
    ).strip():
        out["sectionSystemPrompt"] = catalog["sectionSystemPrompt"]
        changed.append("sectionSystemPrompt")

    for step_key in sorted(_CATALOG_SECTIONS):
        current = dict(sections.get(step_key) or {})
        incoming = dict(catalog_sections.get(step_key) or {})
        next_section = deepcopy(current)
        section_changed = False
        for key in _SYNC_KEYS:
            if key not in incoming:
                continue
            if next_section.get(key) != incoming[key]:
                next_section[key] = incoming[key]
                section_changed = True
        if section_changed:
            sections[step_key] = next_section
            changed.append(step_key)

    out["sections"] = sections
    return out, changed


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
        "--restore-tenants",
        action="store_true",
        help="After baseline update, merge catalog sections into every tenant LLM config.",
    )
    parser.add_argument(
        "--slugs",
        default="",
        help="Comma-separated url_slugs when using --restore-tenants (empty = all).",
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
    catalog = default_llm_lab_config()
    baseline = store.get_llm_baseline()
    if not baseline:
        print("No LLM baseline found; run scripts/seed_llm_baseline.py first.", file=sys.stderr)
        return 1

    merged, changed = _merge_catalog_sections(baseline.config, catalog)
    print(f"table={settings.dynamodb_table}  env={settings.environment}")
    print(f"baseline v{baseline.version}")

    if not changed:
        print("→ baseline: already matches prompts/ catalog")
    else:
        print(
            f"→ baseline: UPDATE ({', '.join(changed)})"
            + (" (apply)" if args.apply else " (dry-run)")
        )
        if args.apply:
            store.put_llm_baseline(
                LlmBaselineTemplate(
                    version=baseline.version + 1,
                    config=merged,
                    updated_at=datetime.now(UTC),
                    updated_by_user_id="ops:sync_llm_baseline_from_prompts",
                )
            )
            print(f"  wrote baseline v{baseline.version + 1}")

    slug_filter = {s.strip() for s in args.slugs.split(",") if s.strip()}
    patched = 0
    skipped = 0
    if args.restore_tenants:
        for tenant in store.list_tenants():
            if slug_filter and tenant.url_slug not in slug_filter:
                continue
            tenant_row = store.get_tenant_llm_config(tenant.tenant_id)
            if not tenant_row:
                skipped += 1
                continue
            tenant_merged, tenant_changed = _merge_catalog_sections(tenant_row.config, catalog)
            if not tenant_changed:
                skipped += 1
                continue
            print(
                f"→ tenant {tenant.url_slug}: UPDATE ({', '.join(tenant_changed)})"
                + (" (apply)" if args.apply else " (dry-run)")
            )
            if args.apply:
                store.put_tenant_llm_config(
                    TenantLlmConfig(
                        tenant_id=tenant.tenant_id,
                        baseline_version_at_copy=tenant_row.baseline_version_at_copy,
                        config=tenant_merged,
                        updated_at=datetime.now(UTC),
                    )
                )
            patched += 1

    print(f"done: baseline_changed={bool(changed)} tenants_patched={patched} skipped={skipped}")
    if not args.apply and (changed or patched):
        print("Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
