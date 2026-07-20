"""Post-render DOCX polish for export skins (Civil1 / ATX presentation defects).

Strips placeholder-only paragraphs, mid-sentence missing sentinels, and empty
recommendation/exhibit table rows that otherwise become walls of
"Not available..." in DOCX/PDF. Headings are kept so the per-skin outline linter
still matches.
"""

from __future__ import annotations

import re
from io import BytesIO

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from civilai_platform.services.export.context import _MISSING, _PENDING_PLACEHOLDER

_MISSING_TEXT = _MISSING
_PENDING_TEXT = _PENDING_PLACEHOLDER
_PLACEHOLDER_RE = re.compile(
    re.escape(_MISSING_TEXT) + "|" + re.escape(_PENDING_TEXT),
    re.IGNORECASE,
)


def _paragraph_text(paragraph: Paragraph) -> str:
    return "".join(run.text for run in paragraph.runs).strip()


def _style_name(paragraph: Paragraph) -> str:
    style = paragraph.style
    return (style.name if style is not None else "") or ""


def _is_heading(paragraph: Paragraph) -> bool:
    return _style_name(paragraph).lower().startswith("heading")


def _is_missing_only(text: str) -> bool:
    cleaned = text.strip()
    return cleaned == _MISSING_TEXT or cleaned.casefold() == _PENDING_TEXT.casefold()


def _scrub_placeholders(text: str) -> str:
    """Remove missing/pending sentinels and tidy leftover punctuation."""
    cleaned = _PLACEHOLDER_RE.sub("", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+\.", ".", cleaned)
    cleaned = re.sub(r"\.\.+", ".", cleaned)
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = re.sub(r",\s*,", ",", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" \t,;:")


def _set_paragraph_text(paragraph: Paragraph, text: str) -> None:
    if not paragraph.runs:
        paragraph.add_run(text)
        return
    paragraph.runs[0].text = text
    for run in paragraph.runs[1:]:
        run.text = ""


def _remove_paragraph(paragraph: Paragraph) -> None:
    element = paragraph._element
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def _remove_table_row(table: Table, row_index: int) -> None:
    row = table.rows[row_index]._tr
    row.getparent().remove(row)


def polish_export_docx(payload: bytes) -> bytes:
    """Remove presentation-only emptiness from a rendered export DOCX."""
    document = docx.Document(BytesIO(payload))

    # 1) Drop table rows whose value cell is empty or the missing sentinel.
    for table in list(document.tables):
        for row_index in range(len(table.rows) - 1, -1, -1):
            cells = table.rows[row_index].cells
            if len(cells) < 2:
                continue
            value = cells[-1].text.strip()
            scrubbed = _scrub_placeholders(value)
            if not scrubbed or _is_missing_only(value):
                _remove_table_row(table, row_index)
            elif scrubbed != value:
                cells[-1].text = scrubbed

    # 2) Scrub mid-sentence placeholders; drop paragraphs that are only sentinel.
    for paragraph in list(document.paragraphs):
        if _is_heading(paragraph):
            continue
        text = _paragraph_text(paragraph)
        if not text:
            continue
        if _is_missing_only(text):
            _remove_paragraph(paragraph)
            continue
        scrubbed = _scrub_placeholders(text)
        if not scrubbed:
            _remove_paragraph(paragraph)
        elif scrubbed != text:
            _set_paragraph_text(paragraph, scrubbed)

    # 3) Collapse runs of blank paragraphs (keep at most one spacer).
    previous_blank = False
    for paragraph in list(document.paragraphs):
        text = _paragraph_text(paragraph)
        if _is_heading(paragraph):
            previous_blank = False
            continue
        if text:
            previous_blank = False
            continue
        if previous_blank:
            _remove_paragraph(paragraph)
        else:
            previous_blank = True

    output = BytesIO()
    document.save(output)
    return output.getvalue()
