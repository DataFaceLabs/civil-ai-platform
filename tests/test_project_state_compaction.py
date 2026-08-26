from __future__ import annotations

from civilai_platform.models.entities import ProjectState, utc_now
from civilai_platform.services.project import (
    _compact_state_for_storage,
    _slim_site_payload_for_storage,
    _strip_parcel_list_thumbnail,
)


def test_slim_site_payload_drops_duplicated_field_views() -> None:
    heavy = {
        "entity_id": "ent-1",
        "geometry": {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}},
        "parcel": [{"code": "X", "value": "y" * 5000, "data_status": "complete"}],
        "zoning": [{"code": "ZONING", "value": "MF-4", "data_status": "complete"}],
        "serving_source": "lake",
    }
    slim = _slim_site_payload_for_storage(heavy)
    assert slim is not None
    assert slim["entity_id"] == "ent-1"
    assert slim["geometry"] == heavy["geometry"]
    assert slim["serving_source"] == "lake"
    assert "parcel" not in slim
    assert "zoning" not in slim


def test_strip_parcel_list_thumbnail() -> None:
    parcel = {
        "lat": 30.0,
        "lng": -97.0,
        "mapboxImageUrl": "https://example.com/map.png",
        "listThumbnailUrl": "data:image/jpeg;base64,abc",
    }
    stripped = _strip_parcel_list_thumbnail(parcel)
    assert stripped is not None
    assert "listThumbnailUrl" not in stripped
    assert stripped["mapboxImageUrl"] == parcel["mapboxImageUrl"]


def test_compact_state_for_storage_applies_slimming() -> None:
    state = ProjectState(
        project_id="p1",
        tenant_id="t1",
        sections=[],
        updated_at=utc_now(),
        parcel={
            "lat": 30.0,
            "lng": -97.0,
            "listThumbnailUrl": "data:image/jpeg;base64,abc",
        },
        site_payload={
            "entity_id": "ent-1",
            "parcel": [{"code": "X", "value": "y" * 2000, "data_status": "complete"}],
        },
    )
    compact = _compact_state_for_storage(state)
    assert compact.parcel is not None
    assert "listThumbnailUrl" not in compact.parcel
    assert compact.site_payload is not None
    assert "parcel" not in compact.site_payload
