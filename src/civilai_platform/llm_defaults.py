"""App-level LLM Lab baseline - mirrors civil-ai-fe/src/lib/llmLab/defaults.ts."""

from __future__ import annotations

from typing import Any

from civilai_platform.prompt_catalog import (
    catalog_section_keys,
    load_section_system_prompt,
    section_prompt_overrides,
)

LLM_SECTION_STEP_KEYS = [
    "parcel",
    "zoning",
    "environmental",
    "utilities",
    "access",
    "exhibits",
    "draft",
]

# Shared ArcGIS viewer hosts from ATX's Tier B list are connector-discovery links,
# not trusted publication domains for agent web search.
ATX_CIVIL_SEARCH_DOMAINS = [
    "texas.gov",
    "fema.gov",
    "usda.gov",
    "austintexas.gov",
    "traviscad.org",
    "tccsearch.org",
    "traviscountytx.gov",
    "txdot.gov",
    "municode.com",
]

# LLM Lab Section draft system prompt — sole style/format authority for section drafts.
SHARED_SYSTEM_PROMPT = load_section_system_prompt()

DEFAULT_CHAT_CONFIG: dict[str, Any] = {
    "systemPrompt": (
        "You are the civil1.ai assistant helping analysts draft land-development "
        "feasibility studies.\n"
        "Use known site facts and conversation context. Do not invent facts, permits, "
        "or utility commitments.\n"
        "Utility service area boundaries do not confirm capacity, pressure, or will-serve."
    ),
    "instructions": [
        "Respond in clear plain text for the chat panel.",
        (
            "Answer factual questions directly; do not output a full section draft "
            "unless the analyst explicitly asks you to rewrite the section."
        ),
        (
            "Answer from known site facts first; supplement only with web search "
            "URLs/snippets returned in this run."
        ),
        (
            "If information is still missing, write that it is not currently known "
            "and which agency or document to verify - do not invent contacts."
        ),
        (
            "For contact answers, format each agency as its own block: name, address, "
            "phone, email when available."
        ),
        "Cite URLs only when returned by web_search_deduped in this run.",
    ],
    "webSearchEnabled": False,
    "searchContextHint": (
        "{GOVERNING_JURIS} utility provider permitting contact OSSF {active_section}"
    ),
}

BASE_GUARDRAILS: dict[str, Any] = {
    # Structured (JSON) drafts must fit content_markdown + caveats + data_gaps + a
    # sources array in one response; 1024 (floored to 2048 server-side) truncates the
    # JSON on web-search sections and fails parsing. 4096 leaves headroom under the
    # Bedrock structured cap (8192).
    "maxOutputTokens": 4096,
    "temperature": 0.2,
    "forbiddenPhrases": [
        "will-serve",
        "guaranteed capacity",
        "confirmed service commitment",
    ],
    "requiredDisclaimers": [],
    "enforceGuardrails": True,
}


def _section_config(step_key: str) -> dict[str, Any]:
    title = step_key.replace("_", " ").title()
    cfg: dict[str, Any] = {
        "stepKey": step_key,
        "userPromptTemplate": (
            f"Review the known site facts for the {title} section and suggest concise "
            "feasibility study language. If a topic is unknown, write that it is not "
            "currently known and should be confirmed."
        ),
        "inputFieldCodes": [],
        "guardrails": dict(BASE_GUARDRAILS),
        "searchContextHint": "",
    }
    if step_key in catalog_section_keys():
        cfg.update(section_prompt_overrides(step_key))
    return cfg


def default_llm_lab_config() -> dict[str, Any]:
    sections = {key: _section_config(key) for key in LLM_SECTION_STEP_KEYS}
    return {
        "version": 1,
        "modelPreset": "haiku",
        "responseMode": "structured",
        "sectionSystemPrompt": SHARED_SYSTEM_PROMPT,
        "webSearch": {
            "enabled": False,
            "executionMode": "server",
            "queryMode": "deterministic",
            "restrictProviderDomains": False,
            "maxQueriesPerInvoke": 3,
            "maxResultsPerQuery": 5,
            "allowedDomains": list(ATX_CIVIL_SEARCH_DOMAINS),
            "blockedDomains": ["reddit.com", "twitter.com", "facebook.com"],
            "searchDepth": "advanced",
            "includeTraceInResponse": True,
        },
        "chat": dict(DEFAULT_CHAT_CONFIG),
        "sections": sections,
    }
