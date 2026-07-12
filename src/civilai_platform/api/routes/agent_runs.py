"""Agent run API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from civilai_platform.api.deps import get_store_dep, tenant_ctx
from civilai_platform.auth.authz import require_membership
from civilai_platform.auth.context import AuthContext
from civilai_platform.models.api import AgentRunCreate, AgentRunResponse
from civilai_platform.models.entities import Role
from civilai_platform.services import agent_run as agent_run_svc
from civilai_platform.store.base import PlatformStore

router = APIRouter(prefix="/v1/projects", tags=["agent-runs"])


def _analyst_ctx(ctx: Annotated[AuthContext, Depends(tenant_ctx)]) -> AuthContext:
    require_membership(ctx, Role.ANALYST)
    return ctx


def _viewer_ctx(ctx: Annotated[AuthContext, Depends(tenant_ctx)]) -> AuthContext:
    require_membership(ctx, Role.VIEWER)
    return ctx


@router.post("/{project_id}/agent-runs", response_model=AgentRunResponse, status_code=201)
def create_agent_run(
    project_id: str,
    body: AgentRunCreate,
    ctx: Annotated[AuthContext, Depends(_analyst_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> AgentRunResponse:
    assert ctx.tenant_id
    project = store.get_project(ctx.tenant_id, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    run = agent_run_svc.start_agent_run(
        store,
        tenant_id=ctx.tenant_id,
        project_id=project_id,
        actor_user_id=ctx.user_id,
        request_text=body.request,
        entity_id=body.entity_id,
        active_section_id=body.active_section_id,
        workflow=body.workflow,
        field_context=body.field_context,
        proposed_use=body.proposed_use,
        thread_memory=body.thread_memory,
        section_body_plain=body.section_body_plain,
        actor_role=ctx.role.value if ctx.role else None,
    )
    return AgentRunResponse.from_entity(run)


@router.get("/{project_id}/agent-runs/{run_id}", response_model=AgentRunResponse)
def get_agent_run(
    project_id: str,
    run_id: str,
    ctx: Annotated[AuthContext, Depends(_viewer_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> AgentRunResponse:
    assert ctx.tenant_id
    run = agent_run_svc.get_agent_run(
        store,
        tenant_id=ctx.tenant_id,
        project_id=project_id,
        run_id=run_id,
    )
    if not run:
        raise HTTPException(404, "Agent run not found")
    return AgentRunResponse.from_entity(run)
