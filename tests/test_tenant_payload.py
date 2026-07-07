from civilai_platform.store.tenant_payload import collect_known_slugs, ensure_url_slug


def test_collect_known_slugs() -> None:
    payloads = [
        {"name": "A", "url_slug": "firm-a"},
        {"name": "B"},
        {"name": "C", "url_slug": "firm-c"},
    ]
    assert collect_known_slugs(payloads) == {"firm-a", "firm-c"}


def test_ensure_url_slug_preserves_existing() -> None:
    reserved: set[str] = set()
    payload = {"name": "ATX Civil", "url_slug": "atx-civil"}
    updated, backfilled = ensure_url_slug(payload, reserved)
    assert updated["url_slug"] == "atx-civil"
    assert backfilled is False
    assert reserved == {"atx-civil"}


def test_ensure_url_slug_backfills_missing() -> None:
    reserved = {"existing-firm"}
    payload = {"name": "ATX Civil Engineering"}
    updated, backfilled = ensure_url_slug(payload, reserved)
    assert backfilled is True
    assert updated["url_slug"] == "atx-civil-engineering"
    assert "atx-civil-engineering" in reserved


def test_ensure_url_slug_avoids_collision() -> None:
    reserved = {"atx-civil"}
    payload = {"name": "ATX Civil"}
    updated, backfilled = ensure_url_slug(payload, reserved)
    assert backfilled is True
    assert updated["url_slug"] == "atx-civil-2"
