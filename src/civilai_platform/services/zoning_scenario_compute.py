"""Compute proposed zoning facts from the land-dev reg-text corpus (ADR-0008)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from civilai_platform.models.zoning_scenario import (
    OrdinanceEvidence,
    ScenarioFieldValue,
    ZoningChangeScenario,
    ZoningComputationMeta,
    ZoningFactBundle,
    ZoningFactComparison,
    ZoningFactDiff,
    ZoningFactRisk,
    ZoningFactStructured,
    ZoningInputFingerprint,
    ZoningRiskSummary,
    ZoningScenarioState,
)
from civilai_platform.settings import get_settings

logger = logging.getLogger(__name__)

COMPARABLE_CODES = (
    "ZONING_REGS",
    "IMPERVIOUS_COVER_LIMIT",
    "IMPERVIOUS_REGS",
    "COMPATIBILITY_STDS",
    "LDC_REFERENCE",
    "GOVERNING_JURIS",
    "MIN_LOT_SIZE",
    "MIN_LOT_WIDTH",
    "SETBACKS",
    "MAX_BUILDING_COVERAGE",
    "MAX_BUILDING_HEIGHT",
    "EASEMENTS_SETBACKS",
)

_DSI_CODES = frozenset(
    {
        "MIN_LOT_SIZE",
        "MIN_LOT_WIDTH",
        "SETBACKS",
        "MAX_BUILDING_COVERAGE",
        "MAX_BUILDING_HEIGHT",
        "IMPERVIOUS_COVER_LIMIT",
        "EASEMENTS_SETBACKS",
    }
)

_CODE_QUERIES: dict[str, tuple[str, list[str]]] = {
    "ZONING_REGS": ("zoning district site development regulations", ["zoning"]),
    "IMPERVIOUS_REGS": ("impervious cover watershed", ["impervious_cover", "environmental"]),
    "IMPERVIOUS_COVER_LIMIT": ("impervious cover limit", ["impervious_cover"]),
    "COMPATIBILITY_STDS": ("compatibility standards height setbacks", ["compatibility", "zoning"]),
    "LDC_REFERENCE": ("land development code", ["zoning"]),
    "GOVERNING_JURIS": ("jurisdiction zoning", ["zoning"]),
    "MIN_LOT_SIZE": ("minimum lot size area", ["zoning"]),
    "MIN_LOT_WIDTH": ("minimum lot width", ["zoning"]),
    "SETBACKS": ("front side rear setback", ["zoning", "compatibility"]),
    "MAX_BUILDING_COVERAGE": ("maximum building coverage", ["zoning"]),
    "MAX_BUILDING_HEIGHT": ("maximum building height", ["zoning"]),
    "EASEMENTS_SETBACKS": ("easement setback", ["zoning"]),
}

# Narrative fields: citation pointers only (no ordinance body excerpts).
_CITATION_ONLY_CODES = frozenset(
    {
        "ZONING_REGS",
        "IMPERVIOUS_REGS",
        "COMPATIBILITY_STDS",
    }
)

_BOILERPLATE_TITLE_RE = re.compile(
    r"\b(definitions?|establishment of districts?|general provisions)\b",
    re.I,
)
_DISTRICT_TITLE_RE = re.compile(
    r"[-–—]\s*([A-Za-z0-9][A-Za-z0-9-]{0,12})\s*(?:\([^)]*\))?\s*district\b",
    re.I,
)
_IMPERVIOUS_TITLE_RE = re.compile(
    r"\b(impervious|watershed|stormwater|drainage|site development)\b",
    re.I,
)
_COMPAT_TITLE_RE = re.compile(r"\bcompatibilit", re.I)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fingerprint(payload: Any, jurisdiction_key: str, proposed_code: str) -> str:
    blob = json.dumps(
        {"site": payload, "j": jurisdiction_key, "z": proposed_code},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _field_value(text: str, *, origin: str, status: str | None = None) -> ScenarioFieldValue:
    resolved = status if status is not None else ("empty" if not text.strip() else "review")
    return ScenarioFieldValue(value=text, status=resolved, origin=origin)  # type: ignore[arg-type]


def _resolve_dsi(
    *,
    jurisdiction_key: str,
    zoning_code: str,
    client: httpx.Client,
    base_url: str,
    service_key: str | None,
) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    if service_key:
        headers["X-Data-Service-Key"] = service_key
    url = f"{base_url.rstrip('/')}/v1/dsi/resolve"
    resp = client.get(
        url,
        params={"jurisdiction_key": jurisdiction_key, "zoning_code": zoning_code},
        headers=headers,
    )
    if resp.status_code >= 400:
        logger.warning("dsi resolve failed: %s %s", resp.status_code, resp.text[:200])
        return None
    data = resp.json()
    return data if isinstance(data, dict) else None


def _dsi_field_texts(dsi: dict[str, Any], proposed_code: str) -> dict[str, str]:
    """Map DSI resolve payload to comparable FE display strings."""
    record = dsi.get("record") or {}
    std = record.get("standards") or {}
    out: dict[str, str] = {}
    if std.get("min_lot_area_sqft") is not None:
        out["MIN_LOT_SIZE"] = f"{float(std['min_lot_area_sqft']):,.0f} sq ft"
    elif std.get("min_lot_area_ac") is not None:
        out["MIN_LOT_SIZE"] = f"{std['min_lot_area_ac']} ac"
    if std.get("min_lot_width_ft") is not None:
        out["MIN_LOT_WIDTH"] = f"{float(std['min_lot_width_ft']):g} ft"
    parts: list[str] = []
    if std.get("setback_front_ft") is not None:
        parts.append(f"Front: {float(std['setback_front_ft']):g} ft")
    if std.get("setback_side_ft") is not None:
        parts.append(f"Side: {float(std['setback_side_ft']):g} ft")
    if std.get("setback_rear_ft") is not None:
        parts.append(f"Rear: {float(std['setback_rear_ft']):g} ft")
    if parts:
        out["SETBACKS"] = "; ".join(parts)
        out["EASEMENTS_SETBACKS"] = (
            f"Required setbacks ({proposed_code}): {'; '.join(parts)}. "
            "Platted / recorded easements require title commitment and survey confirmation."
        )
    if std.get("max_building_coverage_pct") is not None:
        out["MAX_BUILDING_COVERAGE"] = f"{float(std['max_building_coverage_pct']):g}%"
    if std.get("max_height_ft") is not None:
        out["MAX_BUILDING_HEIGHT"] = f"{float(std['max_height_ft']):g} ft"
    elif std.get("max_height_stories") is not None:
        out["MAX_BUILDING_HEIGHT"] = f"{float(std['max_height_stories']):g} stories"
    if std.get("max_impervious_cover_pct") is not None:
        out["IMPERVIOUS_COVER_LIMIT"] = f"{float(std['max_impervious_cover_pct']):g}%"
    return out


def _evidence_from_dsi(jurisdiction_key: str, dsi: dict[str, Any]) -> list[OrdinanceEvidence]:
    now = _now_iso()
    record = dsi.get("record") or {}
    citations = record.get("citations") or {}
    out: list[OrdinanceEvidence] = []
    if isinstance(citations, dict):
        for cite in citations.values():
            if not isinstance(cite, dict):
                continue
            out.append(
                OrdinanceEvidence(
                    jurisdiction_key=jurisdiction_key,
                    section_id=str(cite.get("section_id") or ""),
                    citation=str(cite.get("citation") or ""),
                    title=cite.get("title"),
                    deep_link=str(cite.get("deep_link") or ""),
                    excerpt="",
                    retrieved_at=now,
                )
            )
    return out


def _parse_leading_number(text: str | None) -> float | None:
    if not text:
        return None
    import re

    m = re.search(r"([\d,.]+)", text.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _baseline_from_state(
    site_payload: dict[str, Any] | None,
    sections: list[Any],
    jurisdiction_key: str | None,
) -> ZoningFactBundle:
    fields: dict[str, ScenarioFieldValue] = {}
    zoning_code: str | None = None
    ic_limit: float | None = None
    for section in sections:
        step = getattr(section, "step_key", None) or (
            section.get("step_key") if isinstance(section, dict) else None
        )
        if step != "zoning":
            continue
        sec_fields = getattr(section, "fields", None) or (
            section.get("fields") if isinstance(section, dict) else {}
        )
        for code in COMPARABLE_CODES:
            raw = sec_fields.get(code) if isinstance(sec_fields, dict) else None
            if raw is None:
                continue
            value = getattr(raw, "value", None) if not isinstance(raw, dict) else raw.get("value")
            status = getattr(raw, "status", "empty") if not isinstance(raw, dict) else raw.get("status", "empty")
            if value is None:
                continue
            text = str(value)
            fields[code] = _field_value(text, origin="lake", status=str(status))
            if code == "ZONING_REGS" and text:
                import re

                m = re.search(r"\b([A-Z]{1,4}-?\d[A-Z0-9-]*)\b", text)
                if m:
                    zoning_code = m.group(1)
            if code == "IMPERVIOUS_COVER_LIMIT":
                try:
                    ic_limit = float(str(text).replace("%", "").strip())
                except ValueError:
                    pass
    overlays: list[str] = []
    if isinstance(site_payload, dict):
        zoning = site_payload.get("zoning") or {}
        if isinstance(zoning, dict):
            ov = zoning.get("overlays")
            if isinstance(ov, list):
                overlays = [str(x) for x in ov]
            if not zoning_code:
                zoning_code = zoning.get("zoning_code") or zoning.get("zoning_base")
    return ZoningFactBundle(
        fields=fields,
        structured=ZoningFactStructured(
            zoning_code=str(zoning_code) if zoning_code else None,
            zoning_base=None,
            overlays=overlays,
            jurisdiction_key=jurisdiction_key,
            ic_limit_pct=ic_limit,
        ),
    )


def _search_regtext(
    *,
    jurisdiction_key: str,
    query: str,
    domains: list[str] | None,
    client: httpx.Client,
    base_url: str,
    service_key: str | None,
) -> list[dict[str, Any]]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if service_key:
        headers["X-Data-Service-Key"] = service_key
    url = f"{base_url.rstrip('/')}/v1/regtext/search"
    body: dict[str, Any] = {
        "jurisdiction_key": jurisdiction_key,
        "query": query,
        "limit": 5,
    }
    if domains:
        body["domains"] = domains
    resp = client.post(url, json=body, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def _hit_title(hit: dict[str, Any]) -> str:
    return str(hit.get("title") or hit.get("citation") or "")


def _is_boilerplate_hit(hit: dict[str, Any]) -> bool:
    return bool(_BOILERPLATE_TITLE_RE.search(_hit_title(hit)))


def _title_matches_district_code(title: str, proposed_code: str) -> bool:
    code = proposed_code.strip()
    if not code:
        return False
    m = _DISTRICT_TITLE_RE.search(title)
    if m and m.group(1).upper() == code.upper():
        return True
    # Fallback: code appears in title alongside "district"
    title_u = title.upper()
    return code.upper() in title_u and "DISTRICT" in title_u


def _filter_citation_hits(
    fe_code: str,
    proposed_code: str,
    hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep only ordinance sections that are plausible cites for the FE field."""
    if not hits:
        return []

    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for idx, hit in enumerate(hits):
        title = _hit_title(hit)
        if _is_boilerplate_hit(hit):
            continue
        priority = 0
        if fe_code == "ZONING_REGS":
            if _title_matches_district_code(title, proposed_code):
                priority = 3
            elif proposed_code.upper() in title.upper():
                priority = 2
            elif re.search(r"\bdistrict\b", title, re.I) and not _is_boilerplate_hit(hit):
                priority = 1
            else:
                continue
        elif fe_code == "IMPERVIOUS_REGS":
            if _IMPERVIOUS_TITLE_RE.search(title):
                priority = 2
            elif _title_matches_district_code(title, proposed_code):
                # District article often points at IC via dimensional standards.
                priority = 1
            else:
                continue
        elif fe_code == "COMPATIBILITY_STDS":
            if _COMPAT_TITLE_RE.search(title):
                priority = 2
            else:
                # Do not treat generic height/setback district text as compatibility.
                continue
        else:
            priority = 1
        ranked.append((priority, -idx, hit))

    ranked.sort(key=lambda row: (-row[0], -row[1]))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, __, hit in ranked:
        cite = str(hit.get("citation") or hit.get("section_id") or "").strip()
        if not cite or cite in seen:
            continue
        seen.add(cite)
        out.append(hit)
        if len(out) >= 3:
            break
    return out


