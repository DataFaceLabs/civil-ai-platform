# Agent Feedback Capture (the tuning data flywheel)

**Status:** Phase 1 in progress (2026-07). Owner: platform.

## Why

Every section a customer works on is a chain of signal: the agent drafts it, the SME
accepts / edits / rewrites, walks away, regenerates, edits again, approves, reopens weeks
later and tweaks. That whole **trajectory** is the ground truth for tuning the agent —
not just the first draft and the final text. We capture it as an append-only event stream
so it can later fuel supervised fine-tuning (SFT), preference data (edit ≻ draft), and
evals. Production usage → labeled data → a better agent: the flywheel.

## Storage

- **Bucket:** `civilai-agent-corpus-{env}` (dedicated, versioned, SSE, block-public,
  **no lifecycle expiry** — a corpus is write-once and permanent). *Not* the app bucket,
  whose `tenant/` prefix expires objects at 90 days.
- **Lambda** has `s3:PutObject` only (never read/delete — that's the Phase 2 builder).
  `CIVILAI_AGENT_CORPUS_BUCKET` empty ⇒ capture is a no-op (safe default).

## Layout — append-only event stream per (tenant, project, section)

```
tenant/{tenant_id}/project/{project_id}/section/{section_id}/
    {epoch_millis:013d}__{event_type}__{event_id}.json
```

One immutable object per event. The zero-padded epoch-millis prefix makes a prefix listing
return events in chronological order. The full lifecycle of a section = everything under
its prefix, across breaks and days.

## Events (milestones, not keystrokes)

| event_type | emitted when | payload highlights |
|---|---|---|
| `draft` | an agent run completes for a section (incl. regenerations) | `run_id`, `input_context` (redacted field_context + proposed_use + request), `agent_output` (text + trace_summary), `model` |
| `edit` | SME saves a changed section body (status still draft/in_review) | `text` (new body), `prev_status` |
| `approve` | section status → `approved` | `text`, `prev_status` |
| `reopen` | section status leaves `approved` | `text`, `prev_status` |

No-op saves (body + status unchanged) are skipped. Capture is best-effort and **never
blocks or fails the request** — all errors are swallowed and logged.

## Record schema (v1)

```jsonc
{
  "schema_version": 1,
  "event_id": "<uuid>",
  "event_type": "draft|edit|approve|reopen",
  "captured_at": "<ISO-8601 UTC>",
  "tenant_id": "...", "project_id": "...", "section_id": "...",
  "entity_id": "<parcel uuid|null>",
  "actor_user_id": "<cognito sub>",

  // draft only:
  "run_id": "...",
  "model": { "preset": "...", "model_id": "..." },
  "input_context": {
    "field_context": { "...": "..." },   // the data pulled — PII-redacted (owner_name -> [redacted])
    "proposed_use": "...",
    "request": "..."
  },
  "agent_output": { "text": "...", "trace_summary": { } },

  // edit/approve/reopen only:
  "text": "...",            // section body at this event
  "prev_status": "..."
}
```

## PII

Only `owner_name` is `sensitivity: pii` in the data catalog (the site address and parcel
id are public). The agent already receives field_context redacted (the data proxy defaults
`include_pii=False`, so PII arrives as `[redacted]`). The corpus writer **re-redacts
defensively** against a PII key set before writing — belt-and-suspenders so a future
`include_pii=True` path can never leak a real name into the *permanent* corpus. The
authoritative PII set stays the data catalog's `sensitivity: pii`; the platform mirror is
overridable via `CIVILAI_CORPUS_PII_KEYS`.

---

## Phase 2 — dataset builder (documented, not this week)

A batch job (off the request path) reads the S3 event stream and emits training/eval
datasets:
- **SFT:** for each section, `(input_context of the draft it derived from) → (final approved text)` pairs.
- **Preference (DPO):** within a section's chain, `later_text ≻ earlier_text` and `edited ≻ draft`.
- **Eval set:** held-out `(input_context → SME-approved text)` to grade prompt/model changes.
- Joins events by walking the per-section stream in timestamp order; a `draft` followed by
  `edit`s and an `approve` forms one trajectory.
- Output to a versioned dataset prefix (`datasets/{version}/...`) — reproducible, never
  mutates the raw event stream.

## Phase 3 — retune flywheel (documented, not this week)

- Scheduled: rebuild datasets, run the eval harness (grades agent output vs SME-approved
  ground truth, anchored on the corpus + the 20 client reports), and gate prompt/model
  changes on it.
- Over time: more usage → more edits → better data → fewer edits. Track "SME edit rate per
  section" as the north-star metric.
- Governance gate before any cross-tenant training: data-use agreement + tenant opt-in.
