from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from civilai_platform.api.deps import admin_ctx, get_store_dep, tenant_ctx
from civilai_platform.auth.context import AuthContext
from civilai_platform.models.api import (
    EffectiveGuardRailsResponse,
    GuardRailsAuditListResponse,
    GuardRailsScopeListResponse,
    GuardRailsScopeResponse,
    GuardRailsScopeUpsert,
)
from civilai_platform.services import guardrails as guardrails_svc
from civilai_platform.services.audit import record_audit
from civilai_platform.services.data_proxy import DataProxyClient
from civilai_platform.services.data_routing import data_api_base_for_request
from civilai_platform.store.base import PlatformStore

router = APIRouter(tags=["guardrails"])


@router.get("/v1/guardrails/resolve", response_model=EffectiveGuardRailsResponse)
def resolve_guardrails(
    request: Request,
    ctx: Annotated[AuthContext, Depends(tenant_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
    domain: str = Query("zoning", min_length=1),
    state_abbr: str | None = Query(None),
    county_fips: str | None = Query(None),
    jurisdiction_key: str | None = Query(None),
    catalog_ready: bool | None = Query(None),
) -> EffectiveGuardRailsResponse:
    _ = ctx
    client = DataProxyClient(base_url=data_api_base_for_request(request))
    return guardrails_svc.resolve_guardrails(
        store,
        domain=domain,
        state_abbr=state_abbr,
        county_fips=county_fips,
        jurisdiction_key=jurisdiction_key,
        catalog_ready=catalog_ready,
        data_client=client,
    )


@router.get(
    "/v1/admin/guardrails/zoning/scopes",
    response_model=GuardRailsScopeListResponse,
)
def list_guardrails_scopes(
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> GuardRailsScopeListResponse:
    _ = ctx
    return guardrails_svc.list_scopes_response(store)


@router.get(
    "/v1/admin/guardrails/zoning/audit",
    response_model=GuardRailsAuditListResponse,
)
def list_guardrails_audit(
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
    limit: int = Query(50, ge=1, le=200),
) -> GuardRailsAuditListResponse:
    _ = ctx
    tenant_id = ctx.tenant_id or "platform"
    return guardrails_svc.list_audit_response(store, tenant_id=tenant_id, limit=limit)


@router.get(
    "/v1/admin/guardrails/zoning/scopes/{scope_key:path}",
    response_model=GuardRailsScopeResponse,
)
def get_guardrails_scope(
    scope_key: str,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> GuardRailsScopeResponse:
    _ = ctx
    record = guardrails_svc.get_scope_response(
        store,
        domain=guardrails_svc.GUARDRAILS_DOMAIN,
        scope_key=scope_key,
    )
    if not record:
        raise HTTPException(404, f"Guard rail scope not found: {scope_key!r}")
    return record


@router.put(
    "/v1/admin/guardrails/zoning/scopes/{scope_key:path}",
    response_model=GuardRailsScopeResponse,
)
def put_guardrails_scope(
    scope_key: str,
    body: GuardRailsScopeUpsert,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> GuardRailsScopeResponse:
    updated = guardrails_svc.upsert_scope(
        store,
        domain=guardrails_svc.GUARDRAILS_DOMAIN,
        scope_key=scope_key,
        fields=body.fields,
        topics=body.topics,
        schema_version=body.schema_version,
        actor_user_id=ctx.user_id,
    )
    record_audit(
        tenant_id=ctx.tenant_id or "platform",
        actor_user_id=ctx.user_id,
        action="guardrails.scope.upsert",
        resource_type="guardrails_scope",
        resource_id=scope_key,
        detail={"domain": guardrails_svc.GUARDRAILS_DOMAIN},
    )
    return updated


@router.delete("/v1/admin/guardrails/zoning/scopes/{scope_key:path}", status_code=204)
def delete_guardrails_scope(
    scope_key: str,
    ctx: Annotated[AuthContext, Depends(admin_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> None:
    deleted = guardrails_svc.delete_scope(
        store,
        domain=guardrails_svc.GUARDRAILS_DOMAIN,
        scope_key=scope_key,
        actor_user_id=ctx.user_id,
    )
    if not deleted:
        raise HTTPException(404, f"Guard rail scope not found: {scope_key!r}")
    record_audit(
        tenant_id=ctx.tenant_id or "platform",
        actor_user_id=ctx.user_id,
        action="guardrails.scope.delete",
        resource_type="guardrails_scope",
        resource_id=scope_key,
        detail={"domain": guardrails_svc.GUARDRAILS_DOMAIN},
    )
