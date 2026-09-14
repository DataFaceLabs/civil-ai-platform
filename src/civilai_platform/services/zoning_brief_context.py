"""Build ZoningBriefRequest from project state + Prompt Lab field context."""

from __future__ import annotations

import json
import re
from typing import Any

from civilai_platform.models.entities import FieldValue, ProjectState
from civilai_platform.models.topic_brief import ZoningBriefRequest

_ZONING_PREFIX_RE = re.compile(r"\bZoning:\s*([^\n]+)", re.IGNORECASE)
_OVERLAYS_LINE_RE = re.compile(r"^Overlays:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_MHA_SUFFIX_RE = re.compile(r"\(([Mm](?:\d+)?)\)\s*$")


def _nonempty(value: object) -> str:
    return str(value or "").strip()


def _dig(payload: dict[str, Any], *keys: str) -> str | None:
    cur: Any = payload
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    text = _nonempty(cur)
    return text or None


def _field_text(fields: dict[str, FieldValue] | dict[str, Any], code: str) -> str:
    raw = fields.get(code)
    if raw is None:
        return ""
    if isinstance(raw, FieldValue):
        return _nonempty(raw.value)
    if isinstance(raw, dict):
        return _nonempty(raw.get("value"))
    return _nonempty(raw)


def _merged_zoning_fields(
    field_context: dict[str, str],
    project_state: ProjectState | None,
) -> dict[str, str]:
    merged = {key: value for key, value in field_context.items() if _nonempty(value)}
    if project_state is None:
        return merged
    for section in project_state.sections:
        if section.step_key != "zoning":
            continue
        for code, field in section.fields.items():
            text = _field_text(section.fields, code)
            if text and code not in merged:
                merged[code] = text
        break
    if project_state.site_context:
        for code, field in project_state.site_context.items():
            text = _field_text(project_state.site_context, code)
            if text and code not in merged:
                merged[code] = text
    return merged


def _jurisdiction_key(
    fields: dict[str, str],
    project_state: ProjectState | None,
) -> str | None:
    if project_state and project_state.zoning_scenario is not None:
        scenario = project_state.zoning_scenario
        for attr in ("effective_jurisdiction_key", "baseline_jurisdiction_key"):
            text = _nonempty(getattr(scenario, attr, None))
            if text:
                return text.lower()
    site_payload = (
        project_state.site_payload
        if project_state and isinstance(project_state.site_payload, dict)
        else {}
    )
    for path in (
        ("jurisdiction", "jurisdiction_key"),
        ("parcel", "jurisdiction_key"),
        ("snapshot", "jurisdiction_key"),
    ):
        found = _dig(site_payload, *path)
        if found:
            return found.lower()
    return None


def _parse_zoning_code(text: str) -> str | None:
    match = _ZONING_PREFIX_RE.search(text)
    if not match:
        return None
    return match.group(1).strip().rstrip(".,;")


def _parse_overlay_codes(text: str) -> list[str]:
    match = _OVERLAYS_LINE_RE.search(text)
    if not match:
        return []
    payload = match.group(1).strip()
    if payload.startswith("["):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return []
    if "," in payload:
        return [part.strip() for part in payload.split(",") if part.strip()]
    return [payload] if payload else []


def _parse_mha_class(zoning_code: str | None) -> str | None:
    if not zoning_code:
        return None
    match = _MHA_SUFFIX_RE.search(zoning_code.strip())
    return match.group(1).upper() if match else None


def _county_fips(project_state: ProjectState | None) -> str | None:
    if project_state and isinstance(project_state.parcel, dict):
        for key in ("sourceFips", "source_fips"):
            text = _nonempty(project_state.parcel.get(key))
            if text and text.isdigit() and len(text) == 5:
                return text
    site_payload = (
        project_state.site_payload
        if project_state and isinstance(project_state.site_payload, dict)
        else {}
    )
    geometry = site_payload.get("geometry")
    if isinstance(geometry, dict):
        props = geometry.get("properties")
        if isinstance(props, dict):
            text = _nonempty(props.get("source_fips"))
            if text and text.isdigit() and len(text) == 5:
                return text
    return None


def _state_abbr(county_fips: str | None) -> str | None:
    if not county_fips or len(county_fips) < 2:
        return None
    prefix = county_fips[:2]
    if prefix == "48":
        return "TX"
    if prefix == "53":
        return "WA"
    return None


def build_zoning_brief_request(
    *,
    field_context: dict[str, str],
    project_state: ProjectState | None,
) -> ZoningBriefRequest | None:
    """Assemble a brief request when jurisdiction context is sufficient."""
    fields = _merged_zoning_fields(field_context, project_state)
    jurisdiction_key = _jurisdiction_key(fields, project_state)
    if not jurisdiction_key:
        return None
    zoning_regs = _nonempty(fields.get("ZONING_REGS"))
    zoning_code = _parse_zoning_code(zoning_regs) if zoning_regs else None
    county_fips = _county_fips(project_state)
    return ZoningBriefRequest(
        jurisdiction_key=jurisdiction_key,
        zoning_code=zoning_code,
        overlay_codes=_parse_overlay_codes(zoning_regs),
        mha_class=_parse_mha_class(zoning_code),
        state_abbr=_state_abbr(county_fips),
        county_fips=county_fips,
        topic_ids=None,
    )
