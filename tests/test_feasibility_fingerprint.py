from __future__ import annotations

from civilai_platform.services.feasibility_fingerprint import (
    compact_feasibility_fingerprint,
    hash_section_body,
)


def test_hash_section_body_matches_fe_cyrb53_vectors() -> None:
    # Vectors from civil-ai-fe hashSectionBody (node).
    assert hash_section_body("") == "488bdcb81aee8d83"
    assert hash_section_body("<p>A</p>") == "bc7d2105b046e988"


def test_compact_feasibility_fingerprint_strips_body_and_fields() -> None:
    legacy = (
        '[{"key":"parcel","body":"<p>'
        + ("x" * 5000)
        + '</p>","status":"approved","fields":{"A":{"value":"'
        + ("y" * 2000)
        + '"}}},'
        '{"key":"zoning","body":"<p>B</p>","status":"draft","fields":{}}]'
    )
    compact = compact_feasibility_fingerprint(legacy)
    assert compact is not None
    assert len(compact) < 500
    assert "<p>" not in compact
    assert "fields" not in compact
    assert '"bodyHash"' in compact
    assert hash_section_body("<p>B</p>") in compact


def test_compact_passthrough_when_already_compact() -> None:
    already = '[{"key":"parcel","bodyHash":"abc","status":"draft"}]'
    assert compact_feasibility_fingerprint(already) == (
        '[{"key":"parcel","bodyHash":"abc","status":"draft"}]'
    )
