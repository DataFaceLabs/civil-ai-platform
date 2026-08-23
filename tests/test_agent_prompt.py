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


def test_compose_section_template_keeps_mixed_token_lines() -> None:
    prompt = compose_section_template(
        "size:{{field.PROPERTY_ACRES}} , land use:{{field.TCAD_LAND_USE}}, "
        "{{field.EXISTING_DEVELOPMENT}}",
        field_context={
            "PROPERTY_ACRES": "10.00",
            "EXISTING_DEVELOPMENT": "Barn",
        },
        input_field_codes=[],
    )

    assert prompt == "size:10.00 , land use:, Barn"


def test_compose_section_template_resolves_legacy_tcad_aliases() -> None:
    prompt = compose_section_template(
        "Land use: {{field.TCAD_LAND_USE}}\nLegal: {{field.TCAD_LEGAL_DESCRIPTION}}",
        field_context={
            "CAD_LAND_USE": "A1 — SFR",
            "CAD_LEGAL_DESCRIPTION": "LOT 10 BLK O",
        },
        input_field_codes=[],
    )

    assert prompt == "Land use: A1 — SFR\nLegal: LOT 10 BLK O"


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

    assert "Write as a cautious civil engineer." in resolved.system_prompt
    assert "Draft voice (ACE house style" in resolved.system_prompt
    assert "District: MF-4" in resolved.rendered_prompt
    assert "Additional guidance:\nKeep it concise." in resolved.rendered_prompt
    assert "Governed fields:" not in resolved.rendered_prompt
    assert "ZONING_DISTRICT: MF-4" not in resolved.rendered_prompt
    assert resolved.field_context["PROPERTY_ADDRESS"] == "123 Main St"
    assert "Voice reminder:" in resolved.rendered_prompt
    assert "do not invent" in resolved.rendered_prompt.lower()
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
    assert "Known site facts are unchanged" in resolved.rendered_prompt
    assert "Analyst request:\nAdd the wastewater caveat." in resolved.rendered_prompt


def test_generate_prompt_scopes_field_context_without_appending_governed_block() -> None:
    """Allowlisted facts stay on field_context; resolved prompt is template-only."""
    resolved = resolve_section_agent_prompt(
        {
            "modelPreset": "haiku",
            "sectionSystemPrompt": "System",
            "sections": {
                "zoning": {
                    "userPromptTemplate": (
                        'You are drafting the "Zoning" portion of a real estate '
                        "feasibility report."
                    ),
                    "inputFieldCodes": ["ZONING_DISTRICT", "ZONING_REGS"],
                    "guardrails": {},
                }
            },
        },
        config_version=1,
        section_id="zoning",
        field_context={
            "ZONING_DISTRICT": "MF-4",
            "ZONING_REGS": "MF-4 multifamily",
            "WATER_SERVICE": "Austin Water",
        },
        mode="generate",
    )

    assert 'You are drafting the "Zoning" portion' in resolved.rendered_prompt
    assert "Governed fields:" not in resolved.rendered_prompt
    assert "ZONING_DISTRICT: MF-4" not in resolved.rendered_prompt
    assert resolved.field_context == {
        "ZONING_DISTRICT": "MF-4",
        "ZONING_REGS": "MF-4 multifamily",
    }
    assert "WATER_SERVICE" not in resolved.field_context


def test_section_draft_field_context_filters_to_prompt_lab_inputs() -> None:
    resolved = resolve_section_agent_prompt(
        {
            "modelPreset": "haiku",
            "sectionSystemPrompt": "System",
            "sections": {
                "parcel": {
                    "userPromptTemplate": (
                        "Draft parcel language.\nParcel: {{field.PARCEL_ID}}"
                    ),
                    "inputFieldCodes": ["PARCEL_ID", "PROPERTY_ACRES"],
                    "searchContextHint": "{{field.GOVERNING_JURIS}} parcel records",
                    "guardrails": {},
                }
            },
        },
        config_version=1,
        section_id="parcel",
        field_context={
            "PARCEL_ID": "R123",
            "PROPERTY_ACRES": "10.5",
            "PROPERTY_ADDRESS": "13903 FM 812",
            "GOVERNING_JURIS": "Austin ETJ",
            "ZONING_DISTRICT": "MF-4",
            "WATER_SERVICE": "Austin Water",
            "AVAILABLE_EXHIBITS": "Site Plan",
        },
        mode="generate",
    )

    assert resolved.field_context == {
        "AVAILABLE_EXHIBITS": "Site Plan",
        "GOVERNING_JURIS": "Austin ETJ",
        "PARCEL_ID": "R123",
        "PROPERTY_ACRES": "10.5",
        "PROPERTY_ADDRESS": "13903 FM 812",
    }
    assert "ZONING_DISTRICT" not in resolved.rendered_prompt
    assert "WATER_SERVICE" not in resolved.rendered_prompt
    assert "Parcel: R123" in resolved.rendered_prompt
    assert "Governed fields:" not in resolved.rendered_prompt
    assert "PROPERTY_ADDRESS: 13903 FM 812" not in resolved.rendered_prompt
    assert resolved.field_context["PROPERTY_ADDRESS"] == "13903 FM 812"


