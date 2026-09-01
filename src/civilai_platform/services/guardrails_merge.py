"""Guard rail merge — keep aligned with civilai.guardrails.merge in civil-ai-data."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field

SourceTier = Literal["lake", "dsi", "topic_hydrate", "topic_summary", "scenario"]


class RetrievalBudget(BaseModel):
    searches: int = 3
    gets: int = 5
    hops: int = 2


class FieldGuardRail(BaseModel):
    source_tier: list[SourceTier] = Field(default_factory=lambda: ["lake", "dsi"])
    citation_required: bool = True
    llm_extract_allowed: bool = False
    show_when_populated: bool = False
    not_applicable: bool = False


class TopicGuardRail(BaseModel):
    enabled: bool = True
    source_tier: list[SourceTier] = Field(default_factory=lambda: ["topic_hydrate"])
    retrieval_budget: RetrievalBudget | None = None


class GuardRailsScopePayload(BaseModel):
    domain: str = "zoning"
    scope_key: str
    schema_version: int = 1
    fields: dict[str, FieldGuardRail] = Field(default_factory=dict)
    topics: dict[str, TopicGuardRail] = Field(default_factory=dict)


class EffectiveGuardRails(BaseModel):
    domain: str = "zoning"
    fields: dict[str, FieldGuardRail] = Field(default_factory=dict)
    topics: dict[str, TopicGuardRail] = Field(default_factory=dict)
    applied_scopes: list[str] = Field(default_factory=list)
    guardrails_version: str = ""
    topic_hydrate_enabled: bool = False


def _deep_merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, val in patch.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_dict(out[key], val)
        else:
            out[key] = val
    return out


def scope_keys_for_request(
    *,
    state_abbr: str | None,
    county_fips: str | None,
    jurisdiction_key: str | None,
) -> list[str]:
    keys = ["_default"]
    if state_abbr and state_abbr.strip():
        keys.append(f"state:{state_abbr.strip().upper()}")
    if county_fips and county_fips.strip():
        keys.append(f"county:{county_fips.strip()}")
    if jurisdiction_key and jurisdiction_key.strip():
        keys.append(f"jurisdiction:{jurisdiction_key.strip().lower()}")
    return keys


def merge_scope_payloads(
    layers: list[GuardRailsScopePayload],
) -> tuple[dict[str, FieldGuardRail], dict[str, TopicGuardRail], list[str]]:
    merged_fields: dict[str, dict[str, Any]] = {}
    merged_topics: dict[str, dict[str, Any]] = {}
    applied: list[str] = []
    for layer in layers:
        if not layer.scope_key:
            continue
        applied.append(layer.scope_key)
        for code, rule in layer.fields.items():
            merged_fields[code] = _deep_merge_dict(
                merged_fields.get(code, {}),
                rule.model_dump(exclude_none=True),
            )
        for topic_id, rule in layer.topics.items():
            merged_topics[topic_id] = _deep_merge_dict(
                merged_topics.get(topic_id, {}),
                rule.model_dump(exclude_none=True),
            )
    fields = {k: FieldGuardRail.model_validate(v) for k, v in merged_fields.items()}
    topics = {k: TopicGuardRail.model_validate(v) for k, v in merged_topics.items()}
    return fields, topics, applied


def _apply_catalog_gate(
    fields: dict[str, FieldGuardRail],
    topics: dict[str, TopicGuardRail],
    *,
    catalog_ready: bool,
) -> tuple[dict[str, FieldGuardRail], dict[str, TopicGuardRail], bool]:
    if catalog_ready:
        topic_hydrate_enabled = any(
            t.enabled and "topic_hydrate" in t.source_tier for t in topics.values()
        ) or any("topic_hydrate" in f.source_tier for f in fields.values())
        return fields, topics, topic_hydrate_enabled

    gated_fields: dict[str, FieldGuardRail] = {}
    for code, rule in fields.items():
        tiers = [t for t in rule.source_tier if t not in {"topic_hydrate", "topic_summary"}]
        gated_fields[code] = rule.model_copy(
            update={
                "source_tier": tiers or ["lake", "dsi"],
                "llm_extract_allowed": False,
            }
        )

    gated_topics: dict[str, TopicGuardRail] = {}
    for topic_id, rule in topics.items():
        tiers = [t for t in rule.source_tier if t not in {"topic_hydrate", "topic_summary"}]
        enabled = rule.enabled and bool(tiers)
        gated_topics[topic_id] = rule.model_copy(
            update={"source_tier": tiers or ["topic_summary"], "enabled": enabled}
        )

    return gated_fields, gated_topics, False


def merge_guardrails(
    layers: list[GuardRailsScopePayload],
    *,
    catalog_ready: bool = False,
) -> EffectiveGuardRails:
    fields, topics, applied = merge_scope_payloads(layers)
    fields, topics, topic_hydrate_enabled = _apply_catalog_gate(
        fields, topics, catalog_ready=catalog_ready
    )

    payload = {
        "domain": layers[0].domain if layers else "zoning",
        "fields": {k: v.model_dump() for k, v in sorted(fields.items())},
        "topics": {k: v.model_dump() for k, v in sorted(topics.items())},
        "applied_scopes": applied,
        "catalog_ready": catalog_ready,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    version = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    return EffectiveGuardRails(
        domain=layers[0].domain if layers else "zoning",
        fields=fields,
        topics=topics,
        applied_scopes=applied,
        guardrails_version=version,
        topic_hydrate_enabled=topic_hydrate_enabled,
    )
