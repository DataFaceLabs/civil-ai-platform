"""Compute proposed zoning facts from the land-dev reg-text corpus (ADR-0008)."""

from __future__ import annotations

import hashlib
import json
import logging
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
    "IMPERVIOUS_REGS",
    "IMPERVIOUS_COVER_LIMIT",
    "COMPATIBILITY_STDS",
    "LDC_REFERENCE",
    "GOVERNING_JURIS",
)

_CODE_QUERIES: dict[str, tuple[str, list[str]]] = {
    "ZONING_REGS": ("zoning district site development regulations", ["zoning"]),
    "IMPERVIOUS_REGS": ("impervious cover watershed", ["impervious_cover", "environmental"]),
    "IMPERVIOUS_COVER_LIMIT": ("impervious cover limit", ["impervious_cover"]),
    "COMPATIBILITY_STDS": ("compatibility standards height setbacks", ["compatibility", "zoning"]),
    "LDC_REFERENCE": ("land development code", ["zoning"]),
    "GOVERNING_JURIS": ("jurisdiction zoning", ["zoning"]),
}


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fingerprint(payload: Any, jurisdiction_key: str, proposed_code: str) -> str:
    blob = json.dumps(
        {"site": payload, "j": jurisdiction_key, "z": proposed_code},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _field_value(text: str, *, origin: str, status: str = "review") -> ScenarioFieldValue:
    return ScenarioFieldValue(value=text, status=status, origin=origin)  # type: ignore[arg-type]


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


def _compose_zoning_regs(proposed_code: str, hits: list[dict[str, Any]]) -> str:
    if not hits:
        return (
            f"Proposed zoning: {proposed_code}. "
            "District-specific rule extraction pending — land-dev corpus returned no hits."
        )
    parts = [f"Proposed zoning: {proposed_code}."]
    for hit in hits[:3]:
        citation = hit.get("citation") or hit.get("section_id")
        excerpt = hit.get("excerpt") or ""
        parts.append(f"{citation}: {excerpt}")
    return "\n\n".join(parts)


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
) -> ZoningFactComparison:
    b = baseline.value if baseline else None
    p = proposed.value if proposed else None
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
    elif p and not b:
        kind = "added"
        summary = "Proposed value added"
        level = "medium"
        drivers = ["corpus_gap"] if "pending" in (p or "").lower() else []
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

    if not evidence and kind != "unchanged":
        if "corpus_gap" not in drivers:
            drivers.append("corpus_gap")
        level = "unknown" if level == "low" else level

    return ZoningFactComparison(
        fe_code=fe_code,
        baseline_value=b,
        proposed_value=p,
        diff=ZoningFactDiff(kind=kind, summary=summary),  # type: ignore[arg-type]
        risk=ZoningFactRisk(level=level, drivers=drivers),  # type: ignore[arg-type]
        evidence=evidence,
        needs_review=kind != "unchanged",
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

        for code in COMPARABLE_CODES:
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

            evidence = _evidence_from_hits(jurisdiction_key, hits)
            if code == "ZONING_REGS":
                text = _compose_zoning_regs(proposed_code, hits)
            elif code == "GOVERNING_JURIS":
                text = jurisdiction_key
            elif code == "LDC_REFERENCE":
                text = hits[0]["citation"] if hits else f"Land development code — {jurisdiction_key}"
            elif hits:
                text = f"{hits[0].get('citation', '')}: {hits[0].get('excerpt', '')}".strip(": ")
            else:
                text = f"{code} for {proposed_code}: corpus gap — confirm in adopted land-dev code."
                open_gaps.append(code)

            proposed_fields[code] = _field_value(text, origin="regtext" if hits else "composed")
            cmp = _compare_field(
                code,
                baseline.fields.get(code),
                proposed_fields[code],
                evidence=evidence,
                district_changed=district_changed,
            )
            if cmp.risk.level == "high":
                high_risk.append(code)
            comparisons.append(cmp)

        overall = "high" if high_risk else ("medium" if district_changed else "low")
        if open_gaps and overall == "low":
            overall = "unknown"

        proposed_bundle = ZoningFactBundle(
            fields=proposed_fields,
            structured=ZoningFactStructured(
                zoning_code=proposed_code,
                zoning_base=scenario.intent.proposed_zoning_base,
                overlays=list(baseline.structured.overlays) if scenario.intent.keep_overlays else [],
                jurisdiction_key=jurisdiction_key,
                ic_limit_pct=baseline.structured.ic_limit_pct,
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
