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
_PENDING_PLACEHOLDER = "Pending user input."

# US street-ish phrases used to rewrite alternate situs → canonical project address.
# Street type must follow soon after the house number (avoids matching "78753 in … FARLEY DR").
_STREET_ADDR_RE = re.compile(
    r"\b(?P<num>\d{1,5})\s+"
    r"(?P<name>(?:[A-Za-z0-9.'\-]+\s+){0,4}[A-Za-z0-9.'\-]+)\s+"
    r"(?P<suf>St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Rd|Road|Ln|Lane|"
    r"Ct|Court|Cir|Circle|Way|Hwy|Highway|Pkwy|Parkway|Trl|Trail|Loop)\b\.?"
    r"(?P<tail>(?:\s*,\s*[A-Za-z][A-Za-z .'\-]*){0,2}"
    r"(?:\s*,?\s*(?:TX|Texas)\b)?"
    r"(?:\s+\d{5}(?:-\d{4})?)?)",
    re.IGNORECASE,
)


def _normalize_identity(value: str) -> str:
    """Compare project name vs address without punctuation/case noise."""
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _street_core(value: str) -> str:
    """Normalize to house-number + street tokens (drop city/state/zip)."""
    text = value.strip()
    if "," in text:
        text = text.split(",", 1)[0]
    text = re.sub(
        r"\b(street|st|avenue|ave|boulevard|blvd|drive|dr|road|rd|lane|ln|"
        r"court|ct|circle|cir|way|highway|hwy|parkway|pkwy|trail|trl|loop)\b\.?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return _normalize_identity(text)


def _is_pending_or_empty(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    # TipTap may wrap the placeholder in tags; compare plain-ish.
    plain = re.sub(r"<[^>]+>", "", cleaned).strip()
    plain = re.sub(r"^[\s*_]+|[\s*_]+$", "", plain)
    return plain.casefold() == _PENDING_PLACEHOLDER.casefold()


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


def pin_narration_to_canonical_address(text: str, canonical: str) -> str:
    """Rewrite alternate situs phrases in narration to the project canonical address.

    Multi-situs same-entity parcels (e.g. Farley / Braker) often leave cover on the
    typed address while LLM drafts speak the CAD situs. Prefer the project address.
    """
    canonical = canonical.strip()
    if not text or not canonical:
        return text
    canon_core = _street_core(canonical)
    if not canon_core:
        return text

    def _replace(match: re.Match[str]) -> str:
        found = match.group(0)
        name = match.group("name") or ""
        # Reject spans that jumped past sentence/context words to a later road name.
        if re.search(r"\b(in|on|at|near|frontage|county|city)\b", name, re.IGNORECASE):
            return found
        found_core = _street_core(found)
        if not found_core or found_core == canon_core:
            return found
        if not re.match(r"^\d+", found_core) or not re.match(r"^\d+", canon_core):
            return found
        return canonical

    return _STREET_ADDR_RE.sub(_replace, text)


def _field_values(state: ProjectState) -> dict[str, str]:
    values: dict[str, str] = {}
    for section in state.sections:
        for key, field_value in section.fields.items():
            value = str(field_value.value or "").strip()
            if value:
                values[key] = value
                values[key.lower()] = value
    if state.site_context:
        for key, field_value in state.site_context.items():
            value = str(field_value.value or "").strip()
            if value:
                values.setdefault(key, value)
                values.setdefault(key.lower(), value)
    return values


def _site_payload_codes(site_payload: dict[str, Any]) -> dict[str, str]:
    """Flatten FieldView lists in site_payload into code → display value."""
    out: dict[str, str] = {}
    for key, value in site_payload.items():
        if key in {"entity_id", "serving_source", "snapshot", "parcel_candidates"}:
            continue
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()
            raw = item.get("value")
            if raw is None:
                continue
            text = str(raw).strip()
            if not code or not text:
                continue
            out[code] = text
            out[code.lower()] = text
    return out


def _pick(values: dict[str, str], *keys: str, default: str = _MISSING) -> str:
    for key in keys:
        value = values.get(key) or values.get(key.lower()) or values.get(key.upper())
        if value:
            return value
    return default


def _section_bodies(state: ProjectState, *, canonical_address: str) -> dict[str, str]:
    bodies: dict[str, str] = {}
    for section in state.sections:
        text = editor_body_to_text(section.body)
        if _is_pending_or_empty(text):
            continue
        text = pin_narration_to_canonical_address(text, canonical_address)
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


def _parse_recommendation_lines(text: str) -> list[str]:
    if _is_pending_or_empty(text):
        return []
    lines: list[str] = []
    for line in text.splitlines():
        cleaned = re.sub(r"^[•*\-\d.)\s]+", "", line).strip()
        if cleaned and not _is_pending_or_empty(cleaned):
            lines.append(cleaned)
    return lines[:5]


def derive_recommendations(
    *,
    fields: dict[str, str],
    bodies: dict[str, str],
    property_address: str,
) -> list[str]:
    """Deterministic Priority Recommendations when the exhibits step is empty."""
    bullets: list[str] = []

    def add(text: str) -> None:
        if text and text not in bullets and len(bullets) < 5:
            bullets.append(text)

    plat = _pick(fields, "platting_status", "PLATTING_STATUS", default="").lower()
    if not plat or "undetermined" in plat or "could not" in plat or "pending" in plat:
        add(
            "Confirm recorded-plat / title status for the subject tract before site-plan "
            "submittal (County clerk + CAD legal description)."
        )

    historic = _pick(
        fields, "historic_status", "HISTORIC_STATUS", "historic_designation", default=""
    ).lower()
    if "needs_review" in historic or "could not" in historic or not historic:
        add(
            "Verify historic-landmark and zoning-overlay status with the governing "
            "municipality before design lock."
        )

    tia = _pick(fields, "tia_status", "TIA_STATUS", "tia_applicability", default="").lower()
    access_body = (bodies.get("access") or "").lower()
    if "needs_review" in tia or "tia" in access_body and "must be determined" in access_body:
        add(
            "Complete trip-generation screening against local TIA thresholds for the "
            "proposed use; confirm whether a formal TIA is required."
        )

    flood = _pick(fields, "flood_zone", "FLOOD_ZONE", "fema_zone", default="").lower()
    env = (bodies.get("environmental") or "").lower()
    if "zone x" in flood or "zone x" in env:
        add(
            "FEMA Zone X: no NFIP floodplain study is indicated from mapped SFHA status; "
            "confirm local drainage / water-quality criteria still apply."
        )

    utilities = (bodies.get("utilities") or "").lower()
    if "will-serve" in utilities or "capacity" in utilities or "coordination" in utilities:
        add(
            "Coordinate early with water, wastewater, and electric providers to confirm "
            "connection points and capacity (service territory is not a will-serve)."
        )

    if property_address:
        add(
            f"Validate all exhibit sheets and CAD extracts against the project address "
            f"({property_address}) before client delivery."
        )

    # Ensure we always return something useful for Priority Recommendations.
    if not bullets:
        add(
            "Confirm governing jurisdiction, required permits, and utility connection "
            "feasibility before schematic design."
        )
    return bullets[:5]


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

    property_address = (project.address or "").strip()
    fields = _field_values(state)
    site_payload = state.site_payload or {}
    # Merge governed codes from site_payload so ATX slots fill when fields are empty.
    for code, value in _site_payload_codes(site_payload).items():
        fields.setdefault(code, value)
        fields.setdefault(code.lower(), value)

    bodies = _section_bodies(state, canonical_address=property_address)
    utilities = _split_labeled_body(bodies.get("utilities", ""))

    parcel = state.parcel or {}
    acreage = _pick(fields, "acreage", "property_acres", "lot_size_acres", "ACREAGE")
    if acreage == _MISSING and parcel.get("lotSizeSqft"):
        acreage = f"{float(parcel['lotSizeSqft']) / 43560:.2f}"

    recommendations = _parse_recommendation_lines(bodies.get("exhibits", ""))
    if not recommendations:
        recommendations = derive_recommendations(
            fields=fields,
            bodies=bodies,
            property_address=property_address,
        )

    # Cover identity lines render *blank* when unknown -- ACE's delivered covers simply
    # omit lines they don't have; printing "Not available..." six times on a cover is a
    # presentation defect, not honesty (facts in the body keep the explicit missing text).
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
        "existing_development": _pick(
            fields, "existing_development", "existing_land_use", "LAND_USE", "land_use"
        ),
        "tcad_info": _pick(
            fields, "tcad_info", "legal_desc", "legal_description", "LEGAL_DESCRIPTION"
        ),
        "tcad_discrepancies": _pick(fields, "tcad_discrepancies"),
        "adjacent_props": bodies.get("parcel") or _pick(fields, "adjacent_props"),
        "jurisdiction_status": project.jurisdiction
        or _pick(fields, "jurisdiction_primary", "JURISDICTION_PRIMARY"),
        "jurisdiction_info": _pick(fields, "permit_authority", "jurisdiction_info"),
        "governing_juris": project.jurisdiction
        or _pick(fields, "jurisdiction_primary", "JURISDICTION_PRIMARY"),
        "required_permits": _pick(fields, "required_permits", "REQUIRED_PERMITS"),
        "permit_contacts": _pick(fields, "permit_contacts", "PERMIT_CONTACTS"),
        "ecoregion": _pick(fields, "ecoregion", "ECOREGION"),
        "ecoregion_desc": _pick(fields, "ecoregion_desc", "ECOREGION_DESC"),
        "hydrology_char": _pick(fields, "hydrology_char", "HYDROLOGY_CHAR"),
        "min_elevation": _pick(
            fields, "min_elevation_ft", "min_elevation", "MIN_ELEVATION", "ELEVATION_MIN"
        ),
        "max_elevation": _pick(
            fields, "max_elevation_ft", "max_elevation", "MAX_ELEVATION", "ELEVATION_MAX"
        ),
        "min_slope": _pick(fields, "min_slope_pct", "min_slope", "MIN_SLOPE", "SLOPE_MIN"),
        "max_slope": _pick(fields, "max_slope_pct", "max_slope", "MAX_SLOPE", "SLOPE_MAX"),
        "soil_types": _pick(fields, "soil_types", "soil_primary_name", "SOIL_PRIMARY_NAME"),
        "soil_class": _pick(
            fields, "soil_hydrologic_group", "soil_class", "SOIL_HYDROLOGIC_GROUP"
        ),
        "floodplain_reqs": _pick(fields, "floodplain_reqs", "FLOODPLAIN_REQS"),
        "waterway_setback": _pick(
            fields, "waterway_setback", "cwqz_setback_ft", "CWQZ_SETBACK_FT"
        ),
        "erosion_hazard": _pick(fields, "erosion_hazard", "EROSION_HAZARD"),
        "drainage_areas": _pick(fields, "drainage_areas", "DRAINAGE_AREAS"),
        "drainage_criteria": _pick(fields, "drainage_criteria", "DRAINAGE_CRITERIA"),
        "water_quality_reqs": _pick(fields, "water_quality_reqs", "WATER_QUALITY_REQS"),
        "watershed_info": _pick(fields, "watershed_name", "watershed_info", "WATERSHED_NAME"),
        "platting_status": _pick(fields, "platting_status", "PLATTING_STATUS"),
        "impervious_regs": _pick(
            fields, "impervious_regs", "impervious_cover", "IMPERVIOUS_COVER"
        ),
        "utility_capacity": _pick(fields, "utility_capacity", "UTILITY_CAPACITY"),
        "row_info": _pick(
            fields, "row_info", "row_existing_ft", "ROW_EXISTING_FT", "row_required_ft"
        ),
        "compatibility_stds": _pick(fields, "compatibility_stds", "COMPATIBILITY_STDS"),
        "dev_agreements": _pick(fields, "development_agreements", "DEVELOPMENT_AGREEMENTS"),
        "easements_setbacks": _pick(fields, "easements_setbacks", "EASEMENTS_SETBACKS"),
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
    # Pin narration the same way as bodies (utilities split may still carry alternate situs).
    narration = {
        key: pin_narration_to_canonical_address(val, property_address)
        if val != _MISSING
        else val
        for key, val in narration.items()
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
        "canonical_address": property_address or None,
        "recommendations_derived": not bool(
            _parse_recommendation_lines(
                editor_body_to_text(
                    next(
                        (s.body for s in state.sections if s.step_key == "exhibits"),
                        "",
                    )
                )
            )
        ),
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
