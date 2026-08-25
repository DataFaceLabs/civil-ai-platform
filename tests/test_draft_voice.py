"""Draft-voice helpers (scrubbers; system prompt is pass-through)."""

from civilai_platform.services.draft_voice import (
    DRAFT_VOICE_DIRECTIVE,
    apply_draft_voice_to_system_prompt,
    rewrite_unknown_fact_prose,
    sanitize_field_value_for_draft,
    scrub_robotic_stems,
    split_compose_dump_into_paragraphs,
)


def test_apply_draft_voice_is_pass_through() -> None:
    lab = (
        "You're an expert civil engineer. Format sections using h2 and h3 headings."
    )
    assert apply_draft_voice_to_system_prompt(lab) == lab
    assert apply_draft_voice_to_system_prompt(f"  {lab}  ") == lab
    assert apply_draft_voice_to_system_prompt("") == ""
    assert "Draft voice (ACE house style" not in apply_draft_voice_to_system_prompt(lab)
    # Historical constant retained but not injected.
    assert DRAFT_VOICE_DIRECTIVE.startswith("Draft voice")


def test_rewrite_unknown_fact_prose_keeps_the_sentence() -> None:
    source = (
        "Critical Water Quality Zone designation are not provided in the available "
        "field data and should be confirmed"
    )
    assert rewrite_unknown_fact_prose(source) == (
        "Critical Water Quality Zone designation not currently known and should be confirmed"
    )


def test_scrub_robotic_stems() -> None:
    assert scrub_robotic_stems("Zoning is GR. rule extraction pending.") == "Zoning is GR."
    assert scrub_robotic_stems("Pending user input.") == ""
    assert (
        scrub_robotic_stems(
            "Critical Water Quality Zone designation are not provided in the "
            "available field data and should be confirmed"
        )
        == "Critical Water Quality Zone designation not currently known and should be confirmed"
    )


def test_sanitize_field_drops_robotic_only_values() -> None:
    assert sanitize_field_value_for_draft("rule extraction pending") == ""
    assert "GR-MU" in sanitize_field_value_for_draft("District GR-MU. Pending user input.")


def test_split_compose_dump_into_paragraphs() -> None:
    blob = " ".join(
        f"This is sentence number {i} about zoning overlays and site access."
        for i in range(1, 8)
    )
    split = split_compose_dump_into_paragraphs(blob)
    assert "\n\n" in split
    assert len(split.split("\n\n")) >= 3
