from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from civilai_platform.api.deps import get_store_dep, tenant_ctx
from civilai_platform.auth.authz import require_membership
from civilai_platform.auth.context import AuthContext
from civilai_platform.models.api import ClientCreate, ClientResponse, ClientUpdate
from civilai_platform.models.entities import Role
from civilai_platform.services import client as client_svc
from civilai_platform.store.base import PlatformStore

router = APIRouter(prefix="/v1/clients", tags=["clients"])


def _member_ctx(ctx: Annotated[AuthContext, Depends(tenant_ctx)]) -> AuthContext:
    require_membership(ctx, Role.VIEWER)
    return ctx


def _writer_ctx(ctx: Annotated[AuthContext, Depends(tenant_ctx)]) -> AuthContext:
    require_membership(ctx, Role.ANALYST)
    return ctx


@router.get("", response_model=list[ClientResponse])
def list_clients(
    ctx: Annotated[AuthContext, Depends(_member_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> list[ClientResponse]:
    assert ctx.tenant_id
    return client_svc.list_clients(store, ctx.tenant_id)


@router.post("", response_model=ClientResponse, status_code=201)
def create_client(
    body: ClientCreate,
    ctx: Annotated[AuthContext, Depends(_writer_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> ClientResponse:
    assert ctx.tenant_id
    return client_svc.create_client(
        store,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        data=body,
    )


@router.get("/{client_id}", response_model=ClientResponse)
def get_client(
    client_id: str,
    ctx: Annotated[AuthContext, Depends(_member_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> ClientResponse:
    assert ctx.tenant_id
    client = store.get_client(ctx.tenant_id, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    return ClientResponse.from_entity(client)


@router.patch("/{client_id}", response_model=ClientResponse)
def patch_client(
    client_id: str,
    body: ClientUpdate,
    ctx: Annotated[AuthContext, Depends(_writer_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> ClientResponse:
    assert ctx.tenant_id
    try:
        return client_svc.update_client(
            store,
            tenant_id=ctx.tenant_id,
            client_id=client_id,
            actor_user_id=ctx.user_id,
            data=body,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/{client_id}", status_code=204)
def delete_client(
    client_id: str,
    ctx: Annotated[AuthContext, Depends(_writer_ctx)],
    store: Annotated[PlatformStore, Depends(get_store_dep)],
) -> None:
    assert ctx.tenant_id
    try:
        client_svc.delete_client(
            store,
            tenant_id=ctx.tenant_id,
            client_id=client_id,
            actor_user_id=ctx.user_id,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
