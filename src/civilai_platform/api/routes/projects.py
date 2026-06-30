from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from civilai_platform.api.deps import get_store_dep, tenant_ctx
from civilai_platform.auth.authz import require_membership
from civilai_platform.auth.context import AuthContext
from civilai_platform.models.api import (
    ArtifactPresignRequest,
    ArtifactPresignResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectStatePatch,
    ProjectStateResponse,
    ProjectUpdate,
)
from civilai_platform.models.entities import Role
from civilai_platform.services import artifacts as artifact_svc
from civilai_platform.services import project as project_svc
from civilai_platform.store.base import PlatformStore

router = APIRouter(prefix="/v1/projects", tags=["projects"])


def _member_ctx(ctx: Annotated[AuthContext, Depends(tenant_ctx)]) -> AuthContext:
    require_membership(ctx, Role.VIEWER)
    return ctx


def _writer_ctx(ctx: Annotated[AuthContext, Depends(tenant_ctx)]) -> AuthContext:
    require_membership(ctx, Role.ANALYST)
    return ctx


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    ctx: Annotated[AuthContext, Depends(_member_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> list[ProjectResponse]:
    assert ctx.tenant_id
    return project_svc.list_projects(store, ctx.tenant_id)


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(
    body: ProjectCreate,
    ctx: Annotated[AuthContext, Depends(_writer_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> ProjectResponse:
    assert ctx.tenant_id
    return project_svc.create_project(
        store,
        tenant_id=ctx.tenant_id,
        owner_user_id=ctx.user_id,
        actor_user_id=ctx.user_id,
        data=body,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    ctx: Annotated[AuthContext, Depends(_member_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> ProjectResponse:
    assert ctx.tenant_id
    project = store.get_project(ctx.tenant_id, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return ProjectResponse.from_entity(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
def patch_project(
    project_id: str,
    body: ProjectUpdate,
    ctx: Annotated[AuthContext, Depends(_writer_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> ProjectResponse:
    assert ctx.tenant_id
    try:
        return project_svc.update_project(
            store,
            tenant_id=ctx.tenant_id,
            project_id=project_id,
            actor_user_id=ctx.user_id,
            data=body,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    ctx: Annotated[AuthContext, Depends(_writer_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> None:
    assert ctx.tenant_id
    try:
        project_svc.delete_project(
            store,
            tenant_id=ctx.tenant_id,
            project_id=project_id,
            actor_user_id=ctx.user_id,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{project_id}/state", response_model=ProjectStateResponse)
def get_project_state(
    project_id: str,
    ctx: Annotated[AuthContext, Depends(_member_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> ProjectStateResponse:
    assert ctx.tenant_id
    try:
        return project_svc.get_project_state(store, ctx.tenant_id, project_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.patch("/{project_id}/state", response_model=ProjectStateResponse)
def patch_project_state(
    project_id: str,
    body: ProjectStatePatch,
    ctx: Annotated[AuthContext, Depends(_writer_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> ProjectStateResponse:
    assert ctx.tenant_id
    try:
        return project_svc.patch_project_state(
            store,
            tenant_id=ctx.tenant_id,
            project_id=project_id,
            actor_user_id=ctx.user_id,
            patch=body,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{project_id}/artifacts", response_model=ArtifactPresignResponse)
def presign_artifact(
    project_id: str,
    body: ArtifactPresignRequest,
    ctx: Annotated[AuthContext, Depends(_writer_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> ArtifactPresignResponse:
    assert ctx.tenant_id
    if not store.get_project(ctx.tenant_id, project_id):
        raise HTTPException(404, "Project not found")
    return artifact_svc.presign_upload(
        tenant_id=ctx.tenant_id,
        project_id=project_id,
        request=body,
    )


@router.put("/{project_id}/artifacts/upload")
async def upload_artifact_dev(
    project_id: str,
    request: Request,
    key: Annotated[str, Query()],
    ctx: Annotated[AuthContext, Depends(_writer_ctx)],
) -> dict[str, str]:
    """Dev memory-backend artifact upload."""
    from civilai_platform.settings import get_settings

    if get_settings().artifact_backend != "memory":
        raise HTTPException(400, "Direct upload only in memory artifact mode")
    data = await request.body()
    artifact_svc.store_memory_artifact(key, data)
    return {"s3_key": key, "bytes": str(len(data))}


@router.get("/{project_id}/artifacts/download")
def download_artifact(
    project_id: str,
    key: Annotated[str, Query()],
    ctx: Annotated[AuthContext, Depends(_member_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> Response:
    assert ctx.tenant_id
    if not store.get_project(ctx.tenant_id, project_id):
        raise HTTPException(404, "Project not found")
    data = artifact_svc.download_artifact_bytes(key)
    if not data:
        raise HTTPException(404, "Artifact not found")
    return Response(
        content=data,
        media_type=artifact_svc.artifact_media_type(key),
        headers={"Content-Disposition": f'inline; filename="{key.rsplit("/", 1)[-1]}"'},
    )
