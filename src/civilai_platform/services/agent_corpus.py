"""Agent feedback capture — append-only event stream to the training corpus.

Every meaningful milestone in a section's life (agent draft/regenerate, SME edit,
approve, reopen) is written as one immutable S3 object under

    tenant/{tenant}/project/{project}/section/{section}/{millis:013d}__{type}__{id}.json

so a prefix listing replays the whole trajectory in order. This is deterministic
plumbing, NOT an agent tool: it observes what happened and records it. Capture is
best-effort -- it must never block or fail the user action, so every path swallows and
logs its own errors.

See docs/design/agent-feedback-capture.md.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from functools import lru_cache
from typing import Any

import boto3

from civilai_platform.models.entities import Section, utc_now
from civilai_platform.settings import get_settings

logger = logging.getLogger(__name__)

_REDACTED = "[redacted]"


@lru_cache
def _s3_client():
    settings = get_settings()
    session = boto3.Session(profile_name=settings.aws_profile, region_name=settings.aws_region)
    return session.client("s3")


@lru_cache
def _pii_keys() -> frozenset[str]:
    """PII field keys to redact defensively (lowercased, incl. bare + dotted forms).

    Authoritative source is the data catalog's ``sensitivity: pii`` set; this mirror is a
    belt-and-suspenders net because field_context already arrives redacted from the data
    proxy (``include_pii=False``). Overridable via ``CIVILAI_CORPUS_PII_KEYS``.
    """
    raw = (get_settings().corpus_pii_keys or "").strip()
    keys = {k.strip().lower() for k in raw.split(",") if k.strip()}
    return frozenset(keys)


def _redact_field_context(field_context: dict[str, str]) -> dict[str, str]:
    pii = _pii_keys()
    out: dict[str, str] = {}
    for key, value in field_context.items():
        bare = key.split(".")[-1].lower()
        out[key] = _REDACTED if (key.lower() in pii or bare in pii) else value
    return out


def _section_key(tenant_id: str, project_id: str, section_id: str) -> str:
    return f"tenant/{tenant_id}/project/{project_id}/section/{section_id}"


def _put_event(record: dict[str, Any]) -> None:
    """Write one event object. Best-effort: never raises into the caller."""
    settings = get_settings()
    bucket = settings.agent_corpus_bucket
    if not bucket:  # capture disabled (e.g. local/dev, or bucket not provisioned)
        return
    try:
        millis = int(time.time() * 1000)
        key = (
            f"{_section_key(record['tenant_id'], record['project_id'], record['section_id'])}"
            f"/{millis:013d}__{record['event_type']}__{record['event_id']}.json"
        )
        _s3_client().put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(record, default=str).encode("utf-8"),
            ContentType="application/json",
        )
    except Exception:  # noqa: BLE001 -- capture must never break the request path
        logger.warning("agent-corpus capture failed (non-fatal)", exc_info=True)


def _base_event(
    *,
    event_type: str,
    tenant_id: str,
    project_id: str,
    section_id: str,
    entity_id: str | None,
    actor_user_id: str,
    actor_role: str | None,
) -> dict[str, Any]:
    # actor_user_id is on EVERY event, so a multi-user project is captured natively: each
    # milestone records exactly who did it, in order. actor_role is the actor's tenant role
    # at event time (analyst/admin/reviewer) -- useful signal for weighting edits (a senior
    # reviewer's rewrite is stronger than a junior draft-accept). Stored as the stable
    # Cognito sub, never email/name -- the dataset builder joins the profile if it needs those.
    return {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "captured_at": utc_now(),
        "tenant_id": tenant_id,
        "project_id": project_id,
        "section_id": section_id,
        "entity_id": entity_id,
        "actor_user_id": actor_user_id,
        "actor_role": actor_role,
    }


def capture_draft(
    *,
    tenant_id: str,
    project_id: str,
    section_id: str | None,
    entity_id: str | None,
    actor_user_id: str,
    actor_role: str | None = None,
    run_id: str,
    field_context: dict[str, str],
    request_text: str,
    proposed_use: str | None,
    output_text: str | None,
    trace_summary: dict[str, Any] | None = None,
    model: dict[str, Any] | None = None,
) -> None:
    """Record an agent draft/regeneration for a section."""
    if not section_id:  # untargeted runs (e.g. project-wide chat) aren't section events
        return
    record = _base_event(
        event_type="draft",
        tenant_id=tenant_id,
        project_id=project_id,
        section_id=section_id,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
    )
    record["run_id"] = run_id
    record["model"] = model or {}
    record["input_context"] = {
        "field_context": _redact_field_context(field_context or {}),
        "proposed_use": proposed_use,
        "request": request_text,
    }
    record["agent_output"] = {"text": output_text, "trace_summary": trace_summary or {}}
    _put_event(record)


def capture_section_transitions(
    *,
    tenant_id: str,
    project_id: str,
    entity_id: str | None,
    actor_user_id: str,
    actor_role: str | None = None,
    old_sections: list[Section],
    new_sections: list[Section],
) -> None:
    """Diff a project-state save and emit edit/approve/reopen events per changed section.

    Milestone granularity: one event per section whose body OR status actually changed.
    No-op saves produce nothing.
    """
    old_by_id = {s.id: s for s in old_sections}
    for new in new_sections:
        old = old_by_id.get(new.id)
        prev_status = old.status if old else None
        prev_body = old.body if old else ""
        body_changed = new.body != prev_body
        status_changed = new.status != prev_status
        if not body_changed and not status_changed:
            continue
        if new.status == "approved" and prev_status != "approved":
            event_type = "approve"
        elif prev_status == "approved" and new.status != "approved":
            event_type = "reopen"
        elif body_changed:
            event_type = "edit"
        else:
            continue  # status shuffle between draft/in_review with no body change -- skip
        record = _base_event(
            event_type=event_type,
            tenant_id=tenant_id,
            project_id=project_id,
            section_id=new.step_key or new.id,
            entity_id=entity_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )
        record["text"] = new.body
        record["prev_status"] = prev_status
        _put_event(record)
