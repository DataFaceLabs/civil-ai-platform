"""Foundational X1 tests: content contract invariants + skin registry resolution."""

from __future__ import annotations

from civilai_platform.services.export import contract, skins


def test_contract_section_ids_are_unique() -> None:
    ids = [s.id for s in contract.CONTRACT_SECTIONS]
    assert len(ids) == len(set(ids)), "duplicate contract section id"


def test_contract_lookups_are_consistent() -> None:
    assert set(contract.CONTRACT_SECTIONS_BY_ID) == {s.id for s in contract.CONTRACT_SECTIONS}
    assert contract.REQUIRED_SECTION_IDS <= set(contract.CONTRACT_SECTIONS_BY_ID)
    assert contract.NARRATION_SECTION_IDS <= set(contract.CONTRACT_SECTIONS_BY_ID)


def test_core_contract_sections_present() -> None:
    # A representative slice across every group must exist and be required.
    for section_id in (
        "purpose_scope",
        "property_id",
        "zoning",
        "floodplain",
        "fire_protection",
        "verdict",
        "recommendations",
        "exhibit_list",
    ):
        section = contract.contract_section(section_id)
        assert section is not None, section_id
        assert section.required is True


def test_civil1_additions_are_optional() -> None:
    # Sections ATX lacks (Civil1 value-adds) must not gate a legacy ATX-skin export.
    for section_id in ("risk_register", "constraint_dashboard", "sources_appendix"):
        section = contract.contract_section(section_id)
        assert section is not None and section.required is False


def test_verdict_is_enum_and_narration_is_prose() -> None:
    assert contract.contract_section("verdict").slot_type is contract.SlotType.ENUM
    assert "zoning" in contract.NARRATION_SECTION_IDS
    assert "verdict" not in contract.NARRATION_SECTION_IDS


def test_get_skin_defaults_and_fails_closed() -> None:
    assert skins.get_skin("atxcivil_v1").id == "atxcivil_v1"
    # Unknown id -> default.
    assert skins.get_skin("does_not_exist").id == skins.DEFAULT_SKIN_ID
    # None -> default.
    assert skins.get_skin(None).id == skins.DEFAULT_SKIN_ID


def test_unavailable_skin_falls_back_to_default() -> None:
    # civil1_study_v1 is registered but not renderable until DESIGN lands.
    assert skins.CIVIL1_STUDY_V1.available is False
    assert skins.get_skin("civil1_study_v1").id == skins.DEFAULT_SKIN_ID


def test_atxcivil_skin_metadata() -> None:
    skin = skins.get_skin("atxcivil_v1")
    assert skin.tier == 2
    assert skin.outline[0] == "1" and skin.outline[-1] == "EXHIBITS"
    # Subdoc narration tokens the renderer must feed via {{p }} paragraph tags.
    assert "zoning_regs" in skin.narration_tokens
    assert "floodplain_status" in skin.narration_tokens


def test_atxcivil_outline_matches_legacy_linter() -> None:
    # The per-skin outline must match E6's proven global outline until E6 goes per-skin.
    from scripts.lint_export_docx import EXPECTED_OUTLINE

    assert skins.get_skin("atxcivil_v1").outline == EXPECTED_OUTLINE
