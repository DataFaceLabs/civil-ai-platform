from civilai_platform.services import llm_invoke as llm_invoke_svc


def test_resolve_web_search_enabled_request_override() -> None:
    assert (
        llm_invoke_svc._resolve_web_search_enabled(
            web_search_cfg={"enabled": False},
            section={"webSearchEnabled": False},
            request_override=True,
        )
        is True
    )


def test_resolve_web_search_enabled_section_opt_out() -> None:
    assert (
        llm_invoke_svc._resolve_web_search_enabled(
            web_search_cfg={"enabled": True},
            section={"webSearchEnabled": False},
            request_override=None,
        )
        is False
    )


def test_resolve_web_search_enabled_inherits_global() -> None:
    assert (
        llm_invoke_svc._resolve_web_search_enabled(
            web_search_cfg={"enabled": True},
            section={},
            request_override=None,
        )
        is True
    )


def test_resolve_web_search_enabled_draft_always_off() -> None:
    assert (
        llm_invoke_svc._resolve_web_search_enabled(
            web_search_cfg={"enabled": True},
            section={"webSearchEnabled": True},
            request_override=True,
            step_key="draft",
        )
        is False
    )


def test_resolve_guardrails_chat_uses_base_without_section_disclaimers() -> None:
    section = {
        "guardrails": {
            "maxOutputTokens": 1024,
            "temperature": 0.2,
            "forbiddenPhrases": [],
            "requiredDisclaimers": ["boundary only", "confirm with provider"],
            "enforceGuardrails": True,
        }
    }
    chat = llm_invoke_svc._resolve_guardrails(section=section, invoke_mode="chat")
    section_guardrails = llm_invoke_svc._resolve_guardrails(section=section, invoke_mode="section")

    assert chat["required_disclaimers"] == []
    assert section_guardrails["required_disclaimers"] == ["boundary only", "confirm with provider"]


def test_resolve_guardrails_draft_raises_output_token_floor() -> None:
    section = {"guardrails": {"maxOutputTokens": 1024}}
    guardrails = llm_invoke_svc._resolve_guardrails(
        section=section,
        invoke_mode="section",
        step_key="draft",
    )
    assert guardrails["max_output_tokens"] == 4096


def test_resolve_guardrails_structured_web_search_raises_output_token_floor() -> None:
    # Structured JSON + web search emits a sources array; a 1024 cap truncates the JSON.
    section = {"guardrails": {"maxOutputTokens": 1024}}
    guardrails = llm_invoke_svc._resolve_guardrails(
        section=section,
        invoke_mode="section",
        step_key="utilities",
        response_mode="structured",
        web_search_enabled=True,
    )
    assert guardrails["max_output_tokens"] == 4096


def test_resolve_guardrails_structured_without_web_search_keeps_section_cap() -> None:
    # No web search means no sources array, so the per-section budget is left untouched.
    section = {"guardrails": {"maxOutputTokens": 1024}}
    guardrails = llm_invoke_svc._resolve_guardrails(
        section=section,
        invoke_mode="section",
        step_key="utilities",
        response_mode="structured",
        web_search_enabled=False,
    )
    assert guardrails["max_output_tokens"] == 1024


def test_resolve_guardrails_web_search_respects_higher_section_cap() -> None:
    section = {"guardrails": {"maxOutputTokens": 8192}}
    guardrails = llm_invoke_svc._resolve_guardrails(
        section=section,
        invoke_mode="section",
        step_key="utilities",
        response_mode="structured",
        web_search_enabled=True,
    )
    assert guardrails["max_output_tokens"] == 8192


def test_resolve_response_mode_draft_uses_text() -> None:
    assert (
        llm_invoke_svc._resolve_response_mode(
            tenant_cfg={"responseMode": "structured"},
            invoke_mode="section",
            step_key="draft",
        )
        == "text"
    )


def test_resolve_model_preset_section_override() -> None:
    assert (
        llm_invoke_svc._resolve_model_preset(
            tenant_cfg={"modelPreset": "haiku"},
            section={"modelPreset": "opus"},
        )
        == "opus"
    )


def test_resolve_model_preset_inherits_global() -> None:
    assert (
        llm_invoke_svc._resolve_model_preset(
            tenant_cfg={"modelPreset": "sonnet"},
            section={},
        )
        == "sonnet"
    )


def test_resolve_response_mode_section_honors_tenant_structured() -> None:
    assert (
        llm_invoke_svc._resolve_response_mode(
            tenant_cfg={"responseMode": "structured"},
            invoke_mode="section",
            step_key="zoning",
        )
        == "structured"
    )
