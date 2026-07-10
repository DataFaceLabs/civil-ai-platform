"""App-level LLM Lab baseline — mirrors civil-ai-fe/src/lib/llmLab/defaults.ts."""

from __future__ import annotations

from typing import Any

LLM_SECTION_STEP_KEYS = [
    "parcel",
    "zoning",
    "environmental",
    "utilities",
    "access",
    "exhibits",
    "draft",
]

SHARED_SYSTEM_PROMPT = (
    "You assist civil engineers drafting land-development feasibility studies.\n"
    "Use only the field values provided. Do not invent facts, permits, or utility commitments.\n"
    "Utility service area boundaries do not confirm capacity, pressure, or will-serve.\n"
    "If field values are empty or ambiguous, state what is unknown and recommend verification."
)

DEFAULT_CHAT_CONFIG: dict[str, Any] = {
    "systemPrompt": (
        "You are the civil.ai assistant helping analysts draft land-development feasibility studies.\n"
        "Use governed field values and conversation context. Do not invent facts, permits, or utility commitments.\n"
        "Utility service area boundaries do not confirm capacity, pressure, or will-serve."
    ),
    "instructions": [
        "Respond in clear plain text for the chat panel.",
        "Answer factual questions directly; do not output a full section draft unless the analyst explicitly asks you to rewrite the section.",
        "Answer from governed field values first; supplement only with web search URLs/snippets returned in this run.",
        "If information is still missing, state what is unknown and which agency or document to verify — do not invent contacts.",
        "For contact answers, format each agency as its own block: name, address, phone, email when available.",
        "Cite URLs only when returned by web_search_deduped in this run.",
    ],
    "webSearchEnabled": False,
    "searchContextHint": "{GOVERNING_JURIS} utility provider permitting contact OSSF {active_section}",
}

BASE_GUARDRAILS: dict[str, Any] = {
    "maxOutputTokens": 1024,
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
            f"Review the {title} section field values and suggest concise feasibility study language."
        ),
        "inputFieldCodes": [],
        "guardrails": dict(BASE_GUARDRAILS),
        "searchContextHint": "",
    }
    if step_key == "zoning":
        cfg.update(
            {
                "userPromptTemplate": (
                    "Review zoning-related field values and suggest concise feasibility language.\n"
                    "Zoning regulations: {{field.ZONING_REGS}}\n"
                    "Platting status: {{field.PLATTING_STATUS}}\n"
                    "Impervious cover: {{field.IMPERVIOUS_REGS}}"
                ),
                "inputFieldCodes": ["ZONING_REGS", "PLATTING_STATUS", "IMPERVIOUS_REGS"],
                "searchContextHint": (
                    "Prefer official municipal code, LDC, and UDC sources for the governing jurisdiction."
                ),
            }
        )
    elif step_key == "utilities":
        cfg.update(
            {
                "userPromptTemplate": (
                    "Review utility boundary fields and suggest cautious feasibility language "
                    "that does not imply capacity or will-serve.\n"
                    "Water: {{field.WATER_SERVICE}}\n"
                    "Wastewater: {{field.WASTEWATER_SERVICE}}"
                ),
                "inputFieldCodes": [
                    "WATER_SERVICE",
                    "WASTEWATER_SERVICE",
                    "ELECTRIC_PROVIDER",
                    "FIRE_PROTECTION",
                    "OSSF_REQUIREMENTS",
                    "GOVERNING_JURIS",
                    "PROPERTY_ADDRESS",
                ],
                "guardrails": {
                    **BASE_GUARDRAILS,
                    "requiredDisclaimers": ["boundary only", "confirm with provider"],
                },
                "searchContextHint": (
                    "Prefer PUC Texas CCN maps, municipal utility provider pages, and TCEQ OSSF "
                    "guidance for {{field.GOVERNING_JURIS}}."
                ),
            }
        )
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
            "allowedDomains": [
                "*.texas.gov",
                "municode.com",
                "library.municode.com",
                "austintexas.gov",
                "tcad.org",
            ],
            "blockedDomains": ["reddit.com", "twitter.com", "facebook.com"],
            "searchDepth": "basic",
            "includeTraceInResponse": True,
        },
        "chat": dict(DEFAULT_CHAT_CONFIG),
        "sections": sections,
    }
