#!/usr/bin/env python3
"""Seed or refresh platform LLM baseline from ``prompts/`` catalog."""

from __future__ import annotations

import argparse

from civilai_platform.llm_defaults import default_llm_lab_config
from civilai_platform.models.entities import LlmBaselineTemplate, utc_now
from civilai_platform.services import llm_config as llm_config_svc
from civilai_platform.store import get_store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Replace baseline config with the current prompts/ catalog (bumps version).",
    )
    args = parser.parse_args()

    store = get_store()
    catalog = default_llm_lab_config()
    existing = store.get_llm_baseline()

    if existing is None:
        baseline = llm_config_svc.ensure_llm_baseline(store)
        print(
            f"LLM baseline version {baseline.version} created "
            f"({len(baseline.config.get('sections', {}))} sections)"
        )
        return

    if not args.refresh:
        print(
            f"LLM baseline version {existing.version} already exists "
            f"({len(existing.config.get('sections', {}))} sections). "
            "Use --refresh to overwrite from prompts/."
        )
        return

    now = utc_now()
    updated = LlmBaselineTemplate(
        version=existing.version + 1,
        config=catalog,
        updated_at=now,
        updated_by_user_id="ops:seed_llm_baseline",
    )
    store.put_llm_baseline(updated)
    print(
        f"LLM baseline refreshed to version {updated.version} "
        f"({len(updated.config.get('sections', {}))} sections)"
    )


if __name__ == "__main__":
    main()
