"""Facts Guard Rails service (zoning domain v1)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from civilai_platform.models.api import (
    EffectiveGuardRailsResponse,
    GuardRailsAuditEventResponse,
    GuardRailsAuditListResponse,
    GuardRailsScopeListResponse,
    GuardRailsScopeResponse,
)
from civilai_platform.models.entities import GuardRailsScopeRecord, GuardRailsVersionMeta, utc_now
from civilai_platform.services.data_proxy import DataProxyClient
from civilai_platform.services.guardrails_merge import (
    EffectiveGuardRails,
    FieldGuardRail,
    GuardRailsScopePayload,
    TopicGuardRail,
    merge_guardrails,
    scope_keys_for_request,
)
from civilai_platform.store.base import PlatformStore

GUARDRAILS_DOMAIN = "zoning"
_PLATFORM_ROOT = Path(__file__).resolve().parents[3]
_SEED_DIR = (
    _PLATFORM_ROOT.parent
    / "civil-ai-data"
    / "data"
    / "reference"
    / "facts_guardrails"
    / "zoning"
)


def _record_to_payload(record: GuardRailsScopeRecord) -> GuardRailsScopePayload:
    fields = {
        code: FieldGuardRail.model_validate(rule)
        for code, rule in record.fields.items()
    }
    topics = {
        topic_id: TopicGuardRail.model_validate(rule)
        for topic_id, rule in record.topics.items()
    }
    return GuardRailsScopePayload(
        domain=record.domain,
        scope_key=record.scope_key,
        schema_version=record.schema_version,
        fields=fields,
        topics=topics,
    )


def _scope_version_hash(scopes: list[GuardRailsScopeRecord]) -> str:
    payload = {
        "domain": GUARDRAILS_DOMAIN,
        "scopes": {
            record.scope_key: {
                "fields": record.fields,
                "topics": record.topics,
                "schema_version": record.schema_version,
            }
            for record in sorted(scopes, key=lambda r: r.scope_key)
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def refresh_guardrails_version_meta(
    store: PlatformStore,
    *,
    domain: str = GUARDRAILS_DOMAIN,
    actor_user_id: str | None = None,
) -> GuardRailsVersionMeta:
    scopes = store.list_guardrails_scopes(domain)
    meta = GuardRailsVersionMeta(
        domain=domain,
        version_hash=_scope_version_hash(scopes),
        updated_at=utc_now(),
        updated_by_user_id=actor_user_id,
    )
    store.put_guardrails_version_meta(meta)
    return meta


def scope_to_response(record: GuardRailsScopeRecord) -> GuardRailsScopeResponse:
    return GuardRailsScopeResponse(
        domain=record.domain,
        scope_key=record.scope_key,
        schema_version=record.schema_version,
        fields=record.fields,
        topics=record.topics,
        updated_at=record.updated_at,
        updated_by_user_id=record.updated_by_user_id,
    )


def effective_to_response(effective: EffectiveGuardRails) -> EffectiveGuardRailsResponse:
    return EffectiveGuardRailsResponse(
        domain=effective.domain,
        fields={k: v.model_dump() for k, v in effective.fields.items()},
        topics={k: v.model_dump() for k, v in effective.topics.items()},
        applied_scopes=effective.applied_scopes,
        guardrails_version=effective.guardrails_version,
        topic_hydrate_enabled=effective.topic_hydrate_enabled,
    )


def list_scopes_response(store: PlatformStore, *, domain: str = GUARDRAILS_DOMAIN) -> GuardRailsScopeListResponse:
    scopes = sorted(store.list_guardrails_scopes(domain), key=lambda r: r.scope_key)
    meta = store.get_guardrails_version_meta(domain)
    return GuardRailsScopeListResponse(
        scopes=[scope_to_response(s) for s in scopes],
        guardrails_version=meta.version_hash if meta else None,
        version_updated_at=meta.updated_at if meta else None,
    )


def list_audit_response(
    store: PlatformStore,
    *,
    tenant_id: str = "platform",
    limit: int = 50,
) -> GuardRailsAuditListResponse:
    events = store.list_audit_events(tenant_id, limit=limit)
    filtered = [
        e
        for e in events
        if e.resource_type == "guardrails_scope"
        or e.action.startswith("guardrails.")
    ]
    return GuardRailsAuditListResponse(
        events=[
            GuardRailsAuditEventResponse(
                event_id=e.event_id,
                actor_user_id=e.actor_user_id,
                action=e.action,
                resource_id=e.resource_id,
                detail=e.detail,
                created_at=e.created_at,
            )
            for e in filtered[:limit]
        ]
    )


def get_scope_response(
    store: PlatformStore,
    *,
    domain: str,
    scope_key: str,
) -> GuardRailsScopeResponse | None:
    record = store.get_guardrails_scope(domain, scope_key)
    return scope_to_response(record) if record else None


def upsert_scope(
    store: PlatformStore,
    *,
    domain: str,
    scope_key: str,
    fields: dict[str, Any],
    topics: dict[str, Any],
    schema_version: int,
    actor_user_id: str,
) -> GuardRailsScopeResponse:
    record = GuardRailsScopeRecord(
        domain=domain,
        scope_key=scope_key,
        schema_version=schema_version,
        fields=fields,
        topics=topics,
        updated_at=utc_now(),
        updated_by_user_id=actor_user_id,
    )
    store.put_guardrails_scope(record)
    refresh_guardrails_version_meta(store, domain=domain, actor_user_id=actor_user_id)
    return scope_to_response(record)


def delete_scope(
    store: PlatformStore,
    *,
    domain: str,
    scope_key: str,
    actor_user_id: str,
) -> bool:
    existing = store.get_guardrails_scope(domain, scope_key)
    if not existing:
        return False
    store.delete_guardrails_scope(domain, scope_key)
    refresh_guardrails_version_meta(store, domain=domain, actor_user_id=actor_user_id)
    return True


def _layers_for_request(
    store: PlatformStore,
    *,
    state_abbr: str | None,
    county_fips: str | None,
    jurisdiction_key: str | None,
    domain: str = GUARDRAILS_DOMAIN,
) -> list[GuardRailsScopePayload]:
    keys = scope_keys_for_request(
        state_abbr=state_abbr,
        county_fips=county_fips,
        jurisdiction_key=jurisdiction_key,
    )
    layers: list[GuardRailsScopePayload] = []
    for key in keys:
        record = store.get_guardrails_scope(domain, key)
        if record:
            layers.append(_record_to_payload(record))
    return layers


def jurisdiction_catalog_ready(
    client: DataProxyClient | None,
    jurisdiction_key: str | None,
) -> bool:
    if not jurisdiction_key or not jurisdiction_key.strip():
        return False
    if client is None:
        return False
    try:
        payload = client.request("GET", "/v1/regtext/catalog")
    except RuntimeError:
        return False
    jurisdictions = payload.get("jurisdictions") if isinstance(payload, dict) else None
    if not isinstance(jurisdictions, list):
        return False
    key = jurisdiction_key.strip().lower()
    for row in jurisdictions:
        if not isinstance(row, dict):
            continue
        if str(row.get("jurisdiction_key", "")).lower() == key:
            return row.get("status") == "ready"
    return False


def resolve_guardrails(
    store: PlatformStore,
    *,
    domain: str = GUARDRAILS_DOMAIN,
    state_abbr: str | None = None,
    county_fips: str | None = None,
    jurisdiction_key: str | None = None,
    catalog_ready: bool | None = None,
    data_client: DataProxyClient | None = None,
) -> EffectiveGuardRailsResponse:
    if domain != GUARDRAILS_DOMAIN:
        return effective_to_response(EffectiveGuardRails(domain=GUARDRAILS_DOMAIN))

    ready = (
        catalog_ready
        if catalog_ready is not None
        else jurisdiction_catalog_ready(data_client, jurisdiction_key)
    )
    layers = _layers_for_request(
        store,
        state_abbr=state_abbr,
        county_fips=county_fips,
        jurisdiction_key=jurisdiction_key,
        domain=domain,
    )
    effective = merge_guardrails(layers, catalog_ready=ready)
    return effective_to_response(effective)


def resolve_guardrails_effective(
    store: PlatformStore,
    *,
    domain: str = GUARDRAILS_DOMAIN,
    state_abbr: str | None = None,
    county_fips: str | None = None,
    jurisdiction_key: str | None = None,
    catalog_ready: bool | None = None,
    data_client: DataProxyClient | None = None,
) -> EffectiveGuardRails:
    """Internal merge result for server-side compute (brief, agent)."""
    if domain != GUARDRAILS_DOMAIN:
        return EffectiveGuardRails(domain=GUARDRAILS_DOMAIN)

    ready = (
        catalog_ready
        if catalog_ready is not None
        else jurisdiction_catalog_ready(data_client, jurisdiction_key)
    )
    layers = _layers_for_request(
        store,
        state_abbr=state_abbr,
        county_fips=county_fips,
        jurisdiction_key=jurisdiction_key,
        domain=domain,
    )
    return merge_guardrails(layers, catalog_ready=ready)


def _load_seed_yaml(path: Path) -> GuardRailsScopeRecord:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    scope_key = str(raw.get("scope_key", ""))
    return GuardRailsScopeRecord(
        domain=str(raw.get("domain", GUARDRAILS_DOMAIN)),
        scope_key=scope_key,
        schema_version=int(raw.get("schema_version", 1)),
        fields=raw.get("fields") or {},
        topics=raw.get("topics") or {},
        updated_at=utc_now(),
        updated_by_user_id="ops:seed_guardrails",
    )


def seed_zoning_guardrails_from_yaml(
    store: PlatformStore,
    *,
    seed_dir: Path | None = None,
    refresh: bool = False,
    actor_user_id: str = "ops:seed_guardrails",
) -> int:
    """Load seed YAML from civil-ai-data into the platform store."""
    base = seed_dir or _SEED_DIR
    if not base.is_dir():
        raise FileNotFoundError(f"Guard rails seed directory not found: {base}")

    paths: list[Path] = []
    default = base / "_default.yaml"
    if default.is_file():
        paths.append(default)
    for sub in ("states", "counties", "jurisdictions"):
        folder = base / sub
        if folder.is_dir():
            paths.extend(sorted(folder.glob("*.yaml")))

    written = 0
    for path in paths:
        record = _load_seed_yaml(path)
        existing = store.get_guardrails_scope(record.domain, record.scope_key)
        if existing and not refresh:
            continue
        record.updated_by_user_id = actor_user_id
        record.updated_at = utc_now()
        store.put_guardrails_scope(record)
        written += 1

    if written or refresh:
        refresh_guardrails_version_meta(store, domain=GUARDRAILS_DOMAIN, actor_user_id=actor_user_id)
    return written
