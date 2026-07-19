"""Presentation skins — the tenant-selected Word `.docx` a content contract renders into.

A skin owns *presentation only*: cover, fonts, heading numbers/titles, boilerplate voice,
and the jinja token vocabulary in its `.docx`. The same `ExportContext` (built against
`contract.py`) fills any skin. Tenants pick a skin; the platform never hardcodes one skin's
outline into the service core (`CIVIL1-STUDY-FORMAT.md` §3, §3.5).

Tier model (format §3.5):
- Tier 1 — the Civil1 default skin (`civil1_study_v1`), tenant logo/firm block.
- Tier 2 — a converted house template (`atxcivil_v1` is the first), via
  `scripts/docxtpl_convert_template.py` + a human-verified section→token mapping.
- Tier 3 — runtime arbitrary-DOCX adherence: **not offered** (can't be filled/linted).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def _templates_dir() -> Path:
    here = Path(__file__).resolve()
    # Source checkout: <repo>/src/civilai_platform/...; Lambda: /var/task/civilai_platform/...
    candidates = (
        here.parents[4] / "assets" / "templates",
        here.parents[3] / "assets" / "templates",
    )
    return next((candidate for candidate in candidates if candidate.exists()), candidates[0])


TEMPLATES_DIR = _templates_dir()

# Default skin when a tenant has no explicit selection. ATX-faithful ships first for
# parity demos; flips to civil1_study_v1 once the design skin lands (M1-DESIGN / X5).
DEFAULT_SKIN_ID = "atxcivil_v1"


@dataclass(frozen=True)
class Skin:
    """A renderable presentation skin.

    ``narration_tokens`` are the jinja tokens fed a docxtpl Subdoc (real multi-paragraph
    prose); they use the ``{{p token }}`` paragraph-tag form and silently render blank
    under an inline tag, so the renderer must treat them specially (verified in E1).

    ``outline`` is this skin's expected Heading outline-number sequence — the per-skin
    input to the export linter's heading-sequence check (was global in E6).
    """

    id: str
    display_name: str
    template_filename: str
    tier: int
    narration_tokens: frozenset[str] = field(default_factory=frozenset)
    outline: tuple[str, ...] = ()
    available: bool = True

    @property
    def template_path(self) -> Path:
        return TEMPLATES_DIR / self.template_filename


# --- atxcivil_v1: the first Tier-2 house skin (converted + proven end-to-end in E1) ------
# Subdoc tokens verified in scripts/docxtpl_convert_template.py::SUBDOC_TOKENS and rendered
# in scripts/docxtpl_spike_render.py.
_ATXCIVIL_NARRATION_TOKENS = frozenset(
    {
        "zoning_regs",
        "water_service",
        "wastewater_service",
        "electric_provider",
        "fire_protection",
        "floodplain_status",
    }
)

# The ACE template outline (client-data/ATXCivil_Feasibility_Template.docx), verified
# 2026-07-15 — mirrors scripts/lint_export_docx.py::EXPECTED_OUTLINE. Owned here now so the
# linter check is per-skin.
_ATXCIVIL_OUTLINE = (
    "1", "2", "2.1", "2.2", "2.3", "3", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7",
    "3.8", "3.9", "3.10", "3.11", "3.12", "3.13", "3.13.1", "3.13.2", "3.14", "3.15",
    "3.16", "3.17", "3.18", "3.19", "4", "EXHIBITS",
)  # fmt: skip

ATXCIVIL_V1 = Skin(
    id="atxcivil_v1",
    display_name="ATX Civil (house template)",
    template_filename="atxcivil_v1.docx",
    tier=2,
    narration_tokens=_ATXCIVIL_NARRATION_TOKENS,
    outline=_ATXCIVIL_OUTLINE,
    available=True,
)

# --- civil1_study_v1: the default Civil1 skin — built in M1-DESIGN, shipped in X5 --------
# Registered now so routing/selection code can reference it; not yet renderable.
CIVIL1_STUDY_V1 = Skin(
    id="civil1_study_v1",
    display_name="Civil1 Study",
    template_filename="civil1_study_v1.docx",
    tier=1,
    narration_tokens=frozenset(),
    outline=(),
    available=False,
)


SKINS: dict[str, Skin] = {
    ATXCIVIL_V1.id: ATXCIVIL_V1,
    CIVIL1_STUDY_V1.id: CIVIL1_STUDY_V1,
}


def get_skin(skin_id: str | None) -> Skin:
    """Resolve a skin id to a renderable skin, failing closed to the default.

    An unknown id or an unavailable skin (e.g. civil1_study_v1 before DESIGN lands) falls
    back to the default so an export never hard-fails on skin selection alone.
    """
    if skin_id:
        skin = SKINS.get(skin_id)
        if skin is not None and skin.available:
            return skin
    default = SKINS[DEFAULT_SKIN_ID]
    if not default.available:  # pragma: no cover - default must always be renderable
        raise RuntimeError(f"default skin {DEFAULT_SKIN_ID!r} is not available")
    return default


def resolve_skin_id_for_tenant(export_skin: str | None) -> str:
    """Map a tenant's stored `export_skin` preference to a renderable skin id."""
    return get_skin(export_skin).id
