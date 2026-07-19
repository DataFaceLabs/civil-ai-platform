"""Assemble skin-independent export inputs from persisted project state.

Editor bodies are authoritative for narration. Persisted fields provide deterministic
values and provenance; the renderer does not ask an LLM to reshape the document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any

from civilai_platform.models.entities import MapExhibit, ProjectState
from civilai_platform.services import artifacts as artifact_svc
from civilai_platform.store.base import PlatformStore

_MISSING = "Not available from current project data."


def _normalize_identity(value: str) -> str:
    """Compare project name vs address without punctuation/case noise."""
    return re.sub(r"[^a-z0-9]+", "", value.casefold())



class _PlainTextParser(HTMLParser):
    _BLOCKS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "blockquote"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._BLOCKS and self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("• ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def editor_body_to_text(value: str) -> str:
    """Turn TipTap HTML (or markdown-ish plain text) into paragraph-separated text."""
    if "<" not in value:
        return value.strip()
    parser = _PlainTextParser()
    parser.feed(value)
    text = unescape("".join(parser.parts))
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _field_values(state: ProjectState) -> dict[str, str]:
    values: dict[str, str] = {}
    for section in state.sections:
        for key, field_value in section.fields.items():
            value = str(field_value.value or "").strip()
            if value:
                values[key] = value
    if state.site_context:
        for key, field_value in state.site_context.items():
            value = str(field_value.value or "").strip()
            if value:
                values.setdefault(key, value)
    return values


def _pick(values: dict[str, str], *keys: str, default: str = _MISSING) -> str:
    for key in keys:
        value = values.get(key)
        if value:
            return value
    return default


def _section_bodies(state: ProjectState) -> dict[str, str]:
    bodies: dict[str, str] = {}
    for section in state.sections:
        text = editor_body_to_text(section.body)
        if text:
            bodies[section.step_key] = text
            bodies[section.id] = text
    return bodies


def _split_labeled_body(text: str) -> dict[str, str]:
    """Split a utilities draft on common bold/plain labels without inventing content."""
    labels = {
        "water service": "water_service",
        "wastewater service": "wastewater_service",
        "electric service": "electric_provider",
        "fire protection": "fire_protection",
    }
    result: dict[str, list[str]] = {value: [] for value in labels.values()}
    current: str | None = None
    for paragraph in re.split(r"\n\s*\n", text):
        clean = paragraph.strip()
        if not clean:
            continue
        normalized = re.sub(r"^\*{0,2}([^:*]+?)[:.]\*{0,2}\s*", r"\1: ", clean)
        prefix = normalized.split(":", 1)[0].strip().lower()
        if prefix in labels:
            current = labels[prefix]
        if current:
            result[current].append(clean)
    return {key: "\n\n".join(parts) for key, parts in result.items() if parts}


@dataclass(frozen=True)
class ExportContext:
    skin_id: str
    template_values: dict[str, str]
    narration: dict[str, str]
    exhibits: tuple[MapExhibit, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    # Raw bytes of the tenant's uploaded cover logo (BRANDING slot). The renderer turns
    # this into a docxtpl InlineImage; skins without a `customer_logo` token ignore it.
    customer_logo: bytes | None = None


def build_export_context(
    store: PlatformStore,
    *,
    tenant_id: str,
    project_id: str,
    skin_id: str,
    data_api_base: str | None,
    job_id: str,
) -> ExportContext:
    tenant = store.get_tenant(tenant_id)
    project = store.get_project(tenant_id, project_id)
    state = store.get_project_state(tenant_id, project_id)
    if not tenant or not project or not state:
        raise ValueError("project, tenant, or project state not found")

    client = store.get_client(tenant_id, project.client_id) if project.client_id else None
    contact = state.client_contacts[0] if state.client_contacts else None
    if not contact and client and client.contacts:
        contact = client.contacts[0]

    fields = _field_values(state)
    bodies = _section_bodies(state)
    utilities = _split_labeled_body(bodies.get("utilities", ""))

    parcel = state.parcel or {}
    site_payload = state.site_payload or {}
    acreage = _pick(fields, "acreage", "property_acres", "lot_size_acres")
    if acreage == _MISSING and parcel.get("lotSizeSqft"):
        acreage = f"{float(parcel['lotSizeSqft']) / 43560:.2f}"

    recommendations_text = bodies.get("exhibits", "")
    recommendations = [
        re.sub(r"^[•*\-\d.)\s]+", "", line).strip()
        for line in recommendations_text.splitlines()
        if re.sub(r"^[•*\-\d.)\s]+", "", line).strip()
    ][:5]

    # Cover identity lines render *blank* when unknown -- ACE's delivered covers simply
    # omit lines they don't have; printing "Not available..." six times on a cover is a
    # presentation defect, not honesty (facts in the body keep the explicit missing text).
    property_address = (project.address or "").strip()
    project_name = (project.name or "").strip()
    # When the project was named as the street address, only print it once on the cover.
    cover_project_name = (
        ""
        if project_name
        and property_address
        and _normalize_identity(project_name) == _normalize_identity(property_address)
        else project_name
    )
    values: dict[str, str] = {
        "project_name": project_name or property_address,
        "cover_project_name": cover_project_name,
        "preparer_name": _pick(fields, "preparer_name", default=""),
        "firm_name": tenant.name,
        "firm_address": tenant.address or "",
        "firm_location": tenant.location or "",
        "firm_phone": tenant.phone or "",
        "firm_fax": tenant.fax or "",
        "client_name": client.name if client else "",
        "client_company": client.name if client else "",
        "client_address": client.address if client and client.address else "",
        "client_location": client.location if client and client.location else "",
        "client_email": contact.email if contact else "",
        "client_phone": contact.phone if contact else "",
        "proposed_development": state.proposed_use or _MISSING,
        "report_date": datetime.now(UTC).date().isoformat(),
        "property_address": property_address,
        "property_acres": acreage,
        "existing_development": _pick(fields, "existing_development", "existing_land_use"),
        "tcad_info": _pick(fields, "tcad_info", "legal_desc", "legal_description"),
        "tcad_discrepancies": _pick(fields, "tcad_discrepancies"),
        "adjacent_props": bodies.get("parcel") or _pick(fields, "adjacent_props"),
        "jurisdiction_status": project.jurisdiction or _pick(fields, "jurisdiction_primary"),
        "jurisdiction_info": _pick(fields, "permit_authority", "jurisdiction_info"),
        "governing_juris": project.jurisdiction or _pick(fields, "jurisdiction_primary"),
        "required_permits": _pick(fields, "required_permits"),
        "permit_contacts": _pick(fields, "permit_contacts"),
        "ecoregion": _pick(fields, "ecoregion"),
        "ecoregion_desc": _pick(fields, "ecoregion_desc"),
        "hydrology_char": _pick(fields, "hydrology_char"),
        "min_elevation": _pick(fields, "min_elevation_ft", "min_elevation"),
        "max_elevation": _pick(fields, "max_elevation_ft", "max_elevation"),
        "min_slope": _pick(fields, "min_slope_pct", "min_slope"),
        "max_slope": _pick(fields, "max_slope_pct", "max_slope"),
        "soil_types": _pick(fields, "soil_types", "soil_primary_name"),
        "soil_class": _pick(fields, "soil_hydrologic_group", "soil_class"),
        "floodplain_reqs": _pick(fields, "floodplain_reqs"),
        "waterway_setback": _pick(fields, "waterway_setback", "cwqz_setback_ft"),
        "erosion_hazard": _pick(fields, "erosion_hazard"),
        "drainage_areas": _pick(fields, "drainage_areas"),
        "drainage_criteria": _pick(fields, "drainage_criteria"),
        "water_quality_reqs": _pick(fields, "water_quality_reqs"),
        "watershed_info": _pick(fields, "watershed_name", "watershed_info"),
        "platting_status": _pick(fields, "platting_status"),
        "impervious_regs": _pick(fields, "impervious_regs", "impervious_cover"),
        "utility_capacity": _pick(fields, "utility_capacity"),
        "row_info": _pick(fields, "row_info", "row_existing_ft"),
        "compatibility_stds": _pick(fields, "compatibility_stds"),
        "dev_agreements": _pick(fields, "development_agreements"),
        "easements_setbacks": _pick(fields, "easements_setbacks"),
        "transportation_reqs": bodies.get("access") or _pick(fields, "transportation_reqs"),
        "completed_docs": _pick(fields, "completed_docs"),
    }
    for index in range(1, 6):
        # Empty unused slots (not _MISSING) so the skin can omit list/table rows.
        values[f"recommendation_{index}"] = (
            recommendations[index - 1] if len(recommendations) >= index else ""
        )
        values[f"exhibit_{index}"] = (
            (state.map_exhibits[index - 1].label or state.map_exhibits[index - 1].name)
            if len(state.map_exhibits) >= index
            else ""
        )

    narration = {
        "zoning_regs": bodies.get("zoning") or _MISSING,
        "floodplain_status": bodies.get("environmental") or _MISSING,
        "water_service": utilities.get("water_service") or bodies.get("utilities") or _MISSING,
        "wastewater_service": utilities.get("wastewater_service") or _MISSING,
        "electric_provider": utilities.get("electric_provider") or _MISSING,
        "fire_protection": utilities.get("fire_protection") or _MISSING,
    }
    entity_id = str(site_payload.get("entity_id") or "").strip() or None
    serving_source = site_payload.get("serving_source") or site_payload.get("snapshot")
    provenance = {
        "export_job_id": job_id,
        "skin_id": skin_id,
        "skin_version": "1",
        "entity_id": entity_id,
        "serving_source": serving_source,
        "data_plane": "dev"
        if data_api_base and data_api_base.rstrip("/").endswith(":8001")
        else "prod",
        "generated_at": datetime.now(UTC).isoformat(),
    }
    customer_logo = (
        artifact_svc.download_artifact_bytes(tenant.logo_s3_key)
        if tenant.logo_s3_key
        else None
    )
    return ExportContext(
        skin_id=skin_id,
        template_values=values,
        narration=narration,
        exhibits=tuple(state.map_exhibits),
        provenance=provenance,
        customer_logo=customer_logo,
    )
