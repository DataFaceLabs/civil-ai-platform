"""Cognito user provisioning — no-op in dev when pool is not configured."""

from civilai_platform.settings import get_settings


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
    ) -> str | None:
        """Create Cognito user when pool is configured; return Cognito sub or None."""
        if not self._client or not self._pool_id:
            return None
        temp_password = password or "ChangeMe-123!"
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
            params["DesiredDeliveryMediums"] = ["EMAIL"]
        else:
            params["MessageAction"] = "SUPPRESS"
        resp = self._client.admin_create_user(**params)
        for attr in resp["User"].get("Attributes", []):
            if attr["Name"] == "sub":
                return attr["Value"]
        return resp["User"]["Username"]

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
