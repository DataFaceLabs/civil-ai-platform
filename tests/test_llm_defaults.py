"""Tests for the Prompt Lab section defaults."""

from __future__ import annotations

from civilai_platform.llm_defaults import default_llm_lab_config


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
