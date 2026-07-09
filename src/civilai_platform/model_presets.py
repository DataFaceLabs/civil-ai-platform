"""LLM Lab model preset keys → provider model IDs (mirrors civil-ai-fe openaiModelPresets + Bedrock)."""

from __future__ import annotations

MODEL_PRESET_IDS: dict[str, str] = {
    # Amazon Bedrock
    "haiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "sonnet": "us.anthropic.claude-sonnet-5",
    "sonnet46": "us.anthropic.claude-sonnet-4-6",
    "nova": "amazon.nova-lite-v1:0",
    "opus": "us.anthropic.claude-opus-4-6-20260201-v1:0",
    # OpenAI GPT-5.5
    "gpt55": "gpt-5.5",
    "gpt55pro": "gpt-5.5-pro",
    # OpenAI GPT-5.4
    "gpt54": "gpt-5.4",
    "gpt54mini": "gpt-5.4-mini",
    "gpt54nano": "gpt-5.4-nano",
    # OpenAI GPT-5
    "gpt5": "gpt-5",
    "gpt5mini": "gpt-5-mini",
    "gpt5nano": "gpt-5-nano",
    # OpenAI GPT-4.1
    "gpt41": "gpt-4.1",
    "gpt41mini": "gpt-4.1-mini",
    "gpt41nano": "gpt-4.1-nano",
    # OpenAI GPT-4o
    "gpt4o": "gpt-4o",
    "gpt4omini": "gpt-4o-mini",
    # OpenAI o-series
    "o1": "o1",
    "o1mini": "o1-mini",
    "o1pro": "o1-pro",
    "o3": "o3",
    "o3mini": "o3-mini",
    "o4mini": "o4-mini",
}

_DEFAULT_PRESET = "haiku"


def resolve_model_id(model_preset: str) -> str:
    """Map a tenant ``modelPreset`` key to the provider model ID."""
    key = model_preset.strip()
    if key in MODEL_PRESET_IDS:
        return MODEL_PRESET_IDS[key]
    return MODEL_PRESET_IDS[_DEFAULT_PRESET]
