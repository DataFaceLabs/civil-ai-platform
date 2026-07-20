"""Server-rendered feasibility-study export routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from civilai_platform.api.deps import get_store_dep, tenant_ctx
from civilai_platform.auth.authz import require_membership
from civilai_platform.auth.context import AuthContext
from civilai_platform.models.api import ExportCreate, ExportJobResponse
from civilai_platform.models.entities import Role
from civilai_platform.services.data_routing import data_api_base_for_request
from civilai_platform.services.export import service as export_svc
from civilai_platform.store.base import PlatformStore

router = APIRouter(prefix="/v1/projects", tags=["exports"])


def _analyst_ctx(ctx: Annotated[AuthContext, Depends(tenant_ctx)]) -> AuthContext:
    require_membership(ctx, Role.ANALYST)
    return ctx


def _viewer_ctx(ctx: Annotated[AuthContext, Depends(tenant_ctx)]) -> AuthContext:
    require_membership(ctx, Role.VIEWER)
    return ctx


@router.post("/{project_id}/exports", response_model=ExportJobResponse, status_code=201)
def create_export(
    project_id: str,
    body: ExportCreate,
    request: Request,
    ctx: Annotated[AuthContext, Depends(_analyst_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> ExportJobResponse:
    assert ctx.tenant_id
    if not store.get_project(ctx.tenant_id, project_id):
        raise HTTPException(404, "Project not found")
    if not store.get_project_state(ctx.tenant_id, project_id):
        raise HTTPException(409, "Project state is required before export")
    job = export_svc.start_export(
        store,
        tenant_id=ctx.tenant_id,
        project_id=project_id,
        actor_user_id=ctx.user_id,
        skin_id=body.skin_id,
        data_api_base=data_api_base_for_request(request),
    )
    return ExportJobResponse.from_entity(job)


@router.get("/{project_id}/exports/{job_id}", response_model=ExportJobResponse)
def get_export(
    project_id: str,
    job_id: str,
    ctx: Annotated[AuthContext, Depends(_viewer_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> ExportJobResponse:
    assert ctx.tenant_id
    job = export_svc.get_export(
        store,
        tenant_id=ctx.tenant_id,
        project_id=project_id,
        job_id=job_id,
    )
    if not job:
        raise HTTPException(404, "Export job not found")
    return ExportJobResponse.from_entity(job)
