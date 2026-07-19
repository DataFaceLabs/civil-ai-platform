"""Render an ExportContext through a Word-native docxtpl skin."""

from __future__ import annotations

import base64
import binascii
import re
from io import BytesIO
from typing import Any

import docx
from docx.shared import Inches
from docxcompose.composer import Composer  # type: ignore[import-untyped]
from docxtpl import DocxTemplate, InlineImage  # type: ignore[import-untyped]

from civilai_platform.models.entities import MapExhibit
from civilai_platform.services import artifacts as artifact_svc
from civilai_platform.services.export.context import ExportContext
from civilai_platform.services.export.skins import Skin

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _narration_subdoc(template: DocxTemplate, text: str) -> Any:
    """Convert the editor's paragraph/bold subset into real Word paragraphs."""
    subdoc = template.new_subdoc()
    for chunk in re.split(r"\n\s*\n", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        paragraph = subdoc.add_paragraph()
        pos = 0
        for match in _BOLD_RE.finditer(chunk):
            if match.start() > pos:
                paragraph.add_run(chunk[pos : match.start()])
            paragraph.add_run(match.group(1)).bold = True
            pos = match.end()
        if pos < len(chunk):
            paragraph.add_run(chunk[pos:])
    return subdoc


def _thumbnail_bytes(data_url: str | None) -> bytes | None:
    if not data_url or not data_url.startswith("data:image/") or "," not in data_url:
        return None
    header, encoded = data_url.split(",", 1)
    try:
        return base64.b64decode(encoded) if ";base64" in header else encoded.encode()
    except (ValueError, binascii.Error):
        return None


def _exhibit_image(exhibit: MapExhibit) -> bytes | None:
    mime_type = (exhibit.mime_type or "").lower()
    if exhibit.s3_key and (mime_type.startswith("image/") or not mime_type):
        payload = artifact_svc.download_artifact_bytes(exhibit.s3_key)
        if payload:
            return payload
    # PDF previews are generated client-side and persisted specifically so the report
    # can show the uploaded sheet before server-side PDF rasterization lands in X2.
    return _thumbnail_bytes(exhibit.thumbnail_data_url)


def _append_byo_exhibits(rendered: bytes, exhibits: tuple[MapExhibit, ...]) -> bytes:
    if not exhibits:
        return rendered

    master = docx.Document(BytesIO(rendered))
    composer = Composer(master)
    for index, exhibit in enumerate(exhibits, start=1):
        sheet = docx.Document()
        sheet.add_heading(f"EXHIBIT {index} - {exhibit.label or exhibit.name}", level=1)
        image = _exhibit_image(exhibit)
        if image:
            try:
                sheet.add_picture(BytesIO(image), width=Inches(7.0))
            except (ValueError, OSError):
                sheet.add_paragraph(
                    "The uploaded exhibit could not be embedded; use the original project upload."
                )
        else:
            sheet.add_paragraph(
                "The uploaded exhibit is retained with the project but has no embeddable preview."
            )
        composer.append(sheet)

    output = BytesIO()
    composer.save(output)
    return output.getvalue()


def _customer_logo(template: DocxTemplate, payload: bytes | None) -> Any:
    """A cover InlineImage from the tenant's uploaded logo, height-constrained for an
    elegant lockup. Returns "" when absent or unreadable so the `{{ customer_logo }}`
    token renders empty (the firm name below carries the brand) instead of leaking."""
    if not payload:
        return ""
    try:
        return InlineImage(template, BytesIO(payload), height=Inches(0.8))
    except (ValueError, OSError):
        return ""


def _cover_aerial(template: DocxTemplate, exhibits: tuple[MapExhibit, ...]) -> Any:
    """The cover site image (ACE corpus: every delivered study leads with the parcel
    aerial). Prefers an exhibit labeled like an aerial/vicinity map, falls back to the
    first embeddable exhibit, and renders blank when the project has none."""
    def _score(exhibit: MapExhibit) -> int:
        label = f"{exhibit.label or ''} {exhibit.name}".lower()
        return 0 if ("aerial" in label or "vicinity" in label) else 1

    for exhibit in sorted(exhibits, key=_score):
        image = _exhibit_image(exhibit)
        if image:
            try:
                # Sized so the full ACE cover block (title, preparer, aerial, client
                # contact) still fits one page -- 5.8" pushed contact lines to page 2.
                return InlineImage(template, BytesIO(image), width=Inches(5.0))
            except (ValueError, OSError):
                continue
    return ""


def render_docx(context: ExportContext, skin: Skin) -> bytes:
    if not skin.template_path.exists():
        raise FileNotFoundError(f"export skin template not found: {skin.template_path}")

    template = DocxTemplate(str(skin.template_path))
    render_values: dict[str, Any] = dict(context.template_values)
    render_values["customer_logo"] = _customer_logo(template, context.customer_logo)
    render_values["cover_aerial"] = _cover_aerial(template, context.exhibits)
    for token in skin.narration_tokens:
        text = context.narration.get(token) or "Not available from current project data."
        render_values[token] = _narration_subdoc(template, text)

    # StrictUndefined would turn optional, intentionally unfilled tenant fields into
    # failures. Instead, ensure every declared template variable has an honest value so
    # raw jinja never leaks into a customer document.
    for variable in template.get_undeclared_template_variables():
        render_values.setdefault(variable, "Not available from current project data.")

    template.render(render_values)
    output = BytesIO()
    template.save(output)
    return _append_byo_exhibits(output.getvalue(), context.exhibits)
