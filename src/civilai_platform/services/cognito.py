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
    ) -> str | None:
        """Create Cognito user when pool is configured; return Cognito sub or None."""
        if not self._client or not self._pool_id:
            return None
        temp_password = password or "ChangeMe-123!"
        resp = self._client.admin_create_user(
            UserPoolId=self._pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "given_name", "Value": first_name},
                {"Name": "family_name", "Value": last_name},
            ],
            TemporaryPassword=temp_password,
            MessageAction="SUPPRESS",
        )
        for attr in resp["User"].get("Attributes", []):
            if attr["Name"] == "sub":
                return attr["Value"]
        return resp["User"]["Username"]


_provisioner: CognitoProvisioner | None = None


def get_cognito_provisioner() -> CognitoProvisioner:
    global _provisioner
    if _provisioner is None:
        _provisioner = CognitoProvisioner()
    return _provisioner
