"""Tests for zoning brief request assembly."""

from __future__ import annotations

from civilai_platform.models.entities import FieldValue, ProjectState, Section
from civilai_platform.models.zoning_scenario import ZoningScenarioState
from civilai_platform.services.zoning_brief_context import build_zoning_brief_request


def test_build_zoning_brief_request_from_scenario_and_fields() -> None:
    state = ProjectState(
        project_id="proj-1",
        tenant_id="tenant-1",
        sections=[
            Section(
                id="zoning",
                title="Zoning",
                step_key="zoning",
                fields={
                    "ZONING_REGS": FieldValue(
                        value="Zoning: NC2-55 (M)\nOverlays: [\"PAV\"]",
                        status="review",
                    ),
                },
            )
        ],
        parcel={"source_fips": "53033"},
        zoning_scenario=ZoningScenarioState(baseline_jurisdiction_key="seattle"),
        updated_at="2026-09-01T00:00:00Z",
    )
    request = build_zoning_brief_request(
        field_context={"GOVERNING_JURIS": "City of Seattle"},
        project_state=state,
    )
    assert request is not None
    assert request.jurisdiction_key == "seattle"
    assert request.zoning_code == "NC2-55 (M)"
    assert request.overlay_codes == ["PAV"]
    assert request.mha_class == "M"
    assert request.state_abbr == "WA"
    assert request.county_fips == "53033"


def test_build_zoning_brief_request_missing_jurisdiction_returns_none() -> None:
    state = ProjectState(
        project_id="proj-1",
        tenant_id="tenant-1",
        sections=[],
        updated_at="2026-09-01T00:00:00Z",
    )
    assert (
        build_zoning_brief_request(
            field_context={"ZONING_REGS": "Zoning: LR1 (M)"},
            project_state=state,
        )
        is None
    )
