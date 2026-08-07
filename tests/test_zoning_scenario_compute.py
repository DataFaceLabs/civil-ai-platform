"""Unit tests for zoning scenario compute (mocked reg-text)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from civilai_platform.models.entities import FieldValue, Section
from civilai_platform.models.zoning_scenario import (
    ZoningChangeScenario,
    ZoningScenarioIntent,
    ZoningScenarioState,
)
from civilai_platform.services.zoning_scenario_compute import (
    _compose_citations,
    _filter_citation_hits,
    compute_zoning_scenario,
)


def _scenario_state() -> ZoningScenarioState:
    return ZoningScenarioState(
        schema_version=1,
        analysis_basis="baseline",
        baseline_jurisdiction_key="coa_full",
        effective_jurisdiction_key="coa_full",
        active_scenario_id="sc-1",
        scenarios=[
            ZoningChangeScenario(
                scenario_id="sc-1",
                label="Rezone to MF-4",
                status="draft",
                created_at="2026-08-06T12:00:00Z",
                updated_at="2026-08-06T12:00:00Z",
                created_by_user_id="u1",
                intent=ZoningScenarioIntent(proposed_zoning_code="MF-4"),
            )
        ],
    )


def test_compose_citations_only() -> None:
    hits = [
        {
            "section_id": "25-2-492",
            "citation": "LDC §25-2-492",
            "title": "Sec. 25-2-492. - MF-4 (Multifamily Residence Highest Density) district.",
            "excerpt": "MF-4 allows multifamily residential uses.",
        }
    ]
    assert _compose_citations("MF-4", hits) == "MF-4 — LDC §25-2-492"
    assert _compose_citations("MF-4", []) == ""


def test_filter_drops_boilerplate_and_non_compat() -> None:
    hits = [
        {
            "section_id": "1-50",
            "citation": "Sec. 1-50. - Definitions.",
            "title": "Sec. 1-50. - Definitions.",
        },
        {
            "section_id": "2-73",
            "citation": "Sec. 2-73. - MU-L (Mixed-Use Limited) district.",
            "title": "Sec. 2-73. - MU-L (Mixed-Use Limited) district.",
        },
        {
            "section_id": "2-91",
            "citation": "Sec. 2-91. - Supplementary use standards.",
            "title": "Sec. 2-91. - Supplementary use standards.",
        },
    ]
    zoning = _filter_citation_hits("ZONING_REGS", "MU-L", hits)
    assert [h["citation"] for h in zoning] == [
        "Sec. 2-73. - MU-L (Mixed-Use Limited) district."
    ]
    compat = _filter_citation_hits("COMPATIBILITY_STDS", "MU-L", hits)
    assert compat == []


def test_compute_fills_proposed_and_comparisons() -> None:
    hits = [
        {
            "section_id": "25-2-492",
            "citation": "LDC §25-2-492",
            "title": "Sec. 25-2-492. - MF-4 (Multifamily Residence Highest Density) district.",
            "deep_link": "https://example.com/25-2-492",
            "excerpt": "MF-4 allows multifamily residential uses.",
            "retrieved_at": "2026-08-06T00:00:00Z",
        }
    ]

    def fake_post(url: str, **kwargs):  # type: ignore[no-untyped-def]
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        if url.endswith("/ensure"):
            resp.json.return_value = {
                "status": "ready",
                "corpus_version": "fixture-2026-08-06",
            }
            resp.raise_for_status = MagicMock()
            return resp
        resp.json.return_value = hits
        resp.raise_for_status = MagicMock()
        return resp

    def fake_get(url: str, **kwargs):  # type: ignore[no-untyped-def]
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        if "/v1/dsi/resolve" in url:
            resp.json.return_value = {
                "found": True,
                "freshness": "current",
                "dsi_version": "coa-dsi-test",
                "record": {
                    "standards": {
                        "min_lot_area_sqft": 8000,
                        "min_lot_width_ft": 50,
                        "setback_front_ft": 25,
                        "setback_side_ft": 5,
                        "setback_rear_ft": 10,
                        "max_building_coverage_pct": 60,
                        "max_impervious_cover_pct": 80,
                        "max_height_ft": 60,
                    },
                    "citations": {
                        "dimensional": {
                            "section_id": "S25-2",
                            "citation": "LDC Ch. 25-2",
                            "deep_link": "https://example.com/25-2",
                        }
                    },
                },
            }
            return resp
        resp.json.return_value = {}
        return resp

    client = MagicMock(spec=httpx.Client)
    client.post.side_effect = fake_post
    client.get.side_effect = fake_get

    sections = [
        Section(
            id="z1",
            title="Zoning",
            step_key="zoning",
            fields={
                "ZONING_REGS": FieldValue(value="SF-2 residential", status="complete"),
            },
        )
    ]

    with patch(
        "civilai_platform.services.zoning_scenario_compute.get_settings"
    ) as settings_mock:
        settings_mock.return_value.data_api_base = "http://data.test"
        settings_mock.return_value.data_service_key = None
        updated = compute_zoning_scenario(
            _scenario_state(),
            scenario_id="sc-1",
            site_payload={},
            sections=sections,
            http_client=client,
        )

    sc = updated.scenarios[0]
    assert sc.status == "computed"
    assert sc.proposed.fields["ZONING_REGS"].value == "MF-4 — LDC §25-2-492"
    assert "allows multifamily" not in sc.proposed.fields["ZONING_REGS"].value
    # Search returns the MF-4 district title for every query in this mock; IC filter
    # accepts the district article, and compatibility requires "compatibilit*" — empty.
    assert "LDC §25-2-492" in sc.proposed.fields["IMPERVIOUS_REGS"].value
    assert sc.proposed.fields["COMPATIBILITY_STDS"].value == ""
    assert sc.proposed.fields["MAX_BUILDING_HEIGHT"].value == "60 ft"
    assert sc.input_fingerprint is not None
    assert sc.input_fingerprint.dsi_version == "coa-dsi-test"
    assert sc.comparisons
    assert sc.risk_summary.entitlement_required is True
    assert sc.computation.status == "succeeded"


def test_compute_empty_when_search_returns_nothing() -> None:
    def fake_post(url: str, **kwargs):  # type: ignore[no-untyped-def]
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        if url.endswith("/ensure"):
            resp.json.return_value = {"status": "ready", "corpus_version": "x"}
            resp.raise_for_status = MagicMock()
            return resp
        resp.json.return_value = []
        resp.raise_for_status = MagicMock()
        return resp

    def fake_get(url: str, **kwargs):  # type: ignore[no-untyped-def]
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"found": False}
        return resp

    client = MagicMock(spec=httpx.Client)
    client.post.side_effect = fake_post
    client.get.side_effect = fake_get

    with patch(
        "civilai_platform.services.zoning_scenario_compute.get_settings"
    ) as settings_mock:
        settings_mock.return_value.data_api_base = "http://data.test"
        settings_mock.return_value.data_service_key = None
        updated = compute_zoning_scenario(
            _scenario_state(),
            scenario_id="sc-1",
            site_payload={},
            sections=[],
            http_client=client,
        )

    sc = updated.scenarios[0]
    assert sc.proposed.fields["ZONING_REGS"].value == ""
    assert sc.proposed.fields["IMPERVIOUS_REGS"].value == ""
    assert sc.proposed.fields["COMPATIBILITY_STDS"].value == ""
    assert "ZONING_REGS" in sc.risk_summary.open_gaps


def test_compute_missing_scenario_raises() -> None:
    with pytest.raises(ValueError, match="not found"):
        compute_zoning_scenario(
            _scenario_state(),
            scenario_id="missing",
            site_payload={},
            sections=[],
            http_client=MagicMock(),
        )
