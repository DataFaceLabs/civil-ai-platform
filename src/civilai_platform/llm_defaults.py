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
        "systemPrompt": SHARED_SYSTEM_PROMPT,
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
                "inputFieldCodes": ["WATER_SERVICE", "WASTEWATER_SERVICE"],
                "guardrails": {
                    **BASE_GUARDRAILS,
                    "requiredDisclaimers": ["boundary only", "confirm with provider"],
                },
            }
        )
    return cfg


def default_llm_lab_config() -> dict[str, Any]:
    sections = {key: _section_config(key) for key in LLM_SECTION_STEP_KEYS}
    return {
        "version": 1,
        "modelPreset": "haiku",
        "responseMode": "structured",
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
        "sections": sections,
    }
