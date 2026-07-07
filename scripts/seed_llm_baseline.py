#!/usr/bin/env python3
"""Seed platform LLM baseline from built-in defaults (mirrors FE defaults.ts)."""

from __future__ import annotations

from civilai_platform.services import llm_config as llm_config_svc
from civilai_platform.store import get_store


def main() -> None:
    store = get_store()
    baseline = llm_config_svc.ensure_llm_baseline(store)
    print(f"LLM baseline version {baseline.version} ready ({len(baseline.config.get('sections', {}))} sections)")


if __name__ == "__main__":
    main()
