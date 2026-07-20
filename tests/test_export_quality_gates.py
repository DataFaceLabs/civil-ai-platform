"""Export quality gates: address pin, site_payload mapping, derived recommendations."""

from __future__ import annotations

from io import BytesIO

import docx
import pytest
from fastapi.testclient import TestClient

from civilai_platform.app import create_app
from civilai_platform.services.export.context import (
    _MISSING,
    _PENDING_PLACEHOLDER,
    build_export_context,
    derive_recommendations,
    pin_narration_to_canonical_address,
)
from civilai_platform.services.export.polish import polish_export_docx
from civilai_platform.store import get_store
from tests.conftest import bootstrap_client_user


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIVILAI_DEV_AUTH", "true")
    monkeypatch.setenv("CIVILAI_STORE_BACKEND", "memory")
    monkeypatch.setenv("CIVILAI_ARTIFACT_BACKEND", "memory")
    monkeypatch.delenv("CIVILAI_EXPORT_ASYNC", raising=False)
    monkeypatch.delenv("CIVILAI_EXPORT_PDF_FUNCTION", raising=False)
    get_store.cache_clear()


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


def test_pin_narration_rewrites_alternate_situs() -> None:
    body = (
        "The property is located at 611 E Braker Ln, Austin, Texas 78753 in Travis County. "
        "Frontage on FARLEY DR is assumed."
    )
    canonical = "612 Farley Drive, Austin, Texas 78753, United States"
    out = pin_narration_to_canonical_address(body, canonical)
    assert "611 E Braker" not in out
    assert "612 Farley Drive, Austin, Texas 78753, United States" in out
    assert "FARLEY DR" in out  # road name, not a full street address phrase


def test_derive_recommendations_never_pending() -> None:
    bullets = derive_recommendations(
        fields={"PLATTING_STATUS": "undetermined"},
        bodies={},
        property_address="612 Farley Drive, Austin, TX 78753",
    )
    assert bullets
    assert all(_PENDING_PLACEHOLDER.lower() not in b.lower() for b in bullets)
    assert any("plat" in b.lower() for b in bullets)


def test_export_context_pins_body_and_fills_site_payload(
    client: TestClient,
) -> None:
    user_id = "user-export-quality"
    bootstrap = bootstrap_client_user(
        client,
        user_id,
        email="quality@example.com",
        name="Quality Firm",
    )
    tenant_id = bootstrap["memberships"][0]["tenant_id"]
    headers = {"X-Dev-User-Id": user_id, "X-Tenant-Id": tenant_id}
    farley = "612 Farley Drive, Austin, Texas 78753, United States"
    project_id = client.post(
        "/v1/projects",
        json={
            "name": farley,
            "address": farley,
            "jurisdiction": "Travis County; City of Austin",
            "proposed_use": "Retail",
        },
        headers=headers,
    ).json()["project_id"]

    store = get_store()
    state = store.get_project_state(tenant_id, project_id)
    assert state
    sections = [
        section.model_copy(
            update={
                "body": (
                    "<p>The property is located at 611 E Braker Ln, Austin, Texas 78753 "
                    "in Travis County.</p>"
                    if section.step_key == "parcel"
                    else (
                        f"<p><em>{_PENDING_PLACEHOLDER}</em></p>"
                        if section.step_key == "exhibits"
                        else section.body
                    )
                )
            }
        )
        for section in state.sections
    ]
    state = state.model_copy(
        update={
            "sections": sections,
            "site_payload": {
                "entity_id": "entity-farley",
                "environmental": [
                    {"code": "ECOREGION", "value": "Texas Blackland Prairies"},
                    {"code": "MIN_ELEVATION", "value": "720"},
                    {"code": "MAX_ELEVATION", "value": "730"},
                    {"code": "SOIL_PRIMARY_NAME", "value": "Urban land"},
                    {"code": "SOIL_HYDROLOGIC_GROUP", "value": "D"},
                ],
            },
        }
    )
    store.put_project_state(state)

    ctx = build_export_context(
        store,
        tenant_id=tenant_id,
        project_id=project_id,
        skin_id="civil1_study_v1",
        data_api_base=None,
        job_id="job-quality",
    )
    assert ctx.template_values["property_address"] == farley
    assert "611 E Braker" not in (ctx.template_values.get("adjacent_props") or "")
    assert farley in (ctx.template_values.get("adjacent_props") or "")
    assert ctx.template_values["ecoregion"] == "Texas Blackland Prairies"
    assert ctx.template_values["min_elevation"] == "720"
    assert ctx.template_values["soil_types"] == "Urban land"
    assert ctx.template_values["recommendation_1"]
    assert _PENDING_PLACEHOLDER not in ctx.template_values["recommendation_1"]
    assert ctx.provenance.get("recommendations_derived") is True


