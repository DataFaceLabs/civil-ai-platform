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
