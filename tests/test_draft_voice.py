"""Wave 3 draft-voice helpers."""

import re

from civilai_platform.services.draft_voice import (
    DRAFT_VOICE_DIRECTIVE,
    UNKNOWN_FACT_DIRECTIVE,
    apply_draft_voice_to_system_prompt,
    draft_voice_user_reminder,
    rewrite_unknown_fact_prose,
    sanitize_field_value_for_draft,
    scrub_robotic_stems,
    split_compose_dump_into_paragraphs,
)


def test_apply_draft_voice_appends_once() -> None:
    once = apply_draft_voice_to_system_prompt("Write carefully.")
    assert once.startswith("Write carefully.")
    assert "Draft voice (ACE house style" in once
    assert "not currently known and should be confirmed" in re.sub(r"\s+", " ", once)
    assert once.count("Unknown facts (always apply)") == 0
    twice = apply_draft_voice_to_system_prompt(once)
    assert twice.count("Draft voice (ACE house style") == 1
    assert twice.count("Unknown facts (always apply)") == 0


def test_apply_draft_voice_adds_unknown_fact_rule_to_stale_voice_block() -> None:
    stale = (
        "Write carefully.\n\nDraft voice (ACE house style - always apply):\n"
        "- Write short paragraphs."
    )
    updated = apply_draft_voice_to_system_prompt(stale)
    assert UNKNOWN_FACT_DIRECTIVE in updated
    assert updated.count("Draft voice (ACE house style") == 1


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


def test_voice_reminder_depends_on_exhibits() -> None:
    assert "do not invent" in draft_voice_user_reminder(has_exhibits=False).lower()
    assert "AVAILABLE_EXHIBITS" in draft_voice_user_reminder(has_exhibits=True)
    assert DRAFT_VOICE_DIRECTIVE
