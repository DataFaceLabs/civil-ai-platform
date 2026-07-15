"""Cognito user provisioning — no-op in dev when pool is not configured."""

from __future__ import annotations

import secrets
import string

from civilai_platform.settings import get_settings


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


class CognitoProvisioner:
    def __init__(self) -> None:
        settings = get_settings()
        self._pool_id = settings.cognito_user_pool_id
        self._client = None
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
        """
        if not self._client or not self._pool_id:
            return None, None
        temp_password = password or generate_temporary_password()
        params: dict = {
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
        resp = self._client.admin_create_user(**params)
        for attr in resp["User"].get("Attributes", []):
            if attr["Name"] == "sub":
                return attr["Value"], temp_password
        return resp["User"]["Username"], temp_password

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
