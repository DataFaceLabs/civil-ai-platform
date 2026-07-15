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
        "You are the civil1.ai assistant helping analysts draft land-development feasibility studies.\n"
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
                    "Review the utility boundary fields and draft cautious feasibility language "
                    "that does not imply capacity, pressure, or will-serve.\n\n"
                    "Using only the web search results returned in this run, extract and "
                    "incorporate any of these that appear: the water and wastewater CCN holder "
                    "and CCN number, the electric provider, and published OSSF (on-site sewage) "
                    "requirements for the jurisdiction. Attribute each web-sourced fact to its "
                    "source URL and cite only sources returned by the search. If a fact is not "
                    "in the field values or the search results, state that it is unverified "
                    "rather than inferring it.\n\n"
                    "Never state a specific fire code edition (e.g. \"2021 IFC\") unless the "
                    "IFC edition field below has a value. If it is empty, say the current fire "
                    "code adoption should be confirmed with the fire protection district -- do "
                    "not guess an edition from the jurisdiction or fire district name alone.\n\n"
                    "Water: {{field.WATER_SERVICE}}\n"
                    "Wastewater: {{field.WASTEWATER_SERVICE}}\n"
                    "Electric provider: {{field.ELECTRIC_PROVIDER}}\n"
                    "Fire protection: {{field.FIRE_PROTECTION}}\n"
                    "IFC edition: {{field.IFC_EDITION}}\n"
                    "Governing jurisdiction: {{field.GOVERNING_JURIS}}\n"
                    "Property: {{field.PROPERTY_ADDRESS}}"
                ),
                "inputFieldCodes": [
                    "WATER_SERVICE",
                    "WASTEWATER_SERVICE",
                    "ELECTRIC_PROVIDER",
                    "FIRE_PROTECTION",
                    "IFC_EDITION",
                    "OSSF_REQUIREMENTS",
                    "GOVERNING_JURIS",
                    "PROPERTY_ADDRESS",
                ],
                "guardrails": {
                    **BASE_GUARDRAILS,
                    "requiredDisclaimers": ["boundary only", "confirm with provider"],
                },
                "webSearchEnabled": True,
                "searchContextHint": (
                    "Find the water and wastewater CCN holder and CCN number, the electric "
                    "utility provider, and OSSF requirements for {{field.PROPERTY_ADDRESS}} in "
                    "{{field.GOVERNING_JURIS}}. Prefer PUC Texas CCN maps and records, the "
                    "municipal utility provider's pages, and TCEQ OSSF guidance."
                ),
            }
        )
    elif step_key == "draft":
        cfg.update(
            {
                "userPromptTemplate": (
                    "Polish the merged feasibility study section content below into a cohesive, "
                    "client-ready report body.\n\n"
                    "Do not include a Table of Contents — it is assembled automatically from "
                    "your headings after generation.\n\n"
                    "Use h2 headings for each major section that has source content (for example "
                    "Parcel, Zoning, Environmental, Utilities, Access, Recommendations). Use h3 "
                    "headings for logical subsections within each major section. Do not "
                    "duplicate section titles in body paragraphs. Preserve factual content from "
                    "the merged sections. Use concise professional engineering prose.\n\n"
                    "Site: {{field.PROPERTY_ADDRESS}}\n"
                    "Governing jurisdiction: {{field.GOVERNING_JURIS}}\n"
                    "Proposed development: {{field.PROPOSED_DEVELOPMENT}}"
                ),
                "inputFieldCodes": [
                    "PROPERTY_ADDRESS",
                    "GOVERNING_JURIS",
                    "PROPOSED_DEVELOPMENT",
                ],
                "guardrails": {
                    **BASE_GUARDRAILS,
                    "maxOutputTokens": 4096,
                },
                "webSearchEnabled": False,
                "searchContextHint": "",
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
            "searchDepth": "advanced",
            "includeTraceInResponse": True,
        },
        "chat": dict(DEFAULT_CHAT_CONFIG),
        "sections": sections,
    }
