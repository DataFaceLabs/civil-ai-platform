"""Tests for the Prompt Lab section defaults."""

from __future__ import annotations

from civilai_platform.llm_defaults import ATX_CIVIL_SEARCH_DOMAINS, default_llm_lab_config


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
