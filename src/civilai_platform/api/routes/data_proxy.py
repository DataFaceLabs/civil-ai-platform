"""Platform routes proxying the civil-ai-data typed-tool manifest (contract §7).

Authenticated-platform-member baseline only (Role.VIEWER) — there is no tenant
dimension on lake reads (see data_access_api_contract.md §2), so this router is
deliberately not nested under /v1/projects/{project_id}.

PII scope is never exposed through these routes: every call passes
include_pii=False (the DataProxyClient default). Revisit once Cognito auth is live.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from civilai_platform.api.deps import tenant_ctx
from civilai_platform.auth.authz import require_membership
from civilai_platform.auth.context import AuthContext
from civilai_platform.models.entities import Role
from civilai_platform.services.data_proxy import DataProxyClient

router = APIRouter(prefix="/v1/data-proxy", tags=["data-proxy"])


def _viewer_ctx(ctx: Annotated[AuthContext, Depends(tenant_ctx)]) -> AuthContext:
    require_membership(ctx, Role.VIEWER)
    return ctx


def get_data_proxy() -> DataProxyClient:
    return DataProxyClient()


class ResolveBody(BaseModel):
    address: str | None = None
    parcel_id: str | None = None


@router.post("/entities/resolve")
def resolve(
    body: ResolveBody,
    _ctx: Annotated[AuthContext, Depends(_viewer_ctx)],
    client: Annotated[DataProxyClient, Depends(get_data_proxy)],
) -> dict[str, Any]:
    return client.resolve_parcel(address=body.address, parcel_id=body.parcel_id)


@router.get("/sections/{section_id}/facts/{entity_id}")
def section_facts(
    section_id: str,
    entity_id: str,
    _ctx: Annotated[AuthContext, Depends(_viewer_ctx)],
    client: Annotated[DataProxyClient, Depends(get_data_proxy)],
) -> dict[str, Any]:
    return client.get_section_facts(entity_id, section_id)


@router.get("/fe/site/by-entity/{entity_id}")
def site_by_entity(
    entity_id: str,
    _ctx: Annotated[AuthContext, Depends(_viewer_ctx)],
    client: Annotated[DataProxyClient, Depends(get_data_proxy)],
) -> dict[str, Any]:
    return client.get_site(entity_id)


@router.get("/entities/{entity_id}/determinations")
def determinations(
    entity_id: str,
    _ctx: Annotated[AuthContext, Depends(_viewer_ctx)],
    client: Annotated[DataProxyClient, Depends(get_data_proxy)],
) -> dict[str, Any]:
    return client.run_determinations(entity_id)
