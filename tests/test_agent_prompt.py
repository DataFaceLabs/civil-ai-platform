from civilai_platform.services.agent_prompt import (
    compose_section_template,
    resolve_section_agent_prompt,
)


def test_compose_section_template_removes_empty_field_lines() -> None:
    prompt = compose_section_template(
        "Draft zoning.\nDistrict: {{field.ZONING_DISTRICT}}\nNotes: {{field.ZONING_REGS}}",
        field_context={"ZONING_DISTRICT": "MF-4", "ZONING_REGS": ""},
        input_field_codes=["ZONING_DISTRICT", "ZONING_REGS"],
    )

    assert prompt == "Draft zoning.\nDistrict: MF-4"


def test_resolve_section_prompt_uses_prompt_lab_config(monkeypatch) -> None:
    monkeypatch.setenv("CIVILAI_TAVILY_API_KEY", "test-key")
    config = {
        "version": 7,
        "modelPreset": "haiku",
        "sectionSystemPrompt": "Write as a cautious civil engineer.",
        "webSearch": {
            "enabled": True,
            "allowedDomains": ["austintexas.gov"],
            "blockedDomains": ["example.com"],
            "maxQueriesPerInvoke": 2,
            "queryMode": "deterministic",
        },
        "sections": {
            "zoning": {
                "modelPreset": "sonnet46",
                "userPromptTemplate": (
                    "Draft zoning feasibility language.\nDistrict: {{field.ZONING_DISTRICT}}"
                ),
                "inputFieldCodes": ["ZONING_DISTRICT"],
                "webSearchEnabled": True,
                "searchContextHint": "{{field.PROPERTY_ADDRESS}} zoning ordinance",
                "guardrails": {
                    "temperature": 0.1,
                    "forbiddenPhrases": ["guaranteed approval"],
                    "requiredDisclaimers": [],
                    "enforceGuardrails": True,
                },
            }
        },
    }

    resolved = resolve_section_agent_prompt(
        config,
        config_version=7,
        section_id="zoning",
        field_context={
            "ZONING_DISTRICT": "MF-4",
            "PROPERTY_ADDRESS": "123 Main St",
        },
        user_guidance="Keep it concise.",
    )

    assert resolved.system_prompt == "Write as a cautious civil engineer."
    assert "District: MF-4" in resolved.rendered_prompt
    assert "Additional guidance:\nKeep it concise." in resolved.rendered_prompt
    assert resolved.model_preset == "sonnet46"
    assert resolved.model_id == "us.anthropic.claude-sonnet-4-6"
    assert resolved.temperature == 0.1
    assert resolved.guardrails["enforceGuardrails"] is True
    assert resolved.search_run_policy["enabled"] is True
    assert resolved.search_run_policy["search_context_hint"] == "123 Main St zoning ordinance"


def test_refine_prompt_includes_current_draft_and_analyst_request() -> None:
    resolved = resolve_section_agent_prompt(
        {
            "modelPreset": "haiku",
            "sectionSystemPrompt": "System",
            "sections": {
                "utilities": {
                    "userPromptTemplate": "Draft utilities using {{field.WATER_SERVICE}}.",
                    "inputFieldCodes": ["WATER_SERVICE"],
                    "guardrails": {},
                }
            },
        },
        config_version=1,
        section_id="utilities",
        field_context={"WATER_SERVICE": "Austin Water"},
        mode="refine",
        user_guidance="Add the wastewater caveat.",
        section_body_plain="Austin Water may serve the site.",
        fields_unchanged=True,
    )

    assert "Section drafting requirements:" in resolved.rendered_prompt
    assert "Current draft:\nAustin Water may serve the site." in resolved.rendered_prompt
    assert "Governed field values are unchanged" in resolved.rendered_prompt
    assert "Analyst request:\nAdd the wastewater caveat." in resolved.rendered_prompt
