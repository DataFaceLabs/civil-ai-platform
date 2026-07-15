"""Cognito user provisioning — no-op in dev when pool is not configured."""

from __future__ import annotations

import logging
import secrets
import string
from typing import Any

from civilai_platform.settings import get_settings

logger = logging.getLogger(__name__)


class CognitoProvisionError(RuntimeError):
    """Raised when Cognito rejects a provision/reinvite that cannot be recovered."""


def generate_temporary_password(*, length: int = 16) -> str:
    """Generate a Cognito-compatible temporary password.

    Policy (UAT pool): min 10, upper, lower, number; symbols not required.
    Avoid ambiguous punctuation so admins can read/copy it reliably.
    """
    if length < 10:
        raise ValueError("temporary password length must be >= 10")
    alphabet = string.ascii_letters + string.digits
    while True:
        chars = [
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.digits),
            *[secrets.choice(alphabet) for _ in range(length - 3)],
        ]
        secrets.SystemRandom().shuffle(chars)
        password = "".join(chars)
        if (
            any(c.isupper() for c in password)
            and any(c.islower() for c in password)
            and any(c.isdigit() for c in password)
        ):
            return password


def _is_username_exists(exc: BaseException) -> bool:
    name = type(exc).__name__
    return "UsernameExistsException" in name or "UsernameExistsException" in str(exc)


def _attr_map(attributes: list[dict[str, str]]) -> dict[str, str]:
    return {item["Name"]: item["Value"] for item in attributes}


