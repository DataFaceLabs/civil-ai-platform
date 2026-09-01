#!/usr/bin/env python3
"""Seed platform Facts Guard Rails from civil-ai-data YAML."""

from __future__ import annotations

import argparse
from pathlib import Path

from civilai_platform.services import guardrails as guardrails_svc
from civilai_platform.store import get_store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Overwrite existing scope records from seed YAML.",
    )
    parser.add_argument(
        "--seed-dir",
        type=Path,
        default=None,
        help="Override seed directory (default: ../civil-ai-data/data/reference/facts_guardrails/zoning).",
    )
    args = parser.parse_args()

    store = get_store()
    written = guardrails_svc.seed_zoning_guardrails_from_yaml(
        store,
        seed_dir=args.seed_dir,
        refresh=args.refresh,
    )
    meta = store.get_guardrails_version_meta(guardrails_svc.GUARDRAILS_DOMAIN)
    version = meta.version_hash if meta else "none"
    scopes = len(store.list_guardrails_scopes(guardrails_svc.GUARDRAILS_DOMAIN))
    print(f"Guard rails seed complete: {written} scope(s) written, {scopes} total, version={version}")


if __name__ == "__main__":
    main()
