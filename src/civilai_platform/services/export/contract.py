"""Civil1 Study content contract — the platform-owned, skin-independent study model.

Source of truth: `CIVIL1-STUDY-FORMAT.md` §4. Section *IDs* are stable keys; a skin
(`skins.py`) maps them to its own heading numbers/titles and jinja tokens. Nothing here
knows about ACE outline numbers (`1.0`, `3.13.1`, …) or any single jurisdiction — that
is the whole point of the contract/skin split (format §3, §9.5).

`SlotType` classifies where a section's value comes from, which drives how the renderer
fills it and how the linter checks it:

- ``DETERMINISTIC`` — governed facts / determinations (data API) or project/tenant fields.
- ``NARRATION`` — user-edited editor prose (rendered via docxtpl Subdoc → real paragraphs).
- ``ENUM`` — a controlled value (e.g. the feasibility verdict).
- ``TABLE`` — a structured table (risk register).
- ``LIST`` — an ordered list (recommendations).
- ``DERIVED`` — computed from other content (exhibit list from callouts).
- ``BRANDING`` — tenant identity (logo, firm block).
- ``PROVENANCE`` — export/data lineage (skin version, serving snapshot).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SlotType(StrEnum):
    DETERMINISTIC = "deterministic"
    NARRATION = "narration"
    ENUM = "enum"
    TABLE = "table"
    LIST = "list"
    DERIVED = "derived"
    BRANDING = "branding"
    PROVENANCE = "provenance"


class SectionGroup(StrEnum):
    FRONT_MATTER = "front_matter"  # 4.0
    PURPOSE_PROPERTY = "purpose_property"  # A
    ENTITLEMENTS = "entitlements"  # B
    SITE_CONSTRAINTS = "site_constraints"  # C
    UTILITIES_ACCESS = "utilities_access"  # D
    VERDICT = "verdict"  # E
    EXHIBITS_PROVENANCE = "exhibits_provenance"  # F


@dataclass(frozen=True)
class ContractSection:
    """One slot in the content contract. `required` gates the linter's presence check."""

    id: str
    title: str
    group: SectionGroup
    slot_type: SlotType
    required: bool = True


