"""Zoning Topic Hydrate routes (Slice 2)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from civilai_platform.api.deps import get_store_dep, tenant_ctx
from civilai_platform.auth.context import AuthContext
from civilai_platform.models.topic_brief import ZoningBriefRequest, ZoningBriefResponse
from civilai_platform.services.data_proxy import DataProxyClient
from civilai_platform.services.data_routing import data_api_base_for_request
from civilai_platform.services import topic_brief as topic_brief_svc
from civilai_platform.store.base import PlatformStore

router = APIRouter(tags=["zoning"])


@router.post("/v1/zoning/brief", response_model=ZoningBriefResponse)
def zoning_brief(
    request: Request,
    body: ZoningBriefRequest,
    ctx: Annotated[AuthContext, Depends(tenant_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> ZoningBriefResponse:
    _ = ctx
    client = DataProxyClient(base_url=data_api_base_for_request(request))
    return topic_brief_svc.build_zoning_briefs(store, body, data_client=client)
