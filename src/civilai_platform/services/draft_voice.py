"""Draft-voice helpers: scrub robotic Compose stems and unknown-fact leaks.

Style and formatting for section drafts live in LLM Lab ``sectionSystemPrompt``
(the Section draft system prompt). This module no longer injects ACE draft-voice
or user-prompt voice reminders at resolve time.
"""

from __future__ import annotations

import re

# Retained for tests / callers that still import the historical constant; not
# appended to system prompts anymore.
DRAFT_VOICE_DIRECTIVE = """
Draft voice (ACE house style - always apply):
- Write short paragraphs: typically 1-3 sentences each. Prefer blank-line
  breaks between paragraphs in markdown.
- One topic per subsection or paragraph cluster; do not dump every field into
  a single wall of text.
- Paraphrase known site facts into professional engineering prose. Never paste
  multi-topic Compose dumps verbatim.
- Do not invent "(See Exhibit: ...)" callouts. Only cite an exhibit when
  AVAILABLE_EXHIBITS (or an equivalent project exhibit list) names that
  sheet/map, or when a governed citation clearly identifies it.
- When flood facts include a FIRM ``panel_id``, cite that panel id (and
  effective date when present) in Environmental floodplain prose.
- Never paste the project site address into agency / Development Services
  contact sentences — contacts are agency name and phone only.
- Never invent permits, capacities, will-serve commitments, or unstated
  regulatory conclusions.
- Exclude robotic stems such as "rule extraction pending" or "Pending user input."
- In drafted study and chat prose, never mention field data, available data,
  governed fields, or project data.
- When a fact is unknown, write that it is not currently known and should be
  confirmed.
""".strip()

UNKNOWN_FACT_DIRECTIVE = """
Unknown facts (always apply):
- In drafted study and chat prose, never mention field data, available data,
  governed fields, or project data.
- When a fact is unknown, write that it is not currently known and should
  be confirmed.
""".strip()

_UNKNOWN_FACT_REPLACEMENT = "not currently known"

_UNKNOWN_FACT_PATTERNS = (
    re.compile(
        r"\b(?:are|is|were|was)\s+not\s+provided\s+in\s+the\s+available\s+field\s+data\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bnot\s+provided\s+in\s+the\s+available\s+field\s+data\b", re.IGNORECASE),
    re.compile(
        r"\b(?:are|is|were|was)\s+not\s+(?:present\s+)?in\s+the\s+available\s+field\s+data\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bnot\s+(?:present\s+)?in\s+the\s+available\s+field\s+data\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:are|is|were|was)\s+not\s+present\s+in\s+(?:the\s+)?field\s+data\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bnot\s+present\s+in\s+(?:the\s+)?field\s+data\b", re.IGNORECASE),
    re.compile(r"\bnot\s+available\s+from\s+current\s+project\s+data\b", re.IGNORECASE),
)

_ROBOTIC_STEMS = (
    re.compile(r"(?i)\brule extraction pending\.?"),
    re.compile(r"(?i)\bpending user input\.?"),
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")

# Long Compose blobs: keep content but ask the model to paraphrase (prompt-side hygiene).
_LONG_FIELD_CHARS = 280


def apply_draft_voice_to_system_prompt(system_prompt: str) -> str:
    """Pass through the LLM Lab system prompt unchanged.

    Deprecated: previously appended ACE ``DRAFT_VOICE_DIRECTIVE``. Style rules
    now live only in ``sectionSystemPrompt``.
    """
    return (system_prompt or "").strip()


def rewrite_unknown_fact_prose(text: str) -> str:
    """Rewrite leaked 'available field data' phrasing; keep the surrounding sentence."""
    cleaned = text or ""
    for pattern in _UNKNOWN_FACT_PATTERNS:
        cleaned = pattern.sub(_UNKNOWN_FACT_REPLACEMENT, cleaned)
    return re.sub(r"[ \t]{2,}", " ", cleaned)


def scrub_robotic_stems(text: str) -> str:
    """Remove known robotic Compose/placeholder stems from draft or field text."""
    cleaned = rewrite_unknown_fact_prose(text or "")
    for pattern in _ROBOTIC_STEMS:
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+\.", ".", cleaned)
    cleaned = re.sub(r"\.\.+", ".", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(" \t,;:")


def sanitize_field_value_for_draft(value: str) -> str:
    """Scrub robotic stems; leave long values intact (model paraphrases under Lab rules)."""
    cleaned = scrub_robotic_stems(value)
    if not cleaned:
        return ""
    return cleaned


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
