"""Tests for prompts/ catalog loading."""

from __future__ import annotations

from civilai_platform.llm_defaults import SHARED_SYSTEM_PROMPT, default_llm_lab_config
from civilai_platform.prompt_catalog import (
    catalog_section_keys,
    load_section_user_prompt,
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
