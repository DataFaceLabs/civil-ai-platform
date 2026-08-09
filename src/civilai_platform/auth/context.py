from dataclasses import dataclass, field

from civilai_platform.models.entities import Role


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    email: str
    tenant_id: str | None = None
    role: Role | None = None
    is_platform_admin: bool = False
    # Cognito groups from the access token (e.g. trust-reviewer). Empty in dev-auth
    # unless X-Dev-Cognito-Groups is set.
    cognito_groups: tuple[str, ...] = field(default_factory=tuple)
    # App client that issued the access token (product web vs Trust Hosted UI).
    cognito_client_id: str | None = None