# The Civil1 Study content contract, in canonical document order (format §4).
CONTRACT_SECTIONS: tuple[ContractSection, ...] = (
    # 4.0 Front matter --------------------------------------------------------------
    ContractSection("firm_block", "Firm / Cover", SectionGroup.FRONT_MATTER, SlotType.BRANDING),
    ContractSection("client_block", "Client", SectionGroup.FRONT_MATTER, SlotType.DETERMINISTIC),
    ContractSection(
        "project_meta",
        "Project / Proposed Development / Date",
        SectionGroup.FRONT_MATTER,
        SlotType.DETERMINISTIC,
    ),
    ContractSection(
        "preparer", "Preparer / PE Credentials", SectionGroup.FRONT_MATTER, SlotType.DETERMINISTIC
    ),
    ContractSection("data_vintage", "Data Vintage", SectionGroup.FRONT_MATTER, SlotType.PROVENANCE),
    # A. Purpose & property ---------------------------------------------------------
    ContractSection(
        "purpose_scope", "Purpose & Scope", SectionGroup.PURPOSE_PROPERTY, SlotType.DETERMINISTIC
    ),
    ContractSection(
        "site_overview", "Site Overview", SectionGroup.PURPOSE_PROPERTY, SlotType.NARRATION
    ),
    ContractSection(
        "property_id",
        "Property Identification",
        SectionGroup.PURPOSE_PROPERTY,
        SlotType.DETERMINISTIC,
    ),
    ContractSection(
        "adjacent_context",
        "Adjacent Sites & Context",
        SectionGroup.PURPOSE_PROPERTY,
        SlotType.NARRATION,
    ),
    # B. Entitlements & administration ---------------------------------------------
    ContractSection("zoning", "Zoning & Land Use", SectionGroup.ENTITLEMENTS, SlotType.NARRATION),
    ContractSection(
        "platting", "Platting & Subdivision", SectionGroup.ENTITLEMENTS, SlotType.NARRATION
    ),
    ContractSection(
        "compatibility",
        "Compatibility & Design Standards",
        SectionGroup.ENTITLEMENTS,
        SlotType.NARRATION,
    ),
    ContractSection(
        "governing_jurisdictions",
        "Governing Jurisdictions",
        SectionGroup.ENTITLEMENTS,
        SlotType.DETERMINISTIC,
    ),
    ContractSection(
        "required_permits", "Required Permits", SectionGroup.ENTITLEMENTS, SlotType.NARRATION
    ),
    ContractSection(
        "permit_contacts",
        "Permitting Contacts",
        SectionGroup.ENTITLEMENTS,
        SlotType.DETERMINISTIC,
    ),
    ContractSection(
        "development_agreements",
        "Development Agreements",
        SectionGroup.ENTITLEMENTS,
        SlotType.NARRATION,
        required=False,
    ),
    ContractSection(
        "easements_setbacks", "Easements & Setbacks", SectionGroup.ENTITLEMENTS, SlotType.NARRATION
    ),
    ContractSection(
        "surveys_title",
        "Surveys, Title & Other Documents",
        SectionGroup.ENTITLEMENTS,
        SlotType.NARRATION,
    ),
    # C. Site constraints -----------------------------------------------------------
    ContractSection(
        "watershed", "Watershed & Waterways", SectionGroup.SITE_CONSTRAINTS, SlotType.NARRATION
    ),
    ContractSection(
        "impervious_cover", "Impervious Cover", SectionGroup.SITE_CONSTRAINTS, SlotType.NARRATION
    ),
    ContractSection(
        "soils_topo",
        "Soils, Elevation & Topography",
        SectionGroup.SITE_CONSTRAINTS,
        SlotType.DETERMINISTIC,
    ),
    ContractSection(
        "floodplain", "Floodplain Status", SectionGroup.SITE_CONSTRAINTS, SlotType.NARRATION
    ),
    ContractSection(
        "floodplain_study",
        "Floodplain Study Requirements",
        SectionGroup.SITE_CONSTRAINTS,
        SlotType.NARRATION,
        required=False,
    ),
    ContractSection(
        "drainage",
        "Drainage Areas & Design Criteria",
        SectionGroup.SITE_CONSTRAINTS,
        SlotType.NARRATION,
    ),
    ContractSection(
        "water_quality",
        "Water Quality & Detention",
        SectionGroup.SITE_CONSTRAINTS,
        SlotType.NARRATION,
    ),
    ContractSection(
        "environmental",
        "Environmental Overlays",
        SectionGroup.SITE_CONSTRAINTS,
        SlotType.NARRATION,
    ),
    # D. Utilities, access & mobility ----------------------------------------------
    ContractSection(
        "water_service", "Water Service", SectionGroup.UTILITIES_ACCESS, SlotType.NARRATION
    ),
    ContractSection(
        "wastewater_service",
        "Wastewater Service",
        SectionGroup.UTILITIES_ACCESS,
        SlotType.NARRATION,
    ),
    ContractSection(
        "electric_service", "Electric Service", SectionGroup.UTILITIES_ACCESS, SlotType.NARRATION
    ),
    ContractSection(
        "fire_protection", "Fire Protection", SectionGroup.UTILITIES_ACCESS, SlotType.NARRATION
    ),
    ContractSection(
        "utility_capacity",
        "Utility Capacity",
        SectionGroup.UTILITIES_ACCESS,
        SlotType.NARRATION,
        required=False,
    ),
    ContractSection(
        "right_of_way", "Right-of-Way", SectionGroup.UTILITIES_ACCESS, SlotType.NARRATION
    ),
    ContractSection(
        "transportation",
        "Transportation & Access",
        SectionGroup.UTILITIES_ACCESS,
        SlotType.NARRATION,
    ),
    # E. Verdict --------------------------------------------------------------------
    ContractSection("verdict", "Feasibility Verdict", SectionGroup.VERDICT, SlotType.ENUM),
    ContractSection(
        "verdict_narrative", "Verdict Narrative", SectionGroup.VERDICT, SlotType.NARRATION
    ),
    ContractSection(
        "risk_register", "Risk Register", SectionGroup.VERDICT, SlotType.TABLE, required=False
    ),
    ContractSection("recommendations", "Recommendations", SectionGroup.VERDICT, SlotType.LIST),
    ContractSection(
        "constraint_dashboard",
        "Constraint Dashboard",
        SectionGroup.VERDICT,
        SlotType.TABLE,
        required=False,
    ),
    # F. Exhibits & provenance ------------------------------------------------------
    ContractSection(
        "exhibit_list", "List of Exhibits", SectionGroup.EXHIBITS_PROVENANCE, SlotType.DERIVED
    ),
    ContractSection(
        "exhibit_sheets",
        "Exhibit Sheets",
        SectionGroup.EXHIBITS_PROVENANCE,
        SlotType.DERIVED,
        required=False,
    ),
    ContractSection(
        "sources_appendix",
        "Sources & Data-Vintage Appendix",
        SectionGroup.EXHIBITS_PROVENANCE,
        SlotType.DETERMINISTIC,
        required=False,
    ),
    ContractSection(
        "export_provenance",
        "Export Provenance",
        SectionGroup.EXHIBITS_PROVENANCE,
        SlotType.PROVENANCE,
    ),
)

# Fast lookups.
CONTRACT_SECTIONS_BY_ID: dict[str, ContractSection] = {s.id: s for s in CONTRACT_SECTIONS}

NARRATION_SECTION_IDS: frozenset[str] = frozenset(
    s.id for s in CONTRACT_SECTIONS if s.slot_type is SlotType.NARRATION
)

REQUIRED_SECTION_IDS: frozenset[str] = frozenset(s.id for s in CONTRACT_SECTIONS if s.required)


def contract_section(section_id: str) -> ContractSection | None:
    return CONTRACT_SECTIONS_BY_ID.get(section_id)
