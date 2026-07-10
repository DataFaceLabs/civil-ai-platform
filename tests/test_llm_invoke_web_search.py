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
