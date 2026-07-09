from civilai_platform.model_presets import MODEL_PRESET_IDS, resolve_model_id


def test_resolve_model_id_openai_gpt55() -> None:
    assert resolve_model_id("gpt55") == "gpt-5.5"
    assert resolve_model_id("gpt4omini") == "gpt-4o-mini"


def test_resolve_model_id_bedrock() -> None:
    assert resolve_model_id("haiku") == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert resolve_model_id("sonnet46") == "us.anthropic.claude-sonnet-4-6"
    assert resolve_model_id("opus") == "us.anthropic.claude-opus-4-6-20260201-v1:0"


def test_resolve_model_id_unknown_falls_back_to_haiku() -> None:
    assert resolve_model_id("not-a-real-preset") == MODEL_PRESET_IDS["haiku"]


def test_model_preset_catalog_matches_fe_openai_keys() -> None:
    expected_openai = {
        "gpt55",
        "gpt55pro",
        "gpt54",
        "gpt54mini",
        "gpt54nano",
        "gpt5",
        "gpt5mini",
        "gpt5nano",
        "gpt41",
        "gpt41mini",
        "gpt41nano",
        "gpt4o",
        "gpt4omini",
        "o1",
        "o1mini",
        "o1pro",
        "o3",
        "o3mini",
        "o4mini",
    }
    assert expected_openai.issubset(MODEL_PRESET_IDS.keys())
