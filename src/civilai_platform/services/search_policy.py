"""Resolve SearchRunPolicy from tenant LLM config for agent orchestration."""

from __future__ import annotations

import os
from typing import Any


def _as_str_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def substitute_search_hint_tokens(
    hint: str,
    *,
    active_section_id: str | None = None,
    field_context: dict[str, str] | None = None,
) -> str:
    """Replace simple tokens in admin search hints before agent prefetch."""
    resolved = hint
    if active_section_id:
        resolved = resolved.replace("{active_section}", active_section_id)
    if field_context:
        for code, value in field_context.items():
            token = "{" + code + "}"
            if token in resolved and value.strip():
                resolved = resolved.replace(token, value.strip())
    return resolved


def web_search_provider_configured() -> bool:
    """True when the platform process has credentials for the configured search provider."""
    provider = os.getenv("CIVILAI_WEB_SEARCH_PROVIDER", "tavily").strip().lower()
    if provider == "tavily":
        return bool(os.getenv("CIVILAI_TAVILY_API_KEY", "").strip())
    return False


def resolve_search_run_policy(
    tenant_cfg: dict[str, Any],
    *,
    active_section_id: str | None = None,
    field_context: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a SearchRunPolicy dict from tenant chat + global webSearch settings."""
    chat = dict(tenant_cfg.get("chat") or {})
    web = dict(tenant_cfg.get("webSearch") or {})
    chat_enabled = bool(chat.get("webSearchEnabled", False))
    provider_enabled = bool(web.get("enabled", False))
    runtime_configured = web_search_provider_configured()
    hint = substitute_search_hint_tokens(
        str(chat.get("searchContextHint") or ""),
        active_section_id=active_section_id,
        field_context=field_context,
    )
    return {
        "enabled": chat_enabled and provider_enabled and runtime_configured,
        "search_context_hint": hint,
        "allowed_domains": tuple(_as_str_list(web.get("allowedDomains"))),
        "blocked_domains": tuple(_as_str_list(web.get("blockedDomains"))),
        "max_queries_per_run": int(web.get("maxQueriesPerInvoke", 3)),
        "query_mode": str(web.get("queryMode", "deterministic")),
    }


def resolve_chat_prompts(tenant_cfg: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    """Extract chat system prompt and instruction lines from tenant config."""
    chat = dict(tenant_cfg.get("chat") or {})
    system_prompt = str(chat.get("systemPrompt") or "").strip()
    raw_instructions = chat.get("instructions")
    if isinstance(raw_instructions, list):
        instructions = tuple(
            str(item).strip() for item in raw_instructions if str(item).strip()
        )
    else:
        instructions = ()
    return system_prompt, instructions
