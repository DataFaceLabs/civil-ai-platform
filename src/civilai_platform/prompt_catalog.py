"""Load canonical Prompt Lab section templates from ``prompts/``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_MANIFEST_NAME = "section_prompt_manifest.yaml"


def resolve_prompts_dir(start: Path | None = None) -> Path:
    """Locate ``prompts/`` in a repo checkout or a Lambda zip.

    Local layout: ``civil-ai-platform/src/civilai_platform/prompt_catalog.py``
    → repo root ``prompts/``.

    Lambda layout: ``/var/task/civilai_platform/prompt_catalog.py`` plus
    ``/var/task/prompts/`` (copied by ``scripts/package-lambda.sh``). Using
    ``parents[2]`` here resolves to ``/var/prompts``, which does not exist.
    """
    here = (start or Path(__file__)).resolve()
    candidates = (
        here.parents[2] / "prompts",
        here.parents[1] / "prompts",
    )
    for path in candidates:
        if (path / _MANIFEST_NAME).is_file():
            return path
    looked = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Prompt catalog manifest not found; looked in: {looked}")


_PROMPTS_DIR = resolve_prompts_dir()
_MANIFEST_PATH = _PROMPTS_DIR / _MANIFEST_NAME


def prompts_dir() -> Path:
    return _PROMPTS_DIR


def manifest_path() -> Path:
    return _MANIFEST_PATH


@lru_cache(maxsize=1)
def load_prompt_manifest() -> dict[str, Any]:
    raw = yaml.safe_load(_MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid prompt manifest: {_MANIFEST_PATH}")
    return raw


def load_section_system_prompt() -> str:
    manifest = load_prompt_manifest()
    filename = str(manifest.get("section_system_prompt_file") or "").strip()
    if not filename:
        raise ValueError("section_system_prompt_file missing from prompt manifest")
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8").strip()


def load_section_user_prompt(step_key: str) -> str:
    manifest = load_prompt_manifest()
    sections = dict(manifest.get("sections") or {})
    section = dict(sections.get(step_key) or {})
    filename = str(section.get("prompt_file") or "").strip()
    if not filename:
        raise KeyError(f"No prompt_file for section {step_key!r} in {_MANIFEST_PATH}")
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8").strip()


def section_prompt_overrides(step_key: str) -> dict[str, Any]:
    """Per-section Prompt Lab settings from the manifest (camelCase API keys)."""
    manifest = load_prompt_manifest()
    sections = dict(manifest.get("sections") or {})
    section = dict(sections.get(step_key) or {})
    overrides: dict[str, Any] = {
        "userPromptTemplate": load_section_user_prompt(step_key),
        "inputFieldCodes": list(section.get("input_field_codes") or []),
    }
    if "web_search_enabled" in section:
        overrides["webSearchEnabled"] = bool(section["web_search_enabled"])
    if "search_context_hint" in section:
        overrides["searchContextHint"] = str(section.get("search_context_hint") or "")
    if "model_preset" in section and str(section.get("model_preset") or "").strip():
        overrides["modelPreset"] = str(section["model_preset"]).strip()
    guardrails = section.get("guardrails")
    if isinstance(guardrails, dict) and guardrails:
        overrides["guardrails"] = dict(guardrails)
    return overrides


def catalog_section_keys() -> tuple[str, ...]:
    manifest = load_prompt_manifest()
    sections = dict(manifest.get("sections") or {})
    return tuple(str(key) for key in sections)
