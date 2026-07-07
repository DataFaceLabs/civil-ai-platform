"""Platform-mediated section LLM invoke — loads tenant config server-side."""

from __future__ import annotations

from typing import Any

from civilai_platform.services import llm_config as llm_config_svc
from civilai_platform.services.audit import record_audit
from civilai_platform.services.data_proxy import DataProxyClient
from civilai_platform.store.base import PlatformStore

MODEL_PRESET_IDS: dict[str, str] = {
    "haiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "sonnet": "us.anthropic.claude-sonnet-5",
    "nova": "amazon.nova-lite-v1:0",
    "opus": "us.anthropic.claude-opus-4-6-20260201-v1:0",
    "gpt-4o-mini": "gpt-4o-mini",
    "gpt-4o": "gpt-4o",
}


def _snake_guardrails(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "max_output_tokens": raw.get("maxOutputTokens", 1024),
        "temperature": raw.get("temperature", 0.2),
        "forbidden_phrases": list(raw.get("forbiddenPhrases") or []),
        "required_disclaimers": list(raw.get("requiredDisclaimers") or []),
        "enforce_guardrails": bool(raw.get("enforceGuardrails", False)),
    }


def _snake_web_search(raw: dict[str, Any], *, search_context_hint: str, enabled: bool) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "execution_mode": raw.get("executionMode", "server"),
        "query_mode": raw.get("queryMode", "deterministic"),
        "restrict_provider_domains": bool(raw.get("restrictProviderDomains", False)),
        "max_queries_per_invoke": int(raw.get("maxQueriesPerInvoke", 3)),
        "max_results_per_query": int(raw.get("maxResultsPerQuery", 5)),
        "allowed_domains": list(raw.get("allowedDomains") or []),
        "blocked_domains": list(raw.get("blockedDomains") or []),
        "search_depth": raw.get("searchDepth", "basic"),
        "search_context_hint": search_context_hint,
        "include_trace_in_response": bool(raw.get("includeTraceInResponse", True)),
    }


def invoke_tenant_section_llm(
    store: PlatformStore,
    *,
    tenant_id: str,
    actor_user_id: str,
    step_key: str,
    user_prompt: str,
    field_context: dict[str, str],
    search_context_hint: str = "",
    client: DataProxyClient | None = None,
) -> dict[str, Any]:
    tenant_cfg = llm_config_svc.get_tenant_llm_response(store, tenant_id).config
    sections = tenant_cfg.get("sections") or {}
    section = sections.get(step_key) or {}
    preset = str(tenant_cfg.get("modelPreset", "haiku"))
    model_id = MODEL_PRESET_IDS.get(preset, MODEL_PRESET_IDS["haiku"])
    web_search_cfg = dict(tenant_cfg.get("webSearch") or {})
    section_web_enabled = section.get("webSearchEnabled")
    web_enabled = (
        bool(section_web_enabled)
        if isinstance(section_web_enabled, bool)
        else bool(web_search_cfg.get("enabled", False))
    )
    body = {
        "model_id": model_id,
        "system_prompt": str(section.get("systemPrompt") or ""),
        "user_prompt": user_prompt,
        "field_context": field_context,
        "response_mode": tenant_cfg.get("responseMode", "structured"),
        "guardrails": _snake_guardrails(dict(section.get("guardrails") or {})),
        "web_search": _snake_web_search(
            web_search_cfg,
            search_context_hint=search_context_hint
            or str(section.get("searchContextHint") or ""),
            enabled=web_enabled,
        ),
    }
    proxy = client or DataProxyClient()
    result = proxy.invoke_llm(body)
    record_audit(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="tenant_llm.invoke",
        resource_type="llm_invoke",
        resource_id=step_key,
    )
    return result