def test_polish_scrubs_inline_missing_sentences() -> None:
    document = docx.Document()
    document.add_paragraph(
        f"The property was Travis County; City of Austin. {_MISSING}"
    )
    document.add_paragraph(_MISSING)
    document.add_paragraph(f"Elevation ranges from {_MISSING} to {_MISSING} ft.")
    before = BytesIO()
    document.save(before)

    polished = polish_export_docx(before.getvalue())
    out = docx.Document(BytesIO(polished))
    texts = [p.text.strip() for p in out.paragraphs if p.text.strip()]
    assert all(_MISSING not in t for t in texts)
    assert any("is located in Travis County" in t for t in texts)


def test_polish_clock_tower_presentation_defects() -> None:
    document = docx.Document()
    document.add_heading("3.1 Zoning", level=2)
    document.add_paragraph("Zoning")
    document.add_paragraph("Zoning District")
    document.add_paragraph(
        "According to information provided, the property is zoned Commercial Highway (CH)."
    )
    document.add_heading("3.2 Platting", level=2)
    document.add_heading("3.7 Right of Way", level=2)
    document.add_paragraph(
        "Road class: Local street (inferred)\n"
        "The road is inferred to be a local street. Frontage on Clock Tower Drive."
    )
    document.add_paragraph(
        "According to the maps and additional data the property Surface hydrology "
        "characterization pending USGS NHD overlay."
    )
    document.add_paragraph("1 Purpose Scope")
    before = BytesIO()
    document.save(before)

    polished = polish_export_docx(before.getvalue())
    out = docx.Document(BytesIO(polished))
    texts = [p.text.strip() for p in out.paragraphs if p.text.strip()]
    joined = "\n".join(texts)

    assert "Zoning District" not in texts
    assert texts.count("Zoning") == 0
    assert "3.2 Platting" not in joined  # empty leaf collapsed
    assert "Local street (inferred)" not in joined
    assert "inferred to be a local street" not in joined.lower()
    assert "Local Road" in joined
    assert "the property Surface" not in joined
    assert "Purpose & Scope" in joined
    assert "is zoned Commercial Highway" in joined


def test_linter_allows_outline_subsequence_after_polish() -> None:
    from civilai_platform.services.export.linter import lint_docx
    from civilai_platform.services.export.skins import get_skin

    document = docx.Document()
    document.add_heading("1. Purpose and Scope", level=2)
    document.add_paragraph("Scope body.")
    document.add_heading("2. Description of the Property", level=2)
    document.add_paragraph("Property body.")
    document.add_heading("3. Feasibility Study", level=2)
    document.add_paragraph("Feasibility body.")
    document.add_heading("4. Summary", level=2)
    document.add_paragraph("Summary body.")
    document.add_heading("EXHIBITS", level=2)
    document.add_paragraph("Exhibits.")
    buf = BytesIO()
    document.save(buf)
    findings = lint_docx(buf.getvalue(), get_skin("atxcivil_v1"))
    assert "heading_sequence" not in {f["check"] for f in findings}
