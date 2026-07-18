"""Tenant permanent deletion with email authorization."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from civilai_platform.services.cognito import get_cognito_provisioner
from civilai_platform.settings import get_settings
from civilai_platform.store.base import PlatformStore

logger = logging.getLogger(__name__)

_CODE_TTL = timedelta(minutes=15)


@dataclass
class _PendingPurge:
    tenant_id: str
    actor_user_id: str
    actor_email: str
    code: str
    expires_at: datetime


_pending: dict[str, _PendingPurge] = {}


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def request_tenant_purge(
    store: PlatformStore,
    *,
    tenant_id: str,
    actor_user_id: str,
    actor_email: str,
) -> dict[str, str]:
    from civilai_platform.services.platform_tenant import is_platform_tenant_id

    if is_platform_tenant_id(store, tenant_id):
        raise ValueError("The Platform tenant cannot be deleted")
    if not store.get_tenant(tenant_id):
        raise ValueError("Tenant not found")
    code = f"{secrets.randbelow(1_000_000):06d}"
    _pending[tenant_id] = _PendingPurge(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_email=_normalize_email(actor_email),
        code=code,
        expires_at=datetime.now(UTC) + _CODE_TTL,
    )
    settings = get_settings()
    if settings.dev_auth:
        logger.info(
            "Dev tenant purge authorization for %s: code=%s actor=%s",
            tenant_id,
            code,
            actor_email,
        )
        return {
            "message": "Authorization code generated (dev mode).",
            "authorization_code": code,
        }
    # Production: integrate SES / Cognito custom message delivery here.
    logger.info("Tenant purge authorization requested for %s; email=%s", tenant_id, actor_email)
    return {"message": f"Authorization code sent to {actor_email}."}


def confirm_tenant_purge(
    store: PlatformStore,
    *,
    tenant_id: str,
    actor_user_id: str,
    actor_email: str,
    authorization_code: str,
) -> list[str]:
    pending = _pending.get(tenant_id)
    if not pending:
        raise ValueError("No pending purge authorization for this tenant")
    if pending.actor_user_id != actor_user_id:
        raise ValueError("Unauthorized purge attempt")
    if pending.expires_at < datetime.now(UTC):
        _pending.pop(tenant_id, None)
        raise ValueError("Authorization code expired")
    if _normalize_email(actor_email) != pending.actor_email:
        raise ValueError("Confirmation email does not match authorized account")
    if authorization_code.strip() != pending.code:
        raise ValueError("Invalid authorization code")

    _pending.pop(tenant_id, None)
    user_ids = [m.user_id for m in store.list_memberships_for_tenant(tenant_id)]
    emails: list[str] = []
    for user_id in user_ids:
        profile = store.get_user_profile(user_id)
        if profile:
            emails.append(profile.email)
    store.purge_tenant_data(tenant_id)
    provisioner = get_cognito_provisioner()
    for email in emails:
        provisioner.delete_user(email=email)
    return user_ids
