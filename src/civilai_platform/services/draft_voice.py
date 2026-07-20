"""Wave 3 draft-voice rules shared by Prompt Lab resolve and defaults.

Applied at prompt-resolve time so stored tenant Prompt Lab configs still get the
ACE-style rhythm/exhibit rules without a manual reseed.
"""

from __future__ import annotations

import re

# Appended to every section-draft system prompt (platform resolve + agent renderer).
DRAFT_VOICE_DIRECTIVE = """
Draft voice (ACE house style — always apply):
- Write short paragraphs: typically 1–3 sentences each. Prefer blank-line breaks between paragraphs in markdown.
- One topic per subsection or paragraph cluster; do not dump every field into a single wall of text.
- Paraphrase governed field values into professional engineering prose. Never paste multi-topic Compose/field dumps verbatim.
- Do not invent "(See Exhibit: …)" callouts. Only cite an exhibit when AVAILABLE_EXHIBITS (or an equivalent project exhibit list) names that sheet/map, or when a governed citation clearly identifies it.
- Never invent permits, capacities, will-serve commitments, or unstated regulatory conclusions.
- Replace robotic stems such as "rule extraction pending" or "Pending user input." with an honest verification gap (what is unknown and who to confirm with).
""".strip()

_ROBOTIC_STEMS = (
    re.compile(r"(?i)\brule extraction pending\.?"),
    re.compile(r"(?i)\bpending user input\.?"),
    re.compile(r"(?i)\bnot available from current project data\.?"),
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")

# Long Compose blobs: keep content but ask the model to paraphrase (prompt-side hygiene).
_LONG_FIELD_CHARS = 280


def apply_draft_voice_to_system_prompt(system_prompt: str) -> str:
    """Ensure DRAFT_VOICE_DIRECTIVE is present exactly once on a system prompt."""
    base = (system_prompt or "").strip()
    marker = "Draft voice (ACE house style"
    if marker in base:
        return base
    if not base:
        return DRAFT_VOICE_DIRECTIVE
    return f"{base}\n\n{DRAFT_VOICE_DIRECTIVE}"


def scrub_robotic_stems(text: str) -> str:
    """Remove known robotic Compose/placeholder stems from draft or field text."""
    cleaned = text or ""
    for pattern in _ROBOTIC_STEMS:
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+\.", ".", cleaned)
    cleaned = re.sub(r"\.\.+", ".", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(" \t,;:")


def sanitize_field_value_for_draft(value: str) -> str:
    """Scrub robotic stems; leave long values intact (model paraphrases under voice rules)."""
    cleaned = scrub_robotic_stems(value)
    if not cleaned:
        return ""
    return cleaned


def draft_voice_user_reminder(*, has_exhibits: bool) -> str:
    """Short user-prompt reminder so pipeline format_directive paths also see the rules."""
    if has_exhibits:
        return (
            "Voice reminder: short paragraphs; paraphrase fields; cite (See Exhibit: …) only "
            "for names listed in AVAILABLE_EXHIBITS."
        )
    return (
        "Voice reminder: short paragraphs; paraphrase fields; do not invent "
        "(See Exhibit: …) callouts — no exhibits are listed for this project."
    )


def split_compose_dump_into_paragraphs(text: str, *, max_sentences: int = 2) -> str:
    """Optional pre-body split: turn a mega Compose dump into blank-line paragraphs."""
    stripped = scrub_robotic_stems(text)
    if len(stripped) < _LONG_FIELD_CHARS:
        return stripped
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(stripped) if s.strip()]
    if len(sentences) < 3:
        return stripped
    paras: list[str] = []
    for index in range(0, len(sentences), max_sentences):
        paras.append(" ".join(sentences[index : index + max_sentences]))
    return "\n\n".join(paras)
