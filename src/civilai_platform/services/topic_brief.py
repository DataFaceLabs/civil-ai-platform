"""Topic Hydrate brief compute — retrieve + closed-world LLM + citation gate."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from civilai_platform.llm_defaults import BASE_GUARDRAILS
from civilai_platform.model_presets import resolve_model_id
from civilai_platform.models.topic_brief import (
    TopicBrief,
    TopicBriefStatus,
    TopicCitation,
    TopicFieldExtract,
    ZoningBriefRequest,
    ZoningBriefResponse,
)
from civilai_platform.services import guardrails as guardrails_svc
from civilai_platform.services.data_proxy import DataProxyClient
from civilai_platform.services.guardrails_merge import EffectiveGuardRails, FieldGuardRail
from civilai_platform.store.base import PlatformStore

_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "Topic_Brief_Prompt.txt"
)

TOPIC_LABELS: dict[str, str] = {
    "district_identity": "District identity",
    "height_far": "Height and FAR",
    "setbacks_bulk": "Setbacks and bulk",
    "uses_density": "Uses and density",
    "parking_access": "Parking and access",
    "landscaping": "Landscaping and impervious",
    "overlay_modifiers": "Overlay modifiers",
    "affordability_mha": "Affordability and MHA",
    "shoreline": "Shoreline",
    "design_historic": "Design review and historic",
}

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


def apply_citation_gate(
    fields: list[TopicFieldExtract],
    field_rules: dict[str, FieldGuardRail],
) -> list[TopicFieldExtract]:
    """Drop extracts that violate field guardrails (T1 citation gate)."""
    kept: list[TopicFieldExtract] = []
    for field in fields:
        rule = field_rules.get(field.fe_code)
        if rule is None:
            continue
        if rule.not_applicable:
            continue
        if not rule.llm_extract_allowed:
            continue
        if rule.citation_required:
            if not (field.section_id and field.section_id.strip()):
                continue
            if not (field.quote and str(field.quote).strip()):
                continue
        kept.append(field)
    return kept


def _topic_label(topic_id: str) -> str:
    return TOPIC_LABELS.get(topic_id, topic_id.replace("_", " ").title())


def _enabled_topic_ids(
    effective: EffectiveGuardRails,
    requested: list[str] | None,
) -> list[str]:
    if requested:
        return list(dict.fromkeys(tid.strip() for tid in requested if tid.strip()))
    ids: list[str] = []
    for topic_id, rule in effective.topics.items():
        if not rule.enabled:
            continue
        tiers = set(rule.source_tier)
        if tiers & {"topic_hydrate", "topic_summary"}:
            ids.append(topic_id)
    return ids


def _parse_llm_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    match = _JSON_BLOCK_RE.search(stripped)
    if match is None:
        raise ValueError("LLM response did not contain JSON")
    return json.loads(match.group(0))


def _sections_payload(sections: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for section in sections:
        sid = str(section.get("section_id") or "")
        title = str(section.get("title") or "")
        citation = str(section.get("citation") or "")
        excerpt = str(section.get("excerpt") or section.get("text") or "")[:1200]
        blocks.append(
            f"section_id: {sid}\ncitation: {citation}\ntitle: {title}\nexcerpt: {excerpt}"
        )
    return "\n\n---\n\n".join(blocks)


def _invoke_topic_llm(
    *,
    topic_id: str,
    topic_label: str,
    context: ZoningBriefRequest,
    sections: list[dict[str, Any]],
    summary_only: bool,
    system_prompt: str,
    data_client: DataProxyClient,
    llm_invoke: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    user_prompt = (
        f"Topic: {topic_label} ({topic_id})\n"
        f"Jurisdiction: {context.jurisdiction_key}\n"
        f"Zoning code: {context.zoning_code or 'unknown'}\n"
    )
    if context.mha_class:
        user_prompt += f"MHA suffix: {context.mha_class}\n"
    if context.overlay_codes:
        user_prompt += f"Overlay codes: {', '.join(context.overlay_codes)}\n"
    if summary_only:
        user_prompt += (
            "\nThis topic is summary-only. Return JSON with summary and citations; "
            "leave fields empty.\n"
        )
    user_prompt += f"\nOrdinance sections:\n\n{_sections_payload(sections)}"

    body = {
        "model_id": resolve_model_id("haiku"),
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "field_context": {},
        "response_mode": "text",
        "guardrails": {
            "max_output_tokens": int(BASE_GUARDRAILS.get("maxOutputTokens", 4096)),
            "temperature": float(BASE_GUARDRAILS.get("temperature", 0.2)),
            "forbidden_phrases": list(BASE_GUARDRAILS.get("forbiddenPhrases") or []),
            "required_disclaimers": [],
            "enforce_guardrails": True,
        },
        "web_search": {
            "enabled": False,
            "execution_mode": "server",
            "query_mode": "deterministic",
            "restrict_provider_domains": True,
            "max_queries_per_invoke": 0,
            "max_results_per_query": 1,
            "allowed_domains": [],
            "blocked_domains": [],
            "search_depth": "basic",
            "search_context_hint": "",
            "include_trace_in_response": False,
        },
    }
    invoke = llm_invoke or data_client.invoke_llm
    return invoke(body)


def _brief_from_llm(
    *,
    topic_id: str,
    effective: EffectiveGuardRails,
    llm_payload: dict[str, Any],
    summary_only: bool,
    retrieve_status: str,
) -> TopicBrief:
    raw_text = str(llm_payload.get("text") or "")
    try:
        parsed = _parse_llm_json(raw_text)
    except (ValueError, json.JSONDecodeError) as exc:
        return TopicBrief(
            topic_id=topic_id,
            label=_topic_label(topic_id),
            status="partial",
            summary=raw_text[:500].strip(),
            guardrails_version=effective.guardrails_version,
            message=f"LLM JSON parse failed: {exc}",
        )

    summary = str(parsed.get("summary") or "").strip()
    raw_fields = parsed.get("fields") if isinstance(parsed.get("fields"), list) else []
    fields: list[TopicFieldExtract] = []
    for item in raw_fields:
        if not isinstance(item, dict):
            continue
        fe_code = str(item.get("fe_code") or "").strip()
        if not fe_code:
            continue
        fields.append(
            TopicFieldExtract(
                fe_code=fe_code,
                value=item.get("value"),
                section_id=(
                    str(item.get("section_id")).strip()
                    if item.get("section_id")
                    else None
                ),
                quote=str(item.get("quote")).strip() if item.get("quote") else None,
            )
        )

    if not summary_only:
        fields = apply_citation_gate(fields, effective.fields)

    citations: list[TopicCitation] = []
    raw_cites = parsed.get("citations") if isinstance(parsed.get("citations"), list) else []
    for item in raw_cites:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("section_id") or "").strip()
        if not sid:
            continue
        citations.append(
            TopicCitation(
                section_id=sid,
                citation=str(item.get("citation") or "").strip(),
                quote=str(item.get("quote") or "").strip(),
            )
        )

    if summary_only:
        status: TopicBriefStatus = "summary_only" if summary else "partial"
    elif retrieve_status == "partial" or not fields:
        status = "partial" if summary else "unavailable"
    else:
        status = "complete"

    return TopicBrief(
        topic_id=topic_id,
        label=_topic_label(topic_id),
        status=status,
        summary=summary,
        fields=fields,
        citations=citations,
        guardrails_version=effective.guardrails_version,
    )


def build_zoning_briefs(
    store: PlatformStore,
    request: ZoningBriefRequest,
    *,
    data_client: DataProxyClient,
    llm_invoke: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> ZoningBriefResponse:
    """Resolve guardrails, retrieve sections, LLM-summarize per topic."""
    effective = guardrails_svc.resolve_guardrails_effective(
        store,
        state_abbr=request.state_abbr,
        county_fips=request.county_fips,
        jurisdiction_key=request.jurisdiction_key,
        data_client=data_client,
    )
    base = ZoningBriefResponse(
        jurisdiction_key=request.jurisdiction_key.strip(),
        zoning_code=request.zoning_code,
        topic_hydrate_enabled=effective.topic_hydrate_enabled,
        guardrails_version=effective.guardrails_version,
    )
    topic_ids = _enabled_topic_ids(effective, request.topic_ids)
    if not topic_ids:
        return base

    if not effective.topic_hydrate_enabled:
        return base.model_copy(
            update={
                "briefs": [
                    TopicBrief(
                        topic_id=tid,
                        label=_topic_label(tid),
                        status="disabled",
                        guardrails_version=effective.guardrails_version,
                        message="topic hydrate disabled (corpus not ready or guardrails gate)",
                    )
                    for tid in topic_ids
                ]
            }
        )

    retrieve_body = {
        "jurisdiction_key": request.jurisdiction_key,
        "zoning_code": request.zoning_code,
        "overlay_codes": list(request.overlay_codes),
        "mha_class": request.mha_class,
        "state_abbr": request.state_abbr,
        "county_fips": request.county_fips,
        "topic_ids": topic_ids,
        "effective_guardrails": effective.model_dump(),
    }
    system_prompt = effective.brief_system_prompt.strip() or _load_system_prompt()
    retrieve_payload = data_client.retrieve_regtext(retrieve_body)
    corpus_status = str(retrieve_payload.get("corpus_status") or "")
    if corpus_status != "ready":
        return base.model_copy(
            update={
                "briefs": [
                    TopicBrief(
                        topic_id=tid,
                        label=_topic_label(tid),
                        status="unavailable",
                        guardrails_version=effective.guardrails_version,
                        message=f"corpus_status={corpus_status}",
                    )
                    for tid in topic_ids
                ]
            }
        )

    topics_payload = retrieve_payload.get("topics") or {}
    briefs: list[TopicBrief] = []

    for topic_id in topic_ids:
        topic_rule = effective.topics.get(topic_id)
        if topic_rule is None or not topic_rule.enabled:
            briefs.append(
                TopicBrief(
                    topic_id=topic_id,
                    label=_topic_label(topic_id),
                    status="disabled",
                    guardrails_version=effective.guardrails_version,
                    message="topic disabled by guardrails",
                )
            )
            continue

        tiers = set(topic_rule.source_tier)
        summary_only = "topic_hydrate" not in tiers and "topic_summary" in tiers
        if not tiers & {"topic_hydrate", "topic_summary"}:
            briefs.append(
                TopicBrief(
                    topic_id=topic_id,
                    label=_topic_label(topic_id),
                    status="skipped",
                    guardrails_version=effective.guardrails_version,
                    message="topic source_tier excludes hydrate and summary",
                )
            )
            continue

        topic_result = topics_payload.get(topic_id) if isinstance(topics_payload, dict) else None
        if not isinstance(topic_result, dict):
            briefs.append(
                TopicBrief(
                    topic_id=topic_id,
                    label=_topic_label(topic_id),
                    status="unavailable",
                    guardrails_version=effective.guardrails_version,
                    message="no retrieve result",
                )
            )
            continue

        retrieve_status = str(topic_result.get("status") or "")
        if retrieve_status in {"disabled", "skipped", "no_router"}:
            briefs.append(
                TopicBrief(
                    topic_id=topic_id,
                    label=_topic_label(topic_id),
                    status="skipped",
                    guardrails_version=effective.guardrails_version,
                    message=str(topic_result.get("message") or retrieve_status),
                )
            )
            continue

        sections = topic_result.get("sections") if isinstance(topic_result.get("sections"), list) else []
        if not sections:
            briefs.append(
                TopicBrief(
                    topic_id=topic_id,
                    label=_topic_label(topic_id),
                    status="no_sections",
                    guardrails_version=effective.guardrails_version,
                    message=str(topic_result.get("message") or "no sections retrieved"),
                )
            )
            continue

        llm_payload: dict[str, Any]
        try:
            llm_payload = _invoke_topic_llm(
                topic_id=topic_id,
                topic_label=_topic_label(topic_id),
                context=request,
                sections=sections,
                summary_only=summary_only,
                system_prompt=system_prompt,
                data_client=data_client,
                llm_invoke=llm_invoke,
            )
        except Exception as exc:
            briefs.append(
                TopicBrief(
                    topic_id=topic_id,
                    label=_topic_label(topic_id),
                    status="partial",
                    guardrails_version=effective.guardrails_version,
                    message=f"brief LLM failed: {exc}",
                )
            )
            continue
        briefs.append(
            _brief_from_llm(
                topic_id=topic_id,
                effective=effective,
                llm_payload=llm_payload,
                summary_only=summary_only,
                retrieve_status=retrieve_status,
            )
        )

    return base.model_copy(update={"briefs": briefs})