def _compose_citations(proposed_code: str, hits: list[dict[str, Any]]) -> str:
    """Citation-only field value. Empty when search yields no relevant sections."""
    if not hits:
        return ""
    cites: list[str] = []
    seen: set[str] = set()
    for hit in hits[:3]:
        citation = str(hit.get("citation") or hit.get("section_id") or "").strip()
        if not citation or citation in seen:
            continue
        seen.add(citation)
        cites.append(citation)
    if not cites:
        return ""
    code = proposed_code.strip()
    joined = "; ".join(cites)
    return f"{code} — {joined}" if code else joined


def _dsi_citation_hits(dsi: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Promote DSI dimensional citation into a search-hit-shaped dict."""
    if not dsi:
        return []
    record = dsi.get("record") or {}
    citations = record.get("citations") or {}
    dim = citations.get("dimensional") if isinstance(citations, dict) else None
    if not isinstance(dim, dict):
        return []
    citation = str(dim.get("citation") or "").strip()
    if not citation:
        return []
    return [
        {
            "section_id": str(dim.get("section_id") or ""),
            "citation": citation,
            "title": str(dim.get("title") or citation),
            "deep_link": str(dim.get("deep_link") or ""),
            "excerpt": "",
            "retrieved_at": _now_iso(),
        }
    ]


def _evidence_from_hits(jurisdiction_key: str, hits: list[dict[str, Any]]) -> list[OrdinanceEvidence]:
    now = _now_iso()
    out: list[OrdinanceEvidence] = []
    for hit in hits[:3]:
        out.append(
            OrdinanceEvidence(
                jurisdiction_key=jurisdiction_key,
                section_id=str(hit.get("section_id") or ""),
                citation=str(hit.get("citation") or ""),
                title=hit.get("title"),
                deep_link=str(hit.get("deep_link") or ""),
                excerpt=str(hit.get("excerpt") or ""),
                retrieved_at=str(hit.get("retrieved_at") or now),
            )
        )
    return out


def _compare_field(
    fe_code: str,
    baseline: ScenarioFieldValue | None,
    proposed: ScenarioFieldValue | None,
    *,
    evidence: list[OrdinanceEvidence],
    district_changed: bool,
    standards_stale: bool = False,
) -> ZoningFactComparison:
    from civilai_platform.models.zoning_scenario import NumericDiff

    b = baseline.value if baseline else None
    p = proposed.value if proposed else None
    numeric: NumericDiff | None = None
    if b == p:
        kind = "unchanged"
        summary = "Unchanged"
        level = "low"
        drivers: list[str] = []
    elif b and p:
        kind = "changed"
        summary = "Value changed under proposed zoning"
        level = "medium" if district_changed else "low"
        drivers = ["entitlement_rezoning_required"] if district_changed and fe_code == "ZONING_REGS" else []
        bn = _parse_leading_number(b)
        pn = _parse_leading_number(p)
        if bn is not None and pn is not None and fe_code in _DSI_CODES:
            delta = pn - bn
            unit = "%" if "%" in (p or "") else "ft"
            if "sq ft" in (p or "").lower() or "ac" in (p or "").lower():
                unit = "sqft" if "sq ft" in (p or "").lower() else "ac"
            numeric = NumericDiff(unit=unit, baseline=bn, proposed=pn, delta=delta)
            if delta < 0 and fe_code in {
                "MIN_LOT_SIZE",
                "MIN_LOT_WIDTH",
                "SETBACKS",
                "MAX_BUILDING_COVERAGE",
                "MAX_BUILDING_HEIGHT",
                "IMPERVIOUS_COVER_LIMIT",
            }:
                # Smaller max limits / larger mins need nuance; flag both ways.
                if fe_code.startswith("MAX") or fe_code == "IMPERVIOUS_COVER_LIMIT":
                    drivers.append("dimensional_more_restrictive")
                else:
                    drivers.append("dimensional_more_permissive")
            elif delta > 0 and fe_code in _DSI_CODES:
                if fe_code.startswith("MAX") or fe_code == "IMPERVIOUS_COVER_LIMIT":
                    drivers.append("dimensional_more_permissive")
                else:
                    drivers.append("dimensional_more_restrictive")
    elif p and not b:
        kind = "added"
        summary = "Proposed value added"
        level = "medium"
        drivers = ["corpus_gap"] if "pending" in (p or "").lower() or "gap" in (p or "").lower() else []
    elif b and not p:
        kind = "removed"
        summary = "Proposed value missing"
        level = "unknown"
        drivers = ["corpus_gap"]
    else:
        kind = "incomparable"
        summary = "Insufficient data"
        level = "unknown"
        drivers = ["corpus_gap"]

    if standards_stale and "standards_stale" not in drivers:
        drivers.append("standards_stale")
        if level == "low":
            level = "medium"

    if not evidence and kind != "unchanged" and fe_code not in _DSI_CODES:
        if "corpus_gap" not in drivers:
            drivers.append("corpus_gap")
        level = "unknown" if level == "low" else level

    return ZoningFactComparison(
        fe_code=fe_code,
        baseline_value=b,
        proposed_value=p,
        diff=ZoningFactDiff(kind=kind, summary=summary, numeric=numeric),  # type: ignore[arg-type]
        risk=ZoningFactRisk(level=level, drivers=drivers),  # type: ignore[arg-type]
        evidence=evidence,
        needs_review=kind != "unchanged" or standards_stale,
    )


def compute_zoning_scenario(
    state: ZoningScenarioState,
    *,
    scenario_id: str,
    site_payload: dict[str, Any] | None,
    sections: list[Any],
    http_client: httpx.Client | None = None,
) -> ZoningScenarioState:
    """Fill proposed facts + comparisons for the active scenario using reg-text search."""
    scenario = next((s for s in state.scenarios if s.scenario_id == scenario_id), None)
    if scenario is None:
        raise ValueError(f"Scenario not found: {scenario_id}")

    settings = get_settings()
    jurisdiction_key = (
        scenario.intent.jurisdiction_key
        or state.effective_jurisdiction_key
        or state.baseline_jurisdiction_key
        or "coa_full"
    )
    proposed_code = scenario.intent.proposed_zoning_code.strip()
    baseline = _baseline_from_state(site_payload, sections, state.baseline_jurisdiction_key)
    district_changed = (baseline.structured.zoning_code or "").upper() != proposed_code.upper()

    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=30.0)
    proposed_fields: dict[str, ScenarioFieldValue] = {}
    comparisons: list[ZoningFactComparison] = []
    open_gaps: list[str] = []
    high_risk: list[str] = []
    corpus_version: str | None = None
    dsi_version: str | None = None
    standards_stale = False

    try:
        # Ensure corpus
        ensure_url = f"{settings.data_api_base.rstrip('/')}/v1/regtext/ensure"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if settings.data_service_key:
            headers["X-Data-Service-Key"] = settings.data_service_key
        ensure_resp = client.post(
            ensure_url,
            json={"jurisdiction_key": jurisdiction_key},
            headers=headers,
        )
        if ensure_resp.status_code < 400:
            corpus_version = ensure_resp.json().get("corpus_version")

        # DSI resolve for dimensional standards (ADR-0009)
        dsi_payload = _resolve_dsi(
            jurisdiction_key=jurisdiction_key,
            zoning_code=proposed_code,
            client=client,
            base_url=settings.data_api_base,
            service_key=settings.data_service_key,
        )
        dsi_texts: dict[str, str] = {}
        dsi_evidence: list[OrdinanceEvidence] = []
        if dsi_payload:
            dsi_version = dsi_payload.get("dsi_version")
            standards_stale = dsi_payload.get("freshness") == "stale"
            if dsi_payload.get("found"):
                dsi_texts = _dsi_field_texts(dsi_payload, proposed_code)
                dsi_evidence = _evidence_from_dsi(jurisdiction_key, dsi_payload)
            else:
                open_gaps.extend(sorted(_DSI_CODES))

        for code in COMPARABLE_CODES:
            evidence: list[OrdinanceEvidence] = []
            if code in _DSI_CODES and code in dsi_texts:
                text = dsi_texts[code]
                evidence = list(dsi_evidence)
                origin = "regtext"
            elif code in _DSI_CODES and code not in dsi_texts:
                text = f"{code} for {proposed_code}: confirm in adopted land-dev code."
                open_gaps.append(code)
                origin = "composed"
            else:
                query_base, domains = _CODE_QUERIES[code]
                query = f"{proposed_code} {query_base}"
                try:
                    hits = _search_regtext(
                        jurisdiction_key=jurisdiction_key,
                        query=query,
                        domains=domains,
                        client=client,
                        base_url=settings.data_api_base,
                        service_key=settings.data_service_key,
                    )
                except Exception as exc:  # noqa: BLE001 — surface as corpus gap
                    logger.warning("regtext search failed for %s: %s", code, exc)
                    hits = []

                if code in _CITATION_ONLY_CODES:
                    relevant = _filter_citation_hits(code, proposed_code, hits)
                    if not relevant and code == "IMPERVIOUS_REGS":
                        # Prefer DSI dimensional schedule cite over empty IC regs.
                        relevant = _dsi_citation_hits(dsi_payload)
                    text = _compose_citations(proposed_code, relevant)
                    evidence = _evidence_from_hits(jurisdiction_key, relevant)
                    if not text:
                        open_gaps.append(code)
                    origin = "regtext" if text else "composed"
                else:
                    evidence = _evidence_from_hits(jurisdiction_key, hits)
                    if code == "GOVERNING_JURIS":
                        text = jurisdiction_key
                    elif code == "LDC_REFERENCE":
                        text = (
                            hits[0]["citation"]
                            if hits
                            else f"Land development code — {jurisdiction_key}"
                        )
                    elif hits:
                        text = (
                            f"{hits[0].get('citation', '')}: "
                            f"{hits[0].get('excerpt', '')}"
                        ).strip(": ")
                    else:
                        text = (
                            f"{code} for {proposed_code}: "
                            "confirm in adopted land-dev code."
                        )
                        open_gaps.append(code)
                    origin = "regtext" if hits else "composed"

            proposed_fields[code] = _field_value(text, origin=origin)
            cmp = _compare_field(
                code,
                baseline.fields.get(code),
                proposed_fields[code],
                evidence=evidence,
                district_changed=district_changed,
                standards_stale=standards_stale and code in _DSI_CODES,
            )
            if cmp.risk.level == "high":
                high_risk.append(code)
            comparisons.append(cmp)

        overall = "high" if high_risk else ("medium" if district_changed else "low")
        if open_gaps and overall == "low":
            overall = "unknown"
        if standards_stale and overall == "low":
            overall = "medium"

        ic_limit = baseline.structured.ic_limit_pct
        if "IMPERVIOUS_COVER_LIMIT" in dsi_texts:
            parsed_ic = _parse_leading_number(dsi_texts["IMPERVIOUS_COVER_LIMIT"])
            if parsed_ic is not None:
                ic_limit = parsed_ic

        proposed_bundle = ZoningFactBundle(
            fields=proposed_fields,
            structured=ZoningFactStructured(
                zoning_code=proposed_code,
                zoning_base=scenario.intent.proposed_zoning_base,
                overlays=list(baseline.structured.overlays) if scenario.intent.keep_overlays else [],
                jurisdiction_key=jurisdiction_key,
                ic_limit_pct=ic_limit,
            ),
        )

        updated_scenario = scenario.model_copy(
            update={
                "status": "computed",
                "updated_at": _now_iso(),
                "baseline": baseline,
                "proposed": proposed_bundle,
                "comparisons": comparisons,
                "input_fingerprint": ZoningInputFingerprint(
                    site_payload_fingerprint=_fingerprint(
                        site_payload, jurisdiction_key, proposed_code
                    ),
                    regtext_corpus_version=corpus_version,
                    dsi_version=dsi_version,
                    jurisdiction_key=jurisdiction_key,
                    proposed_zoning_code=proposed_code,
                ),
                "risk_summary": ZoningRiskSummary(
                    overall=overall,  # type: ignore[arg-type]
                    entitlement_required=district_changed,
                    high_risk_fact_codes=high_risk,
                    open_gaps=open_gaps,
                ),
                "computation": ZoningComputationMeta(
                    last_computed_at=_now_iso(),
                    status="succeeded",
                ),
            }
        )
    except Exception as exc:
        updated_scenario = scenario.model_copy(
            update={
                "updated_at": _now_iso(),
                "computation": ZoningComputationMeta(
                    last_computed_at=_now_iso(),
                    status="failed",
                    error=str(exc),
                ),
            }
        )
        raise
    finally:
        if owns_client:
            client.close()

    scenarios = [updated_scenario if s.scenario_id == scenario_id else s for s in state.scenarios]
    return state.model_copy(
        update={
            "scenarios": scenarios,
            "active_scenario_id": scenario_id,
            "effective_jurisdiction_key": jurisdiction_key,
        }
    )
