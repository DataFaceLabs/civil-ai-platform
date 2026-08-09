"""Platform routes proxying the civil-ai-data typed-tool manifest (contract §7).

Authenticated-platform-member baseline only (Role.VIEWER) — there is no tenant
dimension on lake reads (see data_access_api_contract.md §2), so this router is
deliberately not nested under /v1/projects/{project_id}.

PII scope is never exposed through these routes: every call passes
include_pii=False (the DataProxyClient default). Revisit once Cognito auth is live.
"""

from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from civilai_platform.api.deps import tenant_ctx
from civilai_platform.auth.authz import require_membership
from civilai_platform.auth.context import AuthContext
from civilai_platform.models.entities import Role
from civilai_platform.services.data_proxy import DataProxyClient, passthrough_timeout_sec
from civilai_platform.services.data_routing import data_api_base_for_request

router = APIRouter(prefix="/v1/data-proxy", tags=["data-proxy"])

# Read-only site-data families the browser is allowed to reach through the proxy. The
# FE's staged site flow (resolve-address -> per-section facts -> assemble, plus the
# by-address/by-parcel single-shot fallbacks) all live under these prefixes; Explorer
# also needs tiles + serving freshness. Nothing here mutates lake data or touches
# the experimental LLM/admin surfaces.
_PASSTHROUGH_ALLOWED_PREFIXES = (
    "fe/site/",
    "fe/tap-cards/",
    "fe/tiles/",
    "fe/serving/",
    "internal/trust/",
    "sections/",
)


def _viewer_ctx(ctx: Annotated[AuthContext, Depends(tenant_ctx)]) -> AuthContext:
    require_membership(ctx, Role.VIEWER)
    return ctx


def get_data_proxy(request: Request) -> DataProxyClient:
    return DataProxyClient(base_url=data_api_base_for_request(request))


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


@router.api_route("/passthrough/{data_path:path}", methods=["GET", "POST"])
async def passthrough(
    data_path: str,
    request: Request,
    _ctx: Annotated[AuthContext, Depends(_viewer_ctx)],
    client: Annotated[DataProxyClient, Depends(get_data_proxy)],
) -> Response:
    """Status-preserving proxy for the FE's read-only site-data calls.

    The browser can't reach the EC2 data API directly (HTTP data API vs HTTPS app =
    mixed-content block, and no service key belongs in a browser). This forwards an
    allowlisted set of read paths server-side with the service key, viewer-gated and
    PII off, mirroring the upstream status/body so the FE's 409/404/503 handling is
    unchanged.

    Upstream timeouts / connection failures become 504 / 502 with a JSON ``detail``
    string the FE already surfaces — never an unhandled ASGI 500 stack trace.
    """
    if ".." in data_path or not data_path.startswith(_PASSTHROUGH_ALLOWED_PREFIXES):
        raise HTTPException(403, "Path not allowed through the data proxy")
    body: dict[str, Any] | None = None
    if request.method == "POST":
        raw = await request.body()
        if raw:
            import json as _json

            try:
                body = _json.loads(raw)
            except ValueError as exc:
                raise HTTPException(400, "Request body must be JSON") from exc
    try:
        upstream = client.passthrough(request.method, data_path, json=body)
    except httpx.TimeoutException as exc:
        budget = passthrough_timeout_sec(data_path)
        raise HTTPException(
            status_code=504,
            detail=(
                f"Data API timed out after {budget:.0f}s while handling "
                f"{request.method} /v1/{data_path.lstrip('/')}. "
                "Try again, or search with a CAD parcel ID if the address is slow."
            ),
        ) from exc
    except httpx.TransportError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Cannot reach the data API for {request.method} "
                f"/v1/{data_path.lstrip('/')}: {exc}"
            ),
        ) from exc
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
    )
