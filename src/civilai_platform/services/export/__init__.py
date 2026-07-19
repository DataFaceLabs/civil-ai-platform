"""Server-side feasibility-study export (M1 / X1).

The platform owns a versioned *content contract* (`contract.py`); each tenant selects
a presentation *skin* (`skins.py`) — a Word `.docx` whose jinja slots the contract fills.
This inverts today's browser export (LLM-invented HTML → lossy html-to-docx/html2pdf):
governed facts fill deterministic slots, editor narration fills prose slots, and a real
Word document is rendered server-side (see `EXPORT-REDESIGN-PLAN.md` +
`CIVIL1-STUDY-FORMAT.md`).
"""
