"""Post-render DOCX polish for export skins (Civil1 presentation defects).

Strips placeholder-only paragraphs and empty recommendation/exhibit table rows that
otherwise become walls of "Not available..." in DOCX/PDF. Headings are kept so the
per-skin outline linter still matches.
"""

from __future__ import annotations

from io import BytesIO

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from civilai_platform.services.export.context import _MISSING

_MISSING_TEXT = _MISSING


def _paragraph_text(paragraph: Paragraph) -> str:
    return "".join(run.text for run in paragraph.runs).strip()


def _style_name(paragraph: Paragraph) -> str:
    style = paragraph.style
    return (style.name if style is not None else "") or ""


def _is_heading(paragraph: Paragraph) -> bool:
    return _style_name(paragraph).lower().startswith("heading")


def _is_missing_only(text: str) -> bool:
    return text == _MISSING_TEXT


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
            if not value or _is_missing_only(value):
                _remove_table_row(table, row_index)

    # 2) Drop paragraphs that are only the missing sentinel.
    for paragraph in list(document.paragraphs):
        text = _paragraph_text(paragraph)
        if _is_missing_only(text):
            _remove_paragraph(paragraph)

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
