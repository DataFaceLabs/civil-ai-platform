"""Tests for the Prompt Lab section defaults."""

from __future__ import annotations

from civilai_platform.llm_defaults import ATX_CIVIL_SEARCH_DOMAINS, default_llm_lab_config


def test_section_system_prompt_is_lab_style_authority() -> None:
    prompt = default_llm_lab_config()["sectionSystemPrompt"]
    assert "Use only the field values provided" in prompt
    assert "Format sections using h2 and h3 headings" in prompt
    assert "field data facts in bold" in prompt
    assert "Draft voice (ACE house style" not in prompt
    assert "available field data" not in prompt.lower()


def test_web_search_defaults_use_atx_civils_trusted_sources() -> None:
    domains = default_llm_lab_config()["webSearch"]["allowedDomains"]

    assert domains == ATX_CIVIL_SEARCH_DOMAINS
    assert "*.*" not in domains
    assert "*.texas.gov" not in domains
    assert "traviscad.org" in domains
    assert "fema.gov" in domains
    assert "usda.gov" in domains


def test_utilities_section_matches_uat_catalog() -> None:
    utilities = default_llm_lab_config()["sections"]["utilities"]
    assert utilities["webSearchEnabled"] is True
    assert "NEAREST_WATER_MAIN_DETAIL" in utilities["inputFieldCodes"]
    assert "{{field.TAP_CARDS}}" in utilities["userPromptTemplate"]
    assert "will-serve" in utilities["userPromptTemplate"]
    assert utilities["guardrails"]["requiredDisclaimers"] == [
        "boundary only",
        "confirm with provider",
    ]


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
