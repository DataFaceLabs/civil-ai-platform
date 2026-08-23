"""App-level LLM Lab baseline - mirrors civil-ai-fe/src/lib/llmLab/defaults.ts."""

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

SHARED_SYSTEM_PROMPT = (
    "You assist civil engineers drafting land-development feasibility studies.\n"
    "Use only the known site facts provided. Do not invent facts, permits, or "
    "utility commitments.\n"
    "Utility service area boundaries do not confirm capacity, pressure, or will-serve.\n"
    "If a fact is unknown or ambiguous, write that it is not currently known and "
    "should be confirmed.\n"
    "Never mention field data, available data, governed fields, or project data "
    "in drafted prose.\n"
    "\n"
    "Draft voice (ACE house style):\n"
    "- Short paragraphs (1-3 sentences). Prefer blank lines between paragraphs in markdown.\n"
    "- Do not use markdown headings (# / ##) or **bold** markers; plain paragraphs only.\n"
    "- One topic per subsection; paraphrase known site facts - do not paste multi-topic dumps.\n"
    '- Cite "(See Exhibit: ...)" only when AVAILABLE_EXHIBITS lists that sheet; '
    "never invent exhibits.\n"
    "- When flood facts include panel_id, cite the FEMA FIRM panel "
    "(and effective date if present).\n"
    "- Do not mash the project site address into Development Services / permit "
    "contact sentences.\n"
    '- Replace robotic stems ("rule extraction pending", "Pending user input.") '
    "with honest gaps."
)

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
    if step_key == "zoning":
        cfg.update(
            {
                "userPromptTemplate": (
                    "Review known zoning facts and suggest concise feasibility language.\n"
                    "If a topic is unknown, write that it is not currently known and should "
                    "be confirmed.\n"
                    "If ZONING_ANALYSIS_BASIS is proposed, label the draft as analyzed under "
                    "proposed zoning and use proposed-rail values.\n"
                    "Zoning regulations: {{field.ZONING_REGS}}\n"
                    "Platting status: {{field.PLATTING_STATUS}}\n"
                    "Impervious cover: {{field.IMPERVIOUS_REGS}}\n"
                    "Impervious cover limit: {{field.IMPERVIOUS_COVER_LIMIT}}\n"
                    "Analysis basis: {{field.ZONING_ANALYSIS_BASIS}}\n"
                    "Scenario: {{field.ZONING_SCENARIO_LABEL}}"
                ),
                "inputFieldCodes": [
                    "ZONING_REGS",
                    "PLATTING_STATUS",
                    "IMPERVIOUS_REGS",
                    "IMPERVIOUS_COVER_LIMIT",
                    "ZONING_ANALYSIS_BASIS",
                    "ZONING_SCENARIO_LABEL",
                ],
                "searchContextHint": (
                    "Prefer official municipal code, LDC, and UDC sources for the governing "
                    "jurisdiction. Use get_zoning_rails / get_zoning_comparisons evidence when "
                    "a Zoning Change scenario is active; do not invent ordinance citations."
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
                    "among the known site facts or the search results, state that it is unverified "
                    "rather than inferring it.\n\n"
                    'Never state a specific fire code edition (e.g. "2021 IFC") unless the '
                    "IFC edition field below has a value. If it is empty, say the current fire "
                    "code adoption should be confirmed with the fire protection district -- do "
                    "not guess an edition from the jurisdiction or fire district name alone.\n\n"
                    "Nearest-main GIS fields and tap cards are proximity / historical evidence "
                    "only — never treat them as capacity, pressure, connection approval, or "
                    "will-serve. If nearest-main detail is empty, say mapped mains were not "
                    "found nearby (or coverage is unknown) rather than inventing distances.\n\n"
                    "Water: {{field.WATER_SERVICE}}\n"
                    "Wastewater: {{field.WASTEWATER_SERVICE}}\n"
                    "Nearest water main: {{field.NEAREST_WATER_MAIN_DETAIL}}\n"
                    "Nearest wastewater main: {{field.NEAREST_WASTEWATER_MAIN_DETAIL}}\n"
                    "Tap cards: {{field.TAP_CARDS}}\n"
                    "Electric provider: {{field.ELECTRIC_PROVIDER}}\n"
                    "Fire protection: {{field.FIRE_PROTECTION}}\n"
                    "IFC edition: {{field.IFC_EDITION}}\n"
                    "Governing jurisdiction: {{field.GOVERNING_JURIS}}\n"
                    "Property: {{field.PROPERTY_ADDRESS}}"
                ),
                "inputFieldCodes": [
                    "WATER_SERVICE",
                    "WASTEWATER_SERVICE",
                    "NEAREST_WATER_MAIN_DETAIL",
                    "NEAREST_WASTEWATER_MAIN_DETAIL",
                    "TAP_CARDS",
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
                    "Do not include a Table of Contents - it is assembled automatically from "
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
            "allowedDomains": list(ATX_CIVIL_SEARCH_DOMAINS),
            "blockedDomains": ["reddit.com", "twitter.com", "facebook.com"],
            "searchDepth": "advanced",
            "includeTraceInResponse": True,
        },
        "chat": dict(DEFAULT_CHAT_CONFIG),
        "sections": sections,
    }
