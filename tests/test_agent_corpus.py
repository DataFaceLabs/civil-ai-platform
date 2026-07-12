"""Agent feedback capture: redaction, event schema, and milestone detection."""

import pytest

from civilai_platform.models.entities import Section
from civilai_platform.services import agent_corpus


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Intercept the S3 write and collect the event records instead."""
    records: list[dict] = []
    monkeypatch.setattr(agent_corpus, "_put_event", records.append)
    monkeypatch.setattr(agent_corpus, "_pii_keys", lambda: frozenset({"owner_name"}))
    return records


def _section(sid: str, body: str, status: str) -> Section:
    return Section(id=sid, title=sid, body=body, step_key=sid, status=status)


def test_redacts_owner_name_keeps_the_rest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_corpus, "_pii_keys", lambda: frozenset({"owner_name"}))
    out = agent_corpus._redact_field_context(
        {
            "owner_name": "Jane Landowner",
            "parcel_overview.owner_name": "Jane Landowner",
            "ZONING_REGS": "SF-3",
            "PROPERTY_ADDRESS": "20401 Trappers Trail",
        }
    )
    assert out["owner_name"] == "[redacted]"
    assert out["parcel_overview.owner_name"] == "[redacted]"  # dotted form too
    assert out["ZONING_REGS"] == "SF-3"
    assert out["PROPERTY_ADDRESS"] == "20401 Trappers Trail"  # address is public, kept


def test_draft_record_shape(captured: list[dict]) -> None:
    agent_corpus.capture_draft(
        tenant_id="t1",
        project_id="p1",
        section_id="zoning",
        entity_id="e1",
        actor_user_id="u1",
        actor_role="Admin",
        run_id="r1",
        field_context={"owner_name": "Jane", "ZONING_REGS": "SF-3"},
        request_text="draft the zoning section",
        proposed_use="single-family",
        output_text="The site is zoned SF-3...",
        trace_summary={"tokens": 42},
        model={"preset": "haiku"},
    )
    assert len(captured) == 1
    rec = captured[0]
    assert rec["event_type"] == "draft"
    assert rec["section_id"] == "zoning"
    assert rec["entity_id"] == "e1"
    assert rec["actor_user_id"] == "u1"
    assert rec["actor_role"] == "Admin"
    assert rec["input_context"]["field_context"]["owner_name"] == "[redacted]"
    assert rec["input_context"]["field_context"]["ZONING_REGS"] == "SF-3"
    assert rec["agent_output"]["text"] == "The site is zoned SF-3..."


def test_draft_without_section_is_not_captured(captured: list[dict]) -> None:
    agent_corpus.capture_draft(
        tenant_id="t1",
        project_id="p1",
        section_id=None,  # untargeted (e.g. project-wide chat)
        entity_id=None,
        actor_user_id="u1",
        run_id="r1",
        field_context={},
        request_text="",
        proposed_use=None,
        output_text="hi",
    )
    assert captured == []


def test_transitions_edit_approve(captured: list[dict]) -> None:
    old = [_section("zoning", "old body", "draft"), _section("flood", "", "draft")]
    new = [_section("zoning", "new body", "in_review"), _section("flood", "", "approved")]
    agent_corpus.capture_section_transitions(
        tenant_id="t1",
        project_id="p1",
        entity_id=None,
        actor_user_id="u1",
        actor_role="Analyst",
        old_sections=old,
        new_sections=new,
    )
    by_section = {r["section_id"]: r for r in captured}
    assert by_section["zoning"]["event_type"] == "edit"  # body changed
    assert by_section["zoning"]["text"] == "new body"
    assert by_section["zoning"]["actor_role"] == "Analyst"
    assert by_section["flood"]["event_type"] == "approve"  # status -> approved


def test_transitions_reopen(captured: list[dict]) -> None:
    old = [_section("zoning", "body", "approved")]
    new = [_section("zoning", "body v2", "draft")]
    agent_corpus.capture_section_transitions(
        tenant_id="t1",
        project_id="p1",
        entity_id=None,
        actor_user_id="u1",
        old_sections=old,
        new_sections=new,
    )
    assert len(captured) == 1
    assert captured[0]["event_type"] == "reopen"
    assert captured[0]["prev_status"] == "approved"


def test_transitions_noop_save_is_skipped(captured: list[dict]) -> None:
    old = [_section("zoning", "body", "approved")]
    new = [_section("zoning", "body", "approved")]  # nothing changed
    agent_corpus.capture_section_transitions(
        tenant_id="t1",
        project_id="p1",
        entity_id=None,
        actor_user_id="u1",
        old_sections=old,
        new_sections=new,
    )
    assert captured == []


def test_put_event_noop_when_bucket_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """No corpus bucket configured => capture is a silent no-op, never raises.

    Monkeypatch the settings lookup locally rather than clearing the global
    ``get_settings`` cache -- clearing it would rebuild settings from the ambient env and
    poison unrelated tests (they'd get a real DynamoDB/boto3 backend).
    """
    fake_settings = type("S", (), {"agent_corpus_bucket": None})()
    monkeypatch.setattr(agent_corpus, "get_settings", lambda: fake_settings)
    # Should not raise or attempt any S3 call.
    agent_corpus._put_event(
        {
            "tenant_id": "t",
            "project_id": "p",
            "section_id": "s",
            "event_type": "draft",
            "event_id": "x",
        }
    )
