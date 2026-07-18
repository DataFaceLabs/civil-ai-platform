import json
from typing import Any
from urllib.request import urlopen

from jose import JWTError, jwt

from civilai_platform.auth.context import AuthContext
from civilai_platform.settings import get_settings


class AuthError(Exception):
    def __init__(self, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.status = status


_jwks_cache: dict[str, Any] | None = None


def _get_jwks() -> dict[str, Any]:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    settings = get_settings()
    if not settings.cognito_user_pool_id:
        raise AuthError("Cognito not configured", 500)
    region = settings.aws_region
    url = (
        f"https://cognito-idp.{region}.amazonaws.com/"
        f"{settings.cognito_user_pool_id}/.well-known/jwks.json"
    )
    with urlopen(url, timeout=5) as resp:
        _jwks_cache = json.loads(resp.read().decode())
    return _jwks_cache


def validate_cognito_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.cognito_user_pool_id or not settings.cognito_app_client_id:
        raise AuthError("Cognito not configured", 500)
    try:
        headers = jwt.get_unverified_header(token)
        jwks = _get_jwks()
        key = next((k for k in jwks["keys"] if k["kid"] == headers.get("kid")), None)
        if not key:
            raise AuthError("Invalid token key")
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.cognito_app_client_id,
            issuer=f"https://cognito-idp.{settings.aws_region}.amazonaws.com/{settings.cognito_user_pool_id}",
        )
        return claims
    except JWTError as exc:
        raise AuthError("Invalid token") from exc


def parse_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None
