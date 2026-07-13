"""Platform-mediated section LLM invoke — loads tenant config server-side."""

from __future__ import annotations

from typing import Any

from civilai_platform.llm_defaults import BASE_GUARDRAILS
from civilai_platform.model_presets import resolve_model_id
from civilai_platform.services import llm_config as llm_config_svc
from civilai_platform.services.audit import record_audit
from civilai_platform.services.data_proxy import DataProxyClient
from civilai_platform.services.search_policy import resolve_chat_prompts, resolve_search_run_policy
from civilai_platform.store.base import PlatformStore


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


def _resolve_web_search_enabled(
    *,
    web_search_cfg: dict[str, Any],
    section: dict[str, Any],
    request_override: bool | None = None,
    step_key: str = "",
) -> bool:
    # Draft assembly polishes merged section narratives; web search adds latency without benefit.
    if step_key == "draft":
        return False
    if request_override is not None:
        return request_override
    section_flag = section.get("webSearchEnabled")
    if isinstance(section_flag, bool):
        return section_flag
    return bool(web_search_cfg.get("enabled", False))


_STRUCTURED_WEB_SEARCH_TOKEN_FLOOR = 4096


def _resolve_guardrails(
    *,
    section: dict[str, Any],
    invoke_mode: str,
    step_key: str = "",
    response_mode: str = "structured",
    web_search_enabled: bool = False,
) -> dict[str, Any]:
    """Chat Q&A uses base guardrails; section drafts keep per-section disclaimers."""
    if invoke_mode == "chat":
        return _snake_guardrails(dict(BASE_GUARDRAILS))
    guardrails = _snake_guardrails(dict(section.get("guardrails") or {}))
    # Full-document assembly needs a much larger prose budget than single-section drafts.
    if step_key == "draft":
        guardrails["max_output_tokens"] = max(
            int(guardrails["max_output_tokens"]), _STRUCTURED_WEB_SEARCH_TOKEN_FLOOR
        )
    # Structured JSON drafts that run web search must also fit content_markdown plus a
    # sources array in one response; a low per-section cap truncates the JSON mid-value
    # and fails schema parsing in the data API. Guarantee headroom regardless of the
    # per-section setting.
    elif response_mode == "structured" and web_search_enabled:
        guardrails["max_output_tokens"] = max(
            int(guardrails["max_output_tokens"]), _STRUCTURED_WEB_SEARCH_TOKEN_FLOOR
        )
    return guardrails


def _resolve_response_mode(
    *,
    tenant_cfg: dict[str, Any],
    invoke_mode: str,
    step_key: str,
) -> str:
    """Draft document assembly returns Markdown prose, not structured JSON."""
    if invoke_mode == "chat" or step_key == "draft":
        return "text"
    return str(tenant_cfg.get("responseMode", "structured"))


def _resolve_model_preset(
    *,
    tenant_cfg: dict[str, Any],
    section: dict[str, Any],
) -> str:
    section_preset = section.get("modelPreset")
    if isinstance(section_preset, str) and section_preset.strip():
        return section_preset.strip()
    return str(tenant_cfg.get("modelPreset", "haiku"))


def _resolve_system_prompt(
    *,
    tenant_cfg: dict[str, Any],
    section: dict[str, Any],
    invoke_mode: str,
) -> str:
    if invoke_mode == "chat":
        chat_system, chat_instructions = resolve_chat_prompts(tenant_cfg)
        system_prompt = chat_system
        if chat_instructions:
            instruction_lines = "\n".join(f"- {line}" for line in chat_instructions)
            system_prompt = f"{system_prompt}\n\nInstructions:\n{instruction_lines}".strip()
        return system_prompt

    legacy_section_prompt = str(section.get("systemPrompt") or "")
    return str(tenant_cfg.get("sectionSystemPrompt") or legacy_section_prompt or "")


def invoke_tenant_section_llm(
    store: PlatformStore,
    *,
    tenant_id: str,
    actor_user_id: str,
    step_key: str,
    user_prompt: str,
    field_context: dict[str, str],
    search_context_hint: str = "",
    invoke_mode: str = "section",
    web_search_enabled: bool | None = None,
    client: DataProxyClient | None = None,
) -> dict[str, Any]:
    tenant_cfg = llm_config_svc.get_tenant_llm_response(store, tenant_id).config
    sections = tenant_cfg.get("sections") or {}
    section = sections.get(step_key) or {}
    preset = _resolve_model_preset(tenant_cfg=tenant_cfg, section=section)
    model_id = resolve_model_id(preset)
    system_prompt = _resolve_system_prompt(
        tenant_cfg=tenant_cfg,
        section=section,
        invoke_mode=invoke_mode,
    )
    web_search_cfg = dict(tenant_cfg.get("webSearch") or {})
    if invoke_mode == "chat":
        chat_search = resolve_search_run_policy(
            tenant_cfg,
            active_section_id=step_key,
            field_context=field_context,
        )
        web_enabled = (
            bool(web_search_enabled)
            if web_search_enabled is not None
            else bool(chat_search.get("enabled", False))
        )
        resolved_search_hint = search_context_hint or str(chat_search.get("search_context_hint") or "")
    else:
        web_enabled = _resolve_web_search_enabled(
            web_search_cfg=web_search_cfg,
            section=section,
            request_override=web_search_enabled,
            step_key=step_key,
        )
        resolved_search_hint = search_context_hint or str(section.get("searchContextHint") or "")
    response_mode = _resolve_response_mode(
        tenant_cfg=tenant_cfg,
        invoke_mode=invoke_mode,
        step_key=step_key,
    )
    body = {
        "model_id": model_id,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "field_context": field_context,
        "response_mode": response_mode,
        "guardrails": _resolve_guardrails(
            section=section,
            invoke_mode=invoke_mode,
            step_key=step_key,
            response_mode=response_mode,
            web_search_enabled=web_enabled,
        ),
        "web_search": _snake_web_search(
            web_search_cfg,
            search_context_hint=resolved_search_hint,
            enabled=web_enabled,
        ),
    }
    proxy = client or DataProxyClient()
    result = proxy.invoke_llm(body, step_key=step_key)
    record_audit(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="tenant_llm.invoke",
        resource_type="llm_invoke",
        resource_id=step_key,
    )
    return result
