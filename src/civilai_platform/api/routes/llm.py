from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from civilai_platform.api.deps import (
    admin_ctx,
    get_store_dep,
    platform_admin_tenant_ctx,
    tenant_admin_ctx,
)
from civilai_platform.auth.context import AuthContext
from civilai_platform.models.api import (
    LlmConfigResponse,
    LlmConfigUpdate,
    LlmInvokeJobResponse,
    LogoPresignRequest,
    LogoPresignResponse,
    TenantLlmInvokeRequest,
)
from civilai_platform.services import artifacts as artifact_svc
from civilai_platform.services import llm_config as llm_config_svc
from civilai_platform.services import llm_invoke as llm_invoke_svc
from civilai_platform.auth.actor import tenant_actor_user_id
from civilai_platform.services.audit import record_audit, record_audit_for_ctx
from civilai_platform.services.data_proxy import DataProxyClient
from civilai_platform.store.base import PlatformStore

router = APIRouter(tags=["llm", "tenant-branding"])


@router.get("/v1/admin/llm-baseline", response_model=LlmConfigResponse)
def get_llm_baseline(
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> LlmConfigResponse:
    _ = ctx
    return llm_config_svc.get_baseline_response(store)


@router.patch("/v1/admin/llm-baseline", response_model=LlmConfigResponse)
def patch_llm_baseline(
    body: LlmConfigUpdate,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> LlmConfigResponse:
    updated = llm_config_svc.update_baseline(
        store,
        config=body.config,
        actor_user_id=ctx.user_id,
    )
    record_audit(
        tenant_id=ctx.tenant_id or "platform",
        actor_user_id=ctx.user_id,
        action="llm_baseline.update",
        resource_type="llm_baseline",
        resource_id=str(updated.version),
    )
    return updated


@router.get("/v1/tenant/llm-config", response_model=LlmConfigResponse)
def get_tenant_llm_config(
    ctx: Annotated[AuthContext, Depends(platform_admin_tenant_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> LlmConfigResponse:
    assert ctx.tenant_id
    return llm_config_svc.get_tenant_llm_response(store, ctx.tenant_id)


@router.patch("/v1/tenant/llm-config", response_model=LlmConfigResponse)
def patch_tenant_llm_config(
    body: LlmConfigUpdate,
    ctx: Annotated[AuthContext, Depends(platform_admin_tenant_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> LlmConfigResponse:
    assert ctx.tenant_id
    actor_id = tenant_actor_user_id(store, ctx)
    updated = llm_config_svc.update_tenant_llm(
        store,
        tenant_id=ctx.tenant_id,
        config=body.config,
    )
    record_audit_for_ctx(
        ctx,
        action="tenant_llm.update",
        resource_type="tenant_llm_config",
        resource_id=ctx.tenant_id,
    )
    return updated


@router.post("/v1/tenant/llm-config/restore-baseline", response_model=LlmConfigResponse)
def restore_tenant_llm_config(
    ctx: Annotated[AuthContext, Depends(platform_admin_tenant_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> LlmConfigResponse:
    assert ctx.tenant_id
    restored = llm_config_svc.restore_tenant_llm_from_baseline(store, ctx.tenant_id)
    record_audit_for_ctx(
        ctx,
        action="tenant_llm.restore_baseline",
        resource_type="tenant_llm_config",
        resource_id=ctx.tenant_id,
    )
    return restored


@router.post("/v1/tenant/llm/invoke")
def invoke_tenant_llm(
    body: TenantLlmInvokeRequest,
    ctx: Annotated[AuthContext, Depends(platform_admin_tenant_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> dict[str, Any] | LlmInvokeJobResponse:
    assert ctx.tenant_id
    actor_id = tenant_actor_user_id(store, ctx)
    try:
        return llm_invoke_svc.start_tenant_llm_invoke(
            store,
            tenant_id=ctx.tenant_id,
            actor_user_id=actor_id,
            step_key=body.step_key,
            user_prompt=body.user_prompt,
            field_context=body.field_context,
            search_context_hint=body.search_context_hint,
            invoke_mode=body.invoke_mode,
            web_search_enabled=body.web_search_enabled,
        )
    except Exception as exc:
        raise HTTPException(502, f"LLM invoke failed: {exc}") from exc


@router.get("/v1/tenant/llm/invoke/{job_id}", response_model=LlmInvokeJobResponse)
def get_tenant_llm_invoke_job(
    job_id: str,
    ctx: Annotated[AuthContext, Depends(platform_admin_tenant_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> LlmInvokeJobResponse:
    assert ctx.tenant_id
    job = llm_invoke_svc.get_llm_invoke_job(
        store,
        tenant_id=ctx.tenant_id,
        job_id=job_id,
    )
    if not job:
        raise HTTPException(404, "LLM invoke job not found")
    return llm_invoke_svc.job_to_response(job)


@router.post("/v1/tenant/logo", response_model=LogoPresignResponse)
def presign_tenant_logo(
    body: LogoPresignRequest,
    ctx: Annotated[AuthContext, Depends(tenant_admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> LogoPresignResponse:
    assert ctx.tenant_id
    _ = store
    return artifact_svc.presign_tenant_logo(tenant_id=ctx.tenant_id, request=body)
