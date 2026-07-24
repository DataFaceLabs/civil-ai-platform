#!/usr/bin/env python3
"""Ops: add nearest-main + tap-card fields to utilities Prompt Lab configs (M2-AGENT-UTIL).

Updates:
  1. Platform LLM baseline utilities ``inputFieldCodes`` + template stubs
  2. Every tenant LLM config (or ``--slugs`` only)

Surgical: only merges utilities nearest-main / TAP_CARDS codes and template lines.
Does **not** restore full baseline (preserves per-tenant prompt / section edits).

Usage (from civil-ai-platform):

  export AWS_PROFILE=civilai
  export CIVILAI_STORE_BACKEND=dynamodb
  export CIVILAI_DYNAMODB_TABLE=civilai-app-uat
  export CIVILAI_ENVIRONMENT=uat

  uv run python scripts/patch_utilities_nearest_main_prompt.py              # dry-run
  uv run python scripts/patch_utilities_nearest_main_prompt.py --apply      # write
"""

from __future__ import annotations

import argparse
import sys
from copy import deepcopy
from datetime import UTC, datetime

from civilai_platform.models.entities import LlmBaselineTemplate, TenantLlmConfig
from civilai_platform.settings import get_settings
from civilai_platform.store import get_store

CODES = (
    "NEAREST_WATER_MAIN_DETAIL",
    "NEAREST_WASTEWATER_MAIN_DETAIL",
    "TAP_CARDS",
)

CAVEAT = (
    "Nearest-main GIS fields and tap cards are proximity / historical evidence "
    "only — never treat them as capacity, pressure, connection approval, or "
    "will-serve. If nearest-main detail is empty, say mapped mains were not "
    "found nearby (or coverage is unknown) rather than inventing distances."
)

FIELD_LINES = (
    "Nearest water main: {{field.NEAREST_WATER_MAIN_DETAIL}}",
    "Nearest wastewater main: {{field.NEAREST_WASTEWATER_MAIN_DETAIL}}",
    "Tap cards: {{field.TAP_CARDS}}",
)


def _utilities(cfg: dict) -> dict | None:
    sections = cfg.get("sections")
    if not isinstance(sections, dict):
        return None
    util = sections.get("utilities")
    return util if isinstance(util, dict) else None


def _needs_codes(util: dict) -> bool:
    codes = util.get("inputFieldCodes") or []
    return any(code not in codes for code in CODES)


def _needs_template(util: dict) -> bool:
    template = str(util.get("userPromptTemplate") or "")
    return any(f"{{{{field.{code}}}}}" not in template for code in CODES)


def _merge_codes(codes: list[str]) -> list[str]:
    out = list(codes)
    # Insert after WASTEWATER_SERVICE when present; else append before ELECTRIC.
    anchor = "WASTEWATER_SERVICE"
    insert_at = out.index(anchor) + 1 if anchor in out else len(out)
    for code in CODES:
        if code in out:
            continue
        out.insert(insert_at, code)
        insert_at += 1
    return out


def _merge_template(template: str) -> str:
    text = template
    if CAVEAT not in text:
        # Prefer inserting before the Water: field block.
        marker = "Water: {{field.WATER_SERVICE}}"
        if marker in text:
            text = text.replace(marker, f"{CAVEAT}\n\n{marker}", 1)
        else:
            text = f"{text.rstrip()}\n\n{CAVEAT}"
    # Insert field lines after Wastewater when present.
    ww = "Wastewater: {{field.WASTEWATER_SERVICE}}"
    missing = [line for line in FIELD_LINES if line not in text]
    if missing:
        block = "\n".join(missing)
        if ww in text:
            text = text.replace(ww, f"{ww}\n{block}", 1)
        else:
            text = f"{text.rstrip()}\n{block}"
    return text


def _patch_config(cfg: dict) -> tuple[dict | None, list[str]]:
    util = _utilities(cfg)
    if util is None:
        return None, ["no utilities section"]
    reasons: list[str] = []
    if _needs_codes(util):
        reasons.append("codes")
    if _needs_template(util):
        reasons.append("template")
    if not reasons:
        return None, []
    out = deepcopy(cfg)
    util_out = out["sections"]["utilities"]
    if "codes" in reasons:
        util_out["inputFieldCodes"] = _merge_codes(
            [str(c) for c in (util_out.get("inputFieldCodes") or [])]
        )
    if "template" in reasons:
        util_out["userPromptTemplate"] = _merge_template(
            str(util_out.get("userPromptTemplate") or "")
        )
    return out, reasons


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
        help="Comma-separated url_slugs to patch. Empty = all tenants.",
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
        print("No LLM baseline found; seed it first.", file=sys.stderr)
        return 1

    print(f"table={settings.dynamodb_table}  env={settings.environment}")
    print(f"baseline v{baseline.version}")

    patched_cfg, reasons = _patch_config(baseline.config)
    baseline_needs = patched_cfg is not None
    if baseline_needs:
        print(
            f"→ baseline: UPDATE utilities ({', '.join(reasons)})"
            + (" (apply)" if args.apply else " (dry-run)")
        )
        if args.apply and patched_cfg is not None:
            store.put_llm_baseline(
                LlmBaselineTemplate(
                    version=baseline.version + 1,
                    config=patched_cfg,
                    updated_at=datetime.now(UTC),
                    updated_by_user_id="ops:patch_utilities_nearest_main_prompt",
                )
            )
            print(f"  wrote baseline v{baseline.version + 1}")
    else:
        print("→ baseline: already has nearest-main + tap cards")

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
        next_cfg, reasons = _patch_config(cfg_row.config)
        if next_cfg is None:
            skipped += 1
            continue
        print(
            f"→ tenant {tenant.url_slug}: UPDATE utilities ({', '.join(reasons)})"
            + (" (apply)" if args.apply else " (dry-run)")
        )
        if args.apply:
            store.put_tenant_llm_config(
                TenantLlmConfig(
                    tenant_id=tenant.tenant_id,
                    baseline_version_at_copy=cfg_row.baseline_version_at_copy,
                    config=next_cfg,
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
