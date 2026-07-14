from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from civilai_platform.api.deps import get_store_dep
from civilai_platform.models.api import PublicTenantResponse
from civilai_platform.models.entities import TenantStatus
from civilai_platform.services import artifacts as artifact_svc
from civilai_platform.store.base import PlatformStore

router = APIRouter(prefix="/v1/public", tags=["public"])


@router.get("/tenants/{url_slug}", response_model=PublicTenantResponse)
def get_public_tenant(
    url_slug: str,
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> PublicTenantResponse:
    tenant = store.get_tenant_by_slug(url_slug)
    if not tenant or tenant.status != TenantStatus.ACTIVE:
        raise HTTPException(404, "Tenant not found")
    return PublicTenantResponse(
        tenant_id=tenant.tenant_id,
        name=tenant.name,
        url_slug=tenant.url_slug,
        logo_url=artifact_svc.tenant_logo_url(tenant.logo_s3_key),
    )


@router.get("/artifacts/{token}")
def get_public_artifact(token: str) -> Response:
    """Unauthenticated short-lived download used by Microsoft Office Online viewer."""
    key = artifact_svc.resolve_preview_token(token)
    if not key:
        raise HTTPException(404, "Preview link expired or not found")
    data = artifact_svc.download_artifact_bytes(key)
    if not data:
        raise HTTPException(404, "Artifact not found")
    filename = key.rsplit("/", 1)[-1]
    return Response(
        content=data,
        media_type=artifact_svc.artifact_media_type(key),
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
