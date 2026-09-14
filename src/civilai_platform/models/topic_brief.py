"""Topic Hydrate brief models (platform LLM layer)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TopicBriefStatus = Literal[
    "complete",
    "partial",
    "summary_only",
    "skipped",
    "disabled",
    "unavailable",
    "no_sections",
]


class TopicCitation(BaseModel):
    section_id: str
    citation: str = ""
    quote: str = ""


class TopicFieldExtract(BaseModel):
    fe_code: str
    value: str | float | None = None
    section_id: str | None = None
    quote: str | None = None


class TopicBrief(BaseModel):
    topic_id: str
    label: str = ""
    status: TopicBriefStatus
    summary: str = ""
    fields: list[TopicFieldExtract] = Field(default_factory=list)
    citations: list[TopicCitation] = Field(default_factory=list)
    guardrails_version: str = ""
    message: str | None = None


class ZoningBriefRequest(BaseModel):
    jurisdiction_key: str = Field(min_length=1)
    zoning_code: str | None = None
    overlay_codes: list[str] = Field(default_factory=list)
    mha_class: str | None = None
    state_abbr: str | None = None
    county_fips: str | None = None
    topic_ids: list[str] | None = None


class ZoningBriefResponse(BaseModel):
    jurisdiction_key: str
    zoning_code: str | None = None
    topic_hydrate_enabled: bool = False
    guardrails_version: str = ""
    briefs: list[TopicBrief] = Field(default_factory=list)
