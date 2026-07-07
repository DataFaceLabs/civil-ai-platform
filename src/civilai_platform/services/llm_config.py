from __future__ import annotations

from civilai_platform.llm_defaults import default_llm_lab_config
from civilai_platform.models.api import LlmConfigResponse
from civilai_platform.models.entities import LlmBaselineTemplate, TenantLlmConfig, utc_now
from civilai_platform.store.base import PlatformStore


def ensure_llm_baseline(store: PlatformStore) -> LlmBaselineTemplate:
    existing = store.get_llm_baseline()
    if existing:
        return existing
    now = utc_now()
    baseline = LlmBaselineTemplate(
        version=1,
        config=default_llm_lab_config(),
        updated_at=now,
        updated_by_user_id=None,
    )
    store.put_llm_baseline(baseline)
    return baseline


def get_baseline_response(store: PlatformStore) -> LlmConfigResponse:
    baseline = ensure_llm_baseline(store)
    return LlmConfigResponse(
        version=baseline.version,
        config=baseline.config,
        updated_at=baseline.updated_at,
    )


def update_baseline(
    store: PlatformStore,
    *,
    config: dict,
    actor_user_id: str,
) -> LlmConfigResponse:
    current = ensure_llm_baseline(store)
    now = utc_now()
    updated = LlmBaselineTemplate(
        version=current.version + 1,
        config=config,
        updated_at=now,
        updated_by_user_id=actor_user_id,
    )
    store.put_llm_baseline(updated)
    return LlmConfigResponse(
        version=updated.version,
        config=updated.config,
        updated_at=updated.updated_at,
    )


def copy_baseline_to_tenant(store: PlatformStore, tenant_id: str) -> TenantLlmConfig:
    baseline = ensure_llm_baseline(store)
    now = utc_now()
    tenant_cfg = TenantLlmConfig(
        tenant_id=tenant_id,
        baseline_version_at_copy=baseline.version,
        config=dict(baseline.config),
        updated_at=now,
    )
    store.put_tenant_llm_config(tenant_cfg)
    return tenant_cfg


def get_tenant_llm_response(store: PlatformStore, tenant_id: str) -> LlmConfigResponse:
    cfg = store.get_tenant_llm_config(tenant_id)
    if not cfg:
        cfg = copy_baseline_to_tenant(store, tenant_id)
    return LlmConfigResponse(
        version=int(cfg.config.get("version", 1)),
        baseline_version_at_copy=cfg.baseline_version_at_copy,
        config=cfg.config,
        updated_at=cfg.updated_at,
    )


def restore_tenant_llm_from_baseline(store: PlatformStore, tenant_id: str) -> LlmConfigResponse:
    """Replace tenant LLM config with a fresh copy of the current platform baseline."""
    tenant_cfg = copy_baseline_to_tenant(store, tenant_id)
    return LlmConfigResponse(
        version=int(tenant_cfg.config.get("version", 1)),
        baseline_version_at_copy=tenant_cfg.baseline_version_at_copy,
        config=tenant_cfg.config,
        updated_at=tenant_cfg.updated_at,
    )


def update_tenant_llm(
    store: PlatformStore,
    *,
    tenant_id: str,
    config: dict,
) -> LlmConfigResponse:
    existing = store.get_tenant_llm_config(tenant_id)
    baseline_version = existing.baseline_version_at_copy if existing else ensure_llm_baseline(store).version
    now = utc_now()
    updated = TenantLlmConfig(
        tenant_id=tenant_id,
        baseline_version_at_copy=baseline_version,
        config=config,
        updated_at=now,
    )
    store.put_tenant_llm_config(updated)
    return LlmConfigResponse(
        version=int(config.get("version", 1)),
        baseline_version_at_copy=baseline_version,
        config=config,
        updated_at=now,
    )
