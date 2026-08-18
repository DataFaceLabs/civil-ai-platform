"""Tests for the Prompt Lab section defaults."""

from __future__ import annotations

from civilai_platform.llm_defaults import ATX_CIVIL_SEARCH_DOMAINS, default_llm_lab_config


def test_section_system_prompt_uses_unknown_fact_house_style() -> None:
    prompt = default_llm_lab_config()["sectionSystemPrompt"]
    assert "not currently known and should be confirmed" in prompt
    assert "available field data" not in prompt.lower()
    assert "Use only the field values provided" not in prompt


def test_web_search_defaults_use_atx_civils_trusted_sources() -> None:
    domains = default_llm_lab_config()["webSearch"]["allowedDomains"]

    assert domains == ATX_CIVIL_SEARCH_DOMAINS
    assert "*.*" not in domains
    assert "*.texas.gov" not in domains
    assert "traviscad.org" in domains
    assert "fema.gov" in domains
    assert "usda.gov" in domains


def test_utilities_section_never_states_ifc_edition_on_null() -> None:
    # A1: 1852 FM 1704's ifc_edition fact was null, but the exported narration
    # asserted "The 2021 International Fire Code governs" -- a fabrication on a
    # null fact. The default prompt must gate a specific edition citation on the
    # field actually having a value, and IFC_EDITION must be fetched as input so
    # the model can see whether it's null.
    utilities = default_llm_lab_config()["sections"]["utilities"]
    assert "IFC_EDITION" in utilities["inputFieldCodes"]
    assert "{{field.IFC_EDITION}}" in utilities["userPromptTemplate"]
    assert "unless the IFC edition field below has a value" in utilities["userPromptTemplate"]


def test_utilities_section_includes_nearest_main_and_tap_cards() -> None:
    # M2-AGENT-UTIL: lake now serves nearest_* + tap cards; Prompt Lab must
    # pass them into the draft and keep the capacity / will-serve non-goal.
    utilities = default_llm_lab_config()["sections"]["utilities"]
    for code in (
        "NEAREST_WATER_MAIN_DETAIL",
        "NEAREST_WASTEWATER_MAIN_DETAIL",
        "TAP_CARDS",
    ):
        assert code in utilities["inputFieldCodes"]
        assert f"{{{{field.{code}}}}}" in utilities["userPromptTemplate"]
    assert "will-serve" in utilities["userPromptTemplate"]
    assert "proximity / historical evidence" in utilities["userPromptTemplate"]
