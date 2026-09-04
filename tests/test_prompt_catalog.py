"""Tests for prompts/ catalog loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from civilai_platform.llm_defaults import SHARED_SYSTEM_PROMPT, default_llm_lab_config
from civilai_platform.prompt_catalog import (
    catalog_section_keys,
    load_section_user_prompt,
    resolve_prompts_dir,
    section_prompt_overrides,
)


def test_catalog_includes_uat_parcel_field_codes() -> None:
    parcel = section_prompt_overrides("parcel")
    assert "CAD_LAND_USE" in parcel["inputFieldCodes"]
    assert "TCAD_LAND_USE" not in parcel["inputFieldCodes"]
    assert "{{field.CAD_LAND_USE}}" in parcel["userPromptTemplate"]


def test_default_config_loads_parcel_prompt_from_file() -> None:
    cfg = default_llm_lab_config()
    parcel = cfg["sections"]["parcel"]
    assert parcel["userPromptTemplate"] == load_section_user_prompt("parcel")
    assert "Development agreements" in parcel["userPromptTemplate"]


def test_shared_system_prompt_matches_catalog_file() -> None:
    assert "h2 and h3 headings" in SHARED_SYSTEM_PROMPT
    assert "available field data" not in SHARED_SYSTEM_PROMPT.lower()


def test_catalog_section_keys_cover_document_sections() -> None:
    keys = set(catalog_section_keys())
    assert {"parcel", "environmental", "access", "zoning", "utilities", "draft"} <= keys


def test_resolve_prompts_dir_local_checkout_layout() -> None:
    from civilai_platform import prompt_catalog

    found = resolve_prompts_dir(Path(prompt_catalog.__file__))
    assert found.name == "prompts"
    assert (found / "section_prompt_manifest.yaml").is_file()


def test_resolve_prompts_dir_lambda_task_layout(tmp_path: Path) -> None:
    task = tmp_path / "task"
    pkg = task / "civilai_platform"
    pkg.mkdir(parents=True)
    prompts = task / "prompts"
    prompts.mkdir()
    (prompts / "section_prompt_manifest.yaml").write_text("sections: {}\n", encoding="utf-8")
    fake_module = pkg / "prompt_catalog.py"
    fake_module.write_text("# lambda layout\n", encoding="utf-8")
    found = resolve_prompts_dir(fake_module)
    assert found == prompts


def test_resolve_prompts_dir_missing_raises(tmp_path: Path) -> None:
    fake_module = tmp_path / "civilai_platform" / "prompt_catalog.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.write_text("# no prompts\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="Prompt catalog manifest not found"):
        resolve_prompts_dir(fake_module)
