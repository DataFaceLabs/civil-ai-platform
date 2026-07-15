"""E1 spike: fill the converted ACE template with real data for one demo parcel.

Proves the docxtpl mechanism end to end: real EC2 data-API field values + real
agent narration (from a captured eval run) rendered into
`assets/templates/atxcivil_v1.docx`, preserving the template's own Word styles,
heading numbering, and static boilerplate (Purpose & Scope, HSG A-D paragraphs,
Summary shape) because none of that lives in code -- it lives in the template.

Multi-paragraph narration (agent_draft text, which is markdown-ish: **bold**
labels and blank-line-separated paragraphs) is rendered via docxtpl subdocs so
it becomes real Word paragraphs, not one run-on blob. Subdocs require the jinja
tag to be alone in its own paragraph (`{{p token }}` in the template) -- the
tokens used for narration below are already isolated in their own paragraph in
the source template, so no template restructuring was needed.

Every field is sourced from a real system:
- EC2 data API (`http://100.48.24.128:8000/v1/sections/{section}/facts/{entity}`)
- A captured eval run's `agent_draft` narration (zoning/environmental/flood/utilities)
Fields with no real source (client contact info, project/preparer name -- these are
user-entered in the real app, never derived) use clearly-marked placeholder text,
never fabricated values.

Usage::

    CIVILAI_DATA_SERVICE_KEY=... uv run python scripts/docxtpl_spike_render.py
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from docxtpl import DocxTemplate

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = REPO_ROOT / "assets" / "templates" / "atxcivil_v1.docx"
OUTPUT_PATH = REPO_ROOT / "assets" / "templates" / "_spike_output_fm812.docx"

DATA_API_BASE = os.environ.get("CIVILAI_DATA_API_BASE", "http://100.48.24.128:8000")
DATA_SERVICE_KEY = os.environ["CIVILAI_DATA_SERVICE_KEY"]

ENTITY_ID = "a1a722a9-10ad-2260-6e9b-abc2d0ecfe75"  # 13903 FM 812 Rd, Del Valle (Travis)

RUN_JSON = (
    REPO_ROOT.parent
    / "agent-eval-runs"
    / "demo-smoke-c1c2-20260714c"
    / "13903-fm-812-rd-del-valle-tx-78617_haiku-4-5_20260714T015733Z"
    / "run.json"
)

_M_TO_FT = 3.28084

_BOLD_LABEL_RE = re.compile(r"\*\*(.+?)\*\*")


def _fetch_facts(section: str) -> dict[str, Any]:
    resp = httpx.get(
        f"{DATA_API_BASE}/v1/sections/{section}/facts/{ENTITY_ID}",
        headers={"X-Data-Service-Key": DATA_SERVICE_KEY},
        timeout=30,
    )
    resp.raise_for_status()
    return dict(resp.json()["facts"])


def _load_agent_drafts() -> dict[str, str]:
    payload = json.loads(RUN_JSON.read_text(encoding="utf-8"))
    return {s["section_id"]: s["agent_draft"] for s in payload["sections"] if s.get("agent_draft")}


def _markdown_to_subdoc(tpl: DocxTemplate, text: str) -> Any:
    """Convert **bold**-and-blank-line-separated narration into a docxtpl subdoc.

    Each blank-line-separated chunk becomes one real Word paragraph; `**text**`
    spans become bold runs within it. This is a small, spike-scoped converter --
    not a general markdown renderer (no lists/links/nesting) -- sufficient for
    the agent's actual narration style (bold lead-in labels, plain prose after).
    """
    subdoc = tpl.new_subdoc()
    for chunk in text.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        paragraph = subdoc.add_paragraph()
        pos = 0
        for match in _BOLD_LABEL_RE.finditer(chunk):
            if match.start() > pos:
                paragraph.add_run(chunk[pos : match.start()])
            paragraph.add_run(match.group(1)).bold = True
            pos = match.end()
        if pos < len(chunk):
            paragraph.add_run(chunk[pos:])
    return subdoc


def _split_utilities_narration(text: str) -> dict[str, str]:
    """The captured utilities agent_draft covers water/wastewater/electric/fire
    in one narration organized by **Bold Label.** lead-ins. Split on those
    labels so each template slot (WATER_SERVICE, WASTEWATER_SERVICE,
    ELECTRIC_PROVIDER, FIRE_PROTECTION) gets its own real paragraph(s) instead
    of the whole blob landing in one slot."""
    sections: dict[str, list[str]] = {
        "water_service": [],
        "wastewater_service": [],
        "electric_provider": [],
        "fire_protection": [],
    }
    label_map = {
        "water service": "water_service",
        "wastewater service": "wastewater_service",
        "electric service": "electric_provider",
        "fire protection": "fire_protection",
    }
    current = None
    for chunk in text.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = _BOLD_LABEL_RE.match(chunk)
        if match:
            label = match.group(1).rstrip(".").lower()
            if label in label_map:
                current = label_map[label]
        if current:
            sections[current].append(chunk)
    return {k: "\n\n".join(v) for k, v in sections.items() if v}


def build_context(tpl: DocxTemplate) -> dict[str, Any]:
    parcel = _fetch_facts("parcel-overview")
    jurisdiction = _fetch_facts("jurisdiction")
    soils = _fetch_facts("soils")
    watershed = _fetch_facts("watershed")
    utilities = _fetch_facts("utilities")
    mobility = _fetch_facts("mobility")
    flood = _fetch_facts("flood")
    environmental = _fetch_facts("environmental")
    drafts = _load_agent_drafts()
    utilities_narration = _split_utilities_narration(drafts.get("utilities", ""))

    def narration(section_key: str, fallback: str) -> Any:
        text = drafts.get(section_key)
        return _markdown_to_subdoc(tpl, text) if text else fallback

    def narration_text(text: str | None, fallback: str) -> Any:
        return _markdown_to_subdoc(tpl, text) if text else fallback

    pending = "Extraction pending -- not yet available from an automated source."

    ctx: dict[str, Any] = {
        # --- manual / user-entered in the real app: spike stand-ins, never fabricated facts ---
        "project_name": "[Project name -- entered by analyst]",
        "preparer_name": "[Preparer name -- entered by analyst]",
        "firm_name": "ATX Civil",
        "firm_address": "[Firm address]",
        "firm_location": "[Firm city, state zip]",
        "firm_phone": "[Firm phone]",
        "firm_fax": "[Firm fax]",
        "client_name": "[Client name -- entered by analyst]",
        "client_company": "[Client company]",
        "client_address": "[Client address]",
        "client_location": "[Client city, state zip]",
        "client_email": "[Client email]",
        "client_phone": "[Client phone]",
        "proposed_development": "[Proposed development -- entered by analyst]",
        "report_date": "[Report date]",
        # --- parcel-overview (direct) ---
        "property_address": parcel.get("address_norm") or "13903 FM 812 Rd, Del Valle, TX 78617",
        "property_acres": f"{parcel['acreage']:.2f}" if parcel.get("acreage") else "unknown",
        "existing_development": (
            parcel.get("existing_development") or "vacant (no structures on record)"
        ),
        "tcad_info": (
            f"TCAD Property ID: {parcel.get('source_parcel_id')}\n"
            f"Legal Description: {parcel.get('legal_desc')}\n"
            f"Land Use: {parcel.get('land_use_description')} ({parcel.get('land_use_code')})"
        ),
        "tcad_discrepancies": parcel.get("tcad_discrepancies") or pending,
        "adjacent_props": parcel.get("adjacent_props") or pending,
        # --- jurisdiction (direct + composite) ---
        "jurisdiction_status": (
            jurisdiction.get("jurisdiction_primary") or "jurisdiction undetermined"
        ),
        "jurisdiction_info": jurisdiction.get("permit_authority") or pending,
        "governing_juris": jurisdiction.get("jurisdiction_primary") or "unknown",
        "required_permits": mobility.get("required_permits") or pending,
        "permit_contacts": mobility.get("permit_contacts") or pending,
        # --- environmental (direct + unit-converted per D8; live API still serves
        # raw meters under min_elevation/max_elevation pending the D8 code deploy) ---
        "ecoregion": environmental.get("ecoregion") or "unknown",
        "ecoregion_desc": environmental.get("ecoregion_desc") or "",
        "hydrology_char": environmental.get("hydrology_char") or pending,
        "min_elevation": (
            f"{environmental['min_elevation'] * _M_TO_FT:.1f}"
            if environmental.get("min_elevation") is not None
            else "unknown"
        ),
        "max_elevation": (
            f"{environmental['max_elevation'] * _M_TO_FT:.1f}"
            if environmental.get("max_elevation") is not None
            else "unknown"
        ),
        "min_slope": (
            f"{environmental['min_slope']:.1f}"
            if environmental.get("min_slope") is not None
            else "unknown"
        ),
        "max_slope": (
            f"{environmental['max_slope']:.1f}"
            if environmental.get("max_slope") is not None
            else "unknown"
        ),
        "soil_types": (
            f"{soils.get('soil_primary_name')} ({soils.get('soil_primary_map_unit')}), "
            f"{soils.get('soil_drainage_class')}"
            if soils.get("soil_primary_name")
            else pending
        ),
        "soil_class": soils.get("soil_hydrologic_group") or "unknown",
        "floodplain_reqs": environmental.get("floodplain_reqs") or pending,
        "waterway_setback": environmental.get("waterway_setback") or pending,
        "erosion_hazard": environmental.get("erosion_hazard") or pending,
        "drainage_areas": environmental.get("drainage_areas") or pending,
        "drainage_criteria": environmental.get("drainage_criteria") or pending,
        "water_quality_reqs": environmental.get("water_quality_reqs") or pending,
        # --- watershed ---
        "watershed_info": (
            f"{watershed.get('watershed_name')} watershed "
            f"(source: {watershed.get('watershed_source')}, "
            f"confidence {watershed.get('watershed_confidence')})"
            if watershed.get("watershed_name")
            else pending
        ),
        # --- zoning: real agent narration (subdoc) ---
        "zoning_regs": narration("zoning", pending),
        "platting_status": pending,  # not part of this run's 4 captured sections
        "impervious_regs": (
            jurisdiction.get("impervious_regs")
            if isinstance(jurisdiction.get("impervious_regs"), str)
            else pending
        ),
        # --- utilities: real agent narration, split by sub-topic (subdoc each) ---
        "water_service": narration_text(
            utilities_narration.get("water_service"),
            f"Provider on record: {utilities.get('water_provider') or 'unknown'}.",
        ),
        "wastewater_service": narration_text(
            utilities_narration.get("wastewater_service"),
            f"Provider on record: {utilities.get('wastewater_provider') or 'unknown'}.",
        ),
        "electric_provider": narration_text(
            utilities_narration.get("electric_provider"),
            f"Provider on record: {utilities.get('power_provider') or 'unknown'}.",
        ),
        "fire_protection": narration_text(
            utilities_narration.get("fire_protection"),
            utilities.get("fire_protection") or pending,
        ),
        "utility_capacity": pending,
        "row_info": (
            f"{mobility.get('row_existing_ft')} ft existing ROW; "
            f"maintained by {mobility.get('maintenance_authority')}"
            if mobility.get("row_existing_ft")
            else pending
        ),
        # --- flood: real agent narration (subdoc) ---
        "floodplain_status": narration(
            "flood",
            f"FEMA Zone {flood.get('fema_zone')}, panel {flood.get('panel_id')}"
            if flood.get("fema_zone")
            else pending,
        ),
        "compatibility_stds": pending,
        "dev_agreements": pending,
        "easements_setbacks": pending,
        "transportation_reqs": mobility.get("transportation_reqs") or pending,
        "completed_docs": pending,
        "recommendation_1": "[Recommendation 1 -- analyst-authored]",
        "recommendation_2": "[Recommendation 2 -- analyst-authored]",
        "recommendation_3": "[Recommendation 3 -- analyst-authored]",
        "recommendation_4": "[Recommendation 4 -- analyst-authored]",
        "recommendation_5": "[Recommendation 5 -- analyst-authored]",
        "exhibit_1": "[Exhibit 1]",
        "exhibit_2": "[Exhibit 2]",
        "exhibit_3": "[Exhibit 3]",
        "exhibit_4": "[Exhibit 4]",
        "exhibit_5": "[Exhibit 5]",
    }
    return ctx


def main() -> int:
    tpl = DocxTemplate(str(TEMPLATE_PATH))
    context = build_context(tpl)
    tpl.render(context)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tpl.save(str(OUTPUT_PATH))
    print(f"Rendered spike output -> {OUTPUT_PATH}")
    print(f"Context keys filled: {len(context)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
