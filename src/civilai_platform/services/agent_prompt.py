"""Resolve tenant Prompt Lab configuration for production agent runs.

Prompt Lab defines drafting behavior; the Strands agent executes it.  This module
is the single platform-side adapter between the tenant config document and the
framework-agnostic agent context.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

from civilai_platform.model_presets import resolve_model_id
from civilai_platform.services.draft_voice import (
    apply_draft_voice_to_system_prompt,
    draft_voice_user_reminder,
    sanitize_field_value_for_draft,
)
from civilai_platform.services.search_policy import (
    substitute_search_hint_tokens,
    web_search_provider_configured,
)

_FIELD_TOKEN = re.compile(r"\{\{field\.([A-Z0-9_]+)\}\}")


@dataclass(frozen=True)
class ResolvedSectionAgentPrompt:
    """Canonical prompt/config package for one section-draft run."""

    config_version: int
    section_id: str
    mode: str
    system_prompt: str
    prompt_template: str
    rendered_prompt: str
    input_field_codes: tuple[str, ...]
    model_preset: str
    model_id: str
    temperature: float
    guardrails: dict[str, Any]
    search_run_policy: dict[str, Any]

    def metadata(self) -> dict[str, Any]:
        return asdict(self)


def _nonempty(value: object) -> str:
    return str(value or "").strip()


def _remove_missing_token_line(prompt: str, code: str) -> str:
    """Mirror FE Prompt Lab behavior: omit a whole line when its field is empty."""
    token = "{{field." + code + "}}"
    kept = [line for line in prompt.splitlines() if token not in line]
    return "\n".join(kept)


def _sanitized_field(field_context: dict[str, str], code: str) -> str:
    return sanitize_field_value_for_draft(_nonempty(field_context.get(code)))


def compose_section_template(
    template: str,
    *,
    field_context: dict[str, str],
    input_field_codes: list[str] | tuple[str, ...],
) -> str:
    """Render Prompt Lab field tokens using governed values supplied by the FE.

    Field values are scrubbed of robotic Compose stems before substitution so the
    model is not asked to echo "rule extraction pending" into section.body.
    """
    codes = list(dict.fromkeys([*input_field_codes, *_FIELD_TOKEN.findall(template)]))
    prompt = template
    for code in codes:
        if not _sanitized_field(field_context, code):
            prompt = _remove_missing_token_line(prompt, code)
    prompt = _FIELD_TOKEN.sub(
        lambda match: _sanitized_field(field_context, match.group(1)),
        prompt,
    )
    return re.sub(r"\n{3,}", "\n\n", prompt).strip()


def _field_context_block(field_context: dict[str, str]) -> str:
    return "\n".join(
        f"{code}: {value}"
        for code, value in sorted(
            (code, sanitize_field_value_for_draft(raw.strip()))
            for code, raw in field_context.items()
            if raw.strip()
        )
        if value
    )


def _render_user_prompt(
    *,
    mode: Literal["generate", "refine"],
    rendered_template: str,
    user_guidance: str,
    thread_memory: str,
    section_body_plain: str,
    field_context: dict[str, str],
    fields_unchanged: bool,
) -> str:
    if mode == "generate":
        parts = [rendered_template]
        if user_guidance:
            parts.append(f"Additional guidance:\n{user_guidance}")
        return "\n\n".join(part for part in parts if part.strip()).strip()

    parts = [
        "You are refining an existing feasibility study section draft.",
        "Follow the section drafting requirements and do not contradict governed field values.",
    ]
    if rendered_template:
        parts.append(f"Section drafting requirements:\n{rendered_template}")
    if thread_memory.strip():
        parts.append(thread_memory.strip())
    if section_body_plain.strip():
        parts.append(f"Current draft:\n{section_body_plain.strip()}")
    if fields_unchanged:
        parts.append("Governed field values are unchanged since the last turn.")
    else:
        block = _field_context_block(field_context)
        if block:
            parts.append(f"Governed fields:\n{block}")
    parts.append(f"Analyst request:\n{user_guidance or 'Refine the current draft.'}")
    return "\n\n".join(parts)


def resolve_section_agent_prompt(
    tenant_cfg: dict[str, Any],
    *,
    config_version: int,
    section_id: str,
    field_context: dict[str, str],
    mode: Literal["generate", "refine"] = "generate",
    user_guidance: str = "",
    thread_memory: str = "",
    section_body_plain: str = "",
    fields_unchanged: bool = False,
) -> ResolvedSectionAgentPrompt:
    """Resolve one canonical section prompt from the tenant Prompt Lab config."""
    sections = dict(tenant_cfg.get("sections") or {})
    section = dict(sections.get(section_id) or {})
    template = _nonempty(section.get("userPromptTemplate")) or (
        f"Draft concise feasibility-study language for the {section_id} section "
        "using governed facts."
    )
    raw_codes = section.get("inputFieldCodes")
    input_codes = (
        tuple(str(code).strip() for code in raw_codes if str(code).strip())
        if isinstance(raw_codes, list)
        else ()
    )
    rendered_template = compose_section_template(
        template,
        field_context=field_context,
        input_field_codes=input_codes,
    )
    rendered_prompt = _render_user_prompt(
        mode=mode,
        rendered_template=rendered_template,
        user_guidance=user_guidance.strip(),
        thread_memory=thread_memory,
        section_body_plain=section_body_plain,
        field_context=field_context,
        fields_unchanged=fields_unchanged,
    )
    has_exhibits = bool(_sanitized_field(field_context, "AVAILABLE_EXHIBITS"))
    reminder = draft_voice_user_reminder(has_exhibits=has_exhibits)
    rendered_prompt = f"{rendered_prompt}\n\n{reminder}".strip() if rendered_prompt else reminder

    system_prompt = apply_draft_voice_to_system_prompt(
        _nonempty(tenant_cfg.get("sectionSystemPrompt"))
        or _nonempty(section.get("systemPrompt"))
    )
    model_preset = (
        _nonempty(section.get("modelPreset")) or _nonempty(tenant_cfg.get("modelPreset")) or "haiku"
    )
    raw_guardrails = dict(section.get("guardrails") or {})
    temperature = float(raw_guardrails.get("temperature", 0.2))

    web = dict(tenant_cfg.get("webSearch") or {})
    section_web_enabled = section.get("webSearchEnabled")
    configured_enabled = (
        bool(section_web_enabled)
        if isinstance(section_web_enabled, bool)
        else bool(web.get("enabled", False))
    )
    raw_hint = _nonempty(section.get("searchContextHint"))
    hint = substitute_search_hint_tokens(
        raw_hint,
        active_section_id=section_id,
        field_context=field_context,
    )
    # Prompt Lab stores {{field.CODE}} tokens; support them in search hints too.
    hint = _FIELD_TOKEN.sub(lambda match: _nonempty(field_context.get(match.group(1))), hint)
    search_policy = {
        "enabled": configured_enabled and web_search_provider_configured(),
        "search_context_hint": hint,
        "allowed_domains": tuple(
            str(item).strip() for item in web.get("allowedDomains") or [] if str(item).strip()
        ),
        "blocked_domains": tuple(
            str(item).strip() for item in web.get("blockedDomains") or [] if str(item).strip()
        ),
        "max_queries_per_run": int(web.get("maxQueriesPerInvoke", 3)),
        "query_mode": str(web.get("queryMode", "deterministic")),
    }

    return ResolvedSectionAgentPrompt(
        config_version=config_version,
        section_id=section_id,
        mode=mode,
        system_prompt=system_prompt,
        prompt_template=template,
        rendered_prompt=rendered_prompt,
        input_field_codes=input_codes,
        model_preset=model_preset,
        model_id=resolve_model_id(model_preset),
        temperature=temperature,
        guardrails=raw_guardrails,
        search_run_policy=search_policy,
    )
