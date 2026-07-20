"""Wave 3 draft-voice helpers."""

from civilai_platform.services.draft_voice import (
    DRAFT_VOICE_DIRECTIVE,
    apply_draft_voice_to_system_prompt,
    draft_voice_user_reminder,
    sanitize_field_value_for_draft,
    scrub_robotic_stems,
    split_compose_dump_into_paragraphs,
)


def test_apply_draft_voice_appends_once() -> None:
    once = apply_draft_voice_to_system_prompt("Write carefully.")
    assert once.startswith("Write carefully.")
    assert "Draft voice (ACE house style" in once
    twice = apply_draft_voice_to_system_prompt(once)
    assert twice.count("Draft voice (ACE house style") == 1


def test_scrub_robotic_stems() -> None:
    assert scrub_robotic_stems("Zoning is GR. rule extraction pending.") == "Zoning is GR."
    assert scrub_robotic_stems("Pending user input.") == ""


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
