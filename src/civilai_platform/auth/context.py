from dataclasses import dataclass

from civilai_platform.models.entities import Role


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    email: str
    tenant_id: str | None = None
    role: Role | None = None
    is_platform_admin: bool = False
