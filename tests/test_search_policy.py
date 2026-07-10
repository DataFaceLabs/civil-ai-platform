"""Tests for platform search policy resolution."""

import pytest

from civilai_platform.llm_defaults import default_llm_lab_config
from civilai_platform.services.search_policy import (
    resolve_chat_prompts,
    resolve_search_run_policy,
    substitute_search_hint_tokens,
    web_search_provider_configured,
)


def test_substitute_search_hint_tokens() -> None:
    hint = "{GOVERNING_JURIS} code for {active_section}"
    resolved = substitute_search_hint_tokens(
        hint,
        active_section_id="zoning",
        field_context={"GOVERNING_JURIS": "City of Austin"},
    )
    assert resolved == "City of Austin code for zoning"


def test_resolve_search_run_policy_requires_chat_and_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = default_llm_lab_config()
    cfg["chat"]["webSearchEnabled"] = True
    cfg["webSearch"]["enabled"] = False
    policy = resolve_search_run_policy(cfg, active_section_id="zoning")
    assert policy["enabled"] is False

    cfg["webSearch"]["enabled"] = True
    monkeypatch.delenv("CIVILAI_TAVILY_API_KEY", raising=False)
    policy = resolve_search_run_policy(cfg, active_section_id="zoning")
    assert policy["enabled"] is False

    monkeypatch.setenv("CIVILAI_TAVILY_API_KEY", "tvly-test-key")
    policy = resolve_search_run_policy(cfg, active_section_id="zoning")
    assert policy["enabled"] is True
    assert web_search_provider_configured() is True
    assert "zoning" in policy["search_context_hint"]


def test_resolve_chat_prompts() -> None:
    cfg = default_llm_lab_config()
    system_prompt, instructions = resolve_chat_prompts(cfg)
    assert system_prompt
    assert len(instructions) >= 1