def test_parcel_section_drops_dsi_dimensionals_even_when_prompt_lab_selected_them() -> None:
    resolved = resolve_section_agent_prompt(
        {
            "modelPreset": "haiku",
            "sectionSystemPrompt": "System",
            "sections": {
                "parcel": {
                    "userPromptTemplate": (
                        "Parcel: {{field.PROPERTY_ADDRESS}}\n"
                        "Lot: {{field.MIN_LOT_SIZE}}\n"
                        "Zoning: {{field.ZONING_REGS}}"
                    ),
                    "inputFieldCodes": [
                        "PROPERTY_ADDRESS",
                        "GOVERNING_JURIS",
                        "MIN_LOT_SIZE",
                        "SETBACKS",
                        "IMPERVIOUS_COVER_LIMIT",
                        "ZONING_REGS",
                        "ZONING_ANALYSIS_BASIS",
                    ],
                    "guardrails": {},
                }
            },
        },
        config_version=1,
        section_id="parcel",
        field_context={
            "PROPERTY_ADDRESS": "RR 2338, Georgetown, TX",
            "GOVERNING_JURIS": "Georgetown",
            "MIN_LOT_SIZE": "12,000 sq ft",
            "SETBACKS": "Front: 20 ft; Side: 10 ft; Rear: 10 ft",
            "IMPERVIOUS_COVER_LIMIT": "50%",
            "ZONING_REGS": "MF-1 — Sec. 6.02.080",
            "ZONING_ANALYSIS_BASIS": "proposed",
            "ZONING_SCENARIO_LABEL": "Rezone to MF-1",
        },
        mode="generate",
    )

    assert resolved.field_context == {
        "GOVERNING_JURIS": "Georgetown",
        "PROPERTY_ADDRESS": "RR 2338, Georgetown, TX",
    }
    assert "12,000 sq ft" not in resolved.rendered_prompt
    assert "MIN_LOT_SIZE" not in resolved.rendered_prompt
    assert "MF-1" not in resolved.rendered_prompt
    assert "Rezone to MF-1" not in resolved.rendered_prompt
    assert "RR 2338, Georgetown, TX" in resolved.rendered_prompt


def test_zoning_section_keeps_dsi_dimensionals() -> None:
    resolved = resolve_section_agent_prompt(
        {
            "modelPreset": "haiku",
            "sectionSystemPrompt": "System",
            "sections": {
                "zoning": {
                    "userPromptTemplate": (
                        "Zoning: {{field.ZONING_REGS}}\nLot: {{field.MIN_LOT_SIZE}}"
                    ),
                    "inputFieldCodes": ["ZONING_REGS", "MIN_LOT_SIZE"],
                    "guardrails": {},
                }
            },
        },
        config_version=1,
        section_id="zoning",
        field_context={
            "ZONING_REGS": "MF-1 — Sec. 6.02.080",
            "MIN_LOT_SIZE": "12,000 sq ft",
            "WATER_SERVICE": "Georgetown Utility",
        },
        mode="generate",
    )
    assert resolved.field_context == {
        "MIN_LOT_SIZE": "12,000 sq ft",
        "ZONING_REGS": "MF-1 — Sec. 6.02.080",
    }


def test_empty_input_codes_still_keeps_template_tokens_and_always_keeps() -> None:
    resolved = resolve_section_agent_prompt(
        {
            "modelPreset": "haiku",
            "sectionSystemPrompt": "System",
            "sections": {
                "parcel": {
                    "userPromptTemplate": "Acres: {{field.PROPERTY_ACRES}}",
                    "inputFieldCodes": [],
                    "guardrails": {},
                }
            },
        },
        config_version=1,
        section_id="parcel",
        field_context={
            "PROPERTY_ACRES": "10.5",
            "PROPERTY_ADDRESS": "13903 FM 812",
            "ZONING_DISTRICT": "MF-4",
        },
        mode="generate",
    )

    assert resolved.field_context == {
        "PROPERTY_ACRES": "10.5",
        "PROPERTY_ADDRESS": "13903 FM 812",
    }
    assert "ZONING_DISTRICT" not in resolved.rendered_prompt


def test_compose_scrubs_robotic_stems_from_field_values() -> None:
    prompt = compose_section_template(
        "Zoning: {{field.ZONING_REGS}}",
        field_context={"ZONING_REGS": "GR-MU-V. rule extraction pending."},
        input_field_codes=["ZONING_REGS"],
    )
    assert "GR-MU-V" in prompt
    assert "rule extraction pending" not in prompt.lower()


def test_resolve_allows_exhibit_callouts_when_listed() -> None:
    resolved = resolve_section_agent_prompt(
        {
            "modelPreset": "haiku",
            "sectionSystemPrompt": "System",
            "sections": {
                "zoning": {
                    "userPromptTemplate": "Draft zoning.",
                    "inputFieldCodes": [],
                    "guardrails": {},
                }
            },
        },
        config_version=1,
        section_id="zoning",
        field_context={"AVAILABLE_EXHIBITS": "Zoning Map; Floodplain"},
    )
    assert "AVAILABLE_EXHIBITS" in resolved.rendered_prompt
    assert "names listed in AVAILABLE_EXHIBITS" in resolved.rendered_prompt
