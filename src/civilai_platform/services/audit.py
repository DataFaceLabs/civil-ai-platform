from civilai_platform.auth.context import AuthContext
from civilai_platform.auth.actor import tenant_actor_user_id, tenant_audit_detail
from civilai_platform.models.entities import AuditEvent, new_id, utc_now
from civilai_platform.store import get_store


def record_audit(
    *,
    tenant_id: str,
    actor_user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        event_id=new_id(),
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail or {},
        created_at=utc_now(),
    )
    get_store().put_audit_event(event)
    return event


def record_audit_for_ctx(
    ctx: AuthContext,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict | None = None,
) -> AuditEvent:
    store = get_store()
    assert ctx.tenant_id
    return record_audit(
        tenant_id=ctx.tenant_id,
        actor_user_id=tenant_actor_user_id(store, ctx),
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=tenant_audit_detail(store, ctx, detail),
    )
