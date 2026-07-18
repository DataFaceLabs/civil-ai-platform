"""One-time conversion: the firm's ACE feasibility template -> a docxtpl asset.

E1 spike (2026-07-15): the ACE template (`client-data/ATXCivil_Feasibility_Template.docx`)
is a slot-substitution skeleton whose `{TOKEN}` placeholders are Word-native curly-brace
text, not jinja tags. This script rewrites every `{TOKEN}` run in-place to docxtpl's
`{{ token }}` syntax (lowercased, valid Python identifier) so `DocxTemplate.render()` can
fill it, while leaving every other run (fonts, bold, headings, numbering) untouched.

Verified 2026-07-15 against the source template: every `{TOKEN}` sits intact within a
single python-docx run (no run-splitting across a token) -- confirmed by comparing tokens
found in each paragraph's full text against tokens found in its runs' concatenated text,
zero mismatches across all 107 paragraphs + the one table. docxtpl's usual run-splitting
gotcha (a tag broken across runs by Word's spell-check/autocorrect re-flowing) does not
apply here, so a straightforward per-run regex substitution is safe. If a future edit to
the source template (e.g. someone retypes a token in Word) reintroduces run-splitting,
this script's verification step will start reporting unconverted `{TOKEN}` residue and it
needs the docxtpl "fix broken tags" recipe (re-type the tag in Word to normalize runs, or
merge the run text before substituting).

Tokens are converted 1:1 (`{PROPERTY_ADDRESS}` -> `{{ property_address }}`) except the
five image/table slots noted in NOT_CONVERTED below, which need dedicated handling (jinja
loops / InlineImage) in a later pass -- not a run-level text substitution.

Usage::

    uv run python scripts/docxtpl_convert_template.py
"""

from __future__ import annotations

import re
from pathlib import Path

import docx

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_TEMPLATE = (
    REPO_ROOT.parent / "client-data" / "ATXCivil_Feasibility_Template.docx"
)
OUTPUT_TEMPLATE = REPO_ROOT / "assets" / "templates" / "atxcivil_v1.docx"

_TOKEN_RE = re.compile(r"\{([A-Z_0-9]+)\}")

# {TOKEN} instances not handled by the 1:1 substitution below:
# - "![LOGO/IMAGE]" is a placeholder for a real InlineImage, not a {TOKEN}.
# - The identification table (TRACT/PARCEL ID/ADDRESS/DEED DOC. NO./ACRES) has no
#   tokens in its data row today -- it's populated by hand in every delivered study
#   seen in the corpus. Wiring it needs a jinja loop over tract rows, deferred to E2.

# Tokens the render script feeds a docxtpl Subdoc (real multi-paragraph narration,
# not a plain string) -- these need docxtpl's paragraph-tag syntax `{{p token }}`,
# not the inline `{{ token }}` used for every other token. A Subdoc silently
# renders as nothing under an inline tag (verified against the E1 spike output --
# every subdoc-fed section rendered as a blank paragraph until this was fixed).
# Each of these already sits alone in its own paragraph in the source template
# (verified below at conversion time), which paragraph tags require.
SUBDOC_TOKENS = frozenset(
    {
        "ZONING_REGS",
        "WATER_SERVICE",
        "WASTEWATER_SERVICE",
        "ELECTRIC_PROVIDER",
        "FIRE_PROTECTION",
        "FLOODPLAIN_STATUS",
    }
)


def _jinja_name(token: str) -> str:
    return token.lower()


def convert(source: Path, dest: Path) -> tuple[int, list[str]]:
    """Rewrite every `{TOKEN}` run to `{{ jinja_name }}` (or `{{p jinja_name }}`
    for SUBDOC_TOKENS that sit alone in their own paragraph).

    Returns the number of tokens converted and any `{TOKEN}`-shaped text left over
    after conversion (should be empty -- a non-empty list means a token survived
    outside a single run, i.e. the run-splitting gotcha this repo's template does
    not currently have).
    """
    document = docx.Document(str(source))
    converted = 0

    def _convert_runs(paragraph: docx.text.paragraph.Paragraph) -> None:
        nonlocal converted
        alone = _TOKEN_RE.fullmatch(paragraph.text.strip())
        use_paragraph_tag = bool(alone) and alone.group(1) in SUBDOC_TOKENS
        for run in paragraph.runs:
            if "{" not in run.text:
                continue

            def _sub(m: re.Match[str]) -> str:
                name = _jinja_name(m.group(1))
                return "{{p " + name + " }}" if use_paragraph_tag else "{{ " + name + " }}"

            new_text, n = _TOKEN_RE.subn(_sub, run.text)
            if n:
                run.text = new_text
                converted += n

    for paragraph in document.paragraphs:
        _convert_runs(paragraph)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _convert_runs(paragraph)

    dest.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(dest))

    # Verification pass: re-open the saved file and confirm no {TOKEN} text remains
    # (the image placeholder is expected residue, everything else is not).
    saved = docx.Document(str(dest))
    residue = []
    for paragraph in saved.paragraphs:
        for match in _TOKEN_RE.finditer(paragraph.text):
            if match.group(0) != "{LOGO/IMAGE}":
                residue.append(match.group(0))
    return converted, residue


def main() -> int:
    if not SOURCE_TEMPLATE.exists():
        raise SystemExit(f"Source template not found: {SOURCE_TEMPLATE}")
    converted, residue = convert(SOURCE_TEMPLATE, OUTPUT_TEMPLATE)
    print(f"Converted {converted} token(s) -> {OUTPUT_TEMPLATE}")
    if residue:
        print(f"WARNING: {len(residue)} unconverted token(s) remain: {sorted(set(residue))}")
        return 1
    print("Verification passed: no unconverted {TOKEN} residue.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