class CognitoProvisioner:
    def __init__(self) -> None:
        settings = get_settings()
        self._pool_id = settings.cognito_user_pool_id
        self._client: Any | None = None
        if self._pool_id:
            import boto3

            self._client = boto3.client("cognito-idp", region_name=settings.aws_region)

    def provision_user(
        self,
        *,
        email: str,
        first_name: str,
        last_name: str,
        password: str | None = None,
        invite: bool = True,
    ) -> tuple[str | None, str | None]:
        """Create Cognito user when pool is configured.

        Returns ``(cognito_sub_or_username, temporary_password)``.
        ``temporary_password`` is the one-time password Cognito will accept on
        first login (FORCE_CHANGE_PASSWORD). Callers should surface it to the
        inviting admin when email delivery may fail (e.g. SES sandbox).

        If the email already exists (common after tenant delete, which disables
        rather than deletes the Cognito user), re-enable the account, rotate the
        temporary password, and return the existing ``sub``.
        """
        if not self._client or not self._pool_id:
            return None, None
        temp_password = password or generate_temporary_password()
        params: dict[str, Any] = {
            "UserPoolId": self._pool_id,
            "Username": email,
            "UserAttributes": [
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "given_name", "Value": first_name},
                {"Name": "family_name", "Value": last_name},
            ],
            "TemporaryPassword": temp_password,
        }
        if invite and not password:
            # Still attempt Cognito invite email (works for SES-verified recipients
            # while the account remains in the SES sandbox).
            params["DesiredDeliveryMediums"] = ["EMAIL"]
        else:
            params["MessageAction"] = "SUPPRESS"
        try:
            resp = self._client.admin_create_user(**params)
        except Exception as exc:  # noqa: BLE001 — botocore exception types vary
            if _is_username_exists(exc):
                return self.reinvite_existing_user(
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    temporary_password=temp_password,
                    send_email=bool(invite and not password),
                )
            raise CognitoProvisionError(str(exc)) from exc
        for attr in resp["User"].get("Attributes", []):
            if attr["Name"] == "sub":
                return attr["Value"], temp_password
        return resp["User"]["Username"], temp_password

    def reinvite_existing_user(
        self,
        *,
        email: str,
        first_name: str,
        last_name: str,
        temporary_password: str | None = None,
        send_email: bool = True,
    ) -> tuple[str, str]:
        """Re-enable a disabled Cognito user and issue a fresh temporary password.

        Used when re-inviting someone who was removed from a tenant (delete disables
        Cognito but leaves the account) or when AdminCreateUser hits UsernameExists.
        """
        if not self._client or not self._pool_id:
            raise CognitoProvisionError("Cognito user pool is not configured")
        temp_password = temporary_password or generate_temporary_password()
        try:
            self._client.admin_enable_user(UserPoolId=self._pool_id, Username=email)
        except Exception as exc:  # noqa: BLE001
            if "UserNotFoundException" not in type(exc).__name__ and "UserNotFoundException" not in str(
                exc
            ):
                raise CognitoProvisionError(str(exc)) from exc
            raise CognitoProvisionError(f"Cognito user not found for {email}") from exc

        self._client.admin_update_user_attributes(
            UserPoolId=self._pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "given_name", "Value": first_name},
                {"Name": "family_name", "Value": last_name},
            ],
        )
        self._client.admin_set_user_password(
            UserPoolId=self._pool_id,
            Username=email,
            Password=temp_password,
            Permanent=False,
        )
        if send_email:
            # Best-effort invite email. Delivery failures must not block the invite —
            # the admin still receives temporary_password in the API response.
            try:
                self._client.admin_create_user(
                    UserPoolId=self._pool_id,
                    Username=email,
                    MessageAction="RESEND",
                    TemporaryPassword=temp_password,
                    DesiredDeliveryMediums=["EMAIL"],
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cognito invite email resend failed for %s: %s", email, exc)

        sub = self.get_user_sub(email)
        if not sub:
            raise CognitoProvisionError(f"Could not resolve Cognito sub for {email}")
        return sub, temp_password

    def get_user_sub(self, email: str) -> str | None:
        """Return Cognito ``sub`` for an email username, or None if missing."""
        if not self._client or not self._pool_id:
            return None
        try:
            resp = self._client.admin_get_user(UserPoolId=self._pool_id, Username=email)
        except Exception as exc:  # noqa: BLE001
            if "UserNotFoundException" in type(exc).__name__ or "UserNotFoundException" in str(exc):
                return None
            raise
        attrs = _attr_map(resp.get("UserAttributes", []))
        return attrs.get("sub") or resp.get("Username")

    def resend_invite(self, *, email: str, temporary_password: str | None = None) -> str:
        """Resend the Cognito invitation email with a (new) temporary password."""
        if not self._client or not self._pool_id:
            raise RuntimeError("Cognito user pool is not configured")
        temp_password = temporary_password or generate_temporary_password()
        self._client.admin_create_user(
            UserPoolId=self._pool_id,
            Username=email,
            MessageAction="RESEND",
            TemporaryPassword=temp_password,
            DesiredDeliveryMediums=["EMAIL"],
        )
        return temp_password

    def disable_user(self, *, email: str) -> None:
        if not self._client or not self._pool_id:
            return
        try:
            self._client.admin_disable_user(UserPoolId=self._pool_id, Username=email)
        except self._client.exceptions.UserNotFoundException:
            return
        except Exception as exc:  # noqa: BLE001 — Cognito client errors vary by botocore version
            # Race: user may not be queryable immediately after admin_create_user.
            if "UserNotFoundException" in type(exc).__name__ or "UserNotFoundException" in str(exc):
                return
            raise

    def delete_user(self, *, email: str) -> None:
        if not self._client or not self._pool_id:
            return
        try:
            self._client.admin_delete_user(UserPoolId=self._pool_id, Username=email)
        except self._client.exceptions.UserNotFoundException:
            return
        except Exception as exc:  # noqa: BLE001
            if "UserNotFoundException" in type(exc).__name__ or "UserNotFoundException" in str(exc):
                return
            raise


_provisioner: CognitoProvisioner | None = None


def get_cognito_provisioner() -> CognitoProvisioner:
    global _provisioner
    if _provisioner is None:
        _provisioner = CognitoProvisioner()
    return _provisioner
