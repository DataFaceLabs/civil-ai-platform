import json
from typing import Any
from urllib.request import urlopen

from jose import JWTError, jwt

from civilai_platform.settings import get_settings


class AuthError(Exception):
    def __init__(self, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.status = status


_jwks_cache: dict[str, Any] | None = None

TRUST_REVIEWER_GROUP = "trust-reviewer"


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


def allowed_cognito_client_ids() -> set[str]:
    """Product web client + optional Trust Console Hosted UI client."""
    settings = get_settings()
    ids: set[str] = set()
    if settings.cognito_app_client_id:
        ids.add(settings.cognito_app_client_id)
    if settings.cognito_trust_app_client_id:
        ids.add(settings.cognito_trust_app_client_id)
    return ids


def token_client_id(claims: dict[str, Any]) -> str | None:
    """Cognito access tokens use ``client_id``; ID tokens use ``aud``."""
    raw = claims.get("client_id") or claims.get("aud")
    if isinstance(raw, list):
        return str(raw[0]) if raw else None
    if raw is None:
        return None
    return str(raw)


def groups_from_claims(claims: dict[str, Any]) -> tuple[str, ...]:
    raw = claims.get("cognito:groups") or claims.get("groups") or ()
    if isinstance(raw, str):
        return (raw,) if raw else ()
    return tuple(str(g) for g in raw)


def validate_cognito_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    allowed = allowed_cognito_client_ids()
    if not settings.cognito_user_pool_id or not allowed:
        raise AuthError("Cognito not configured", 500)
    try:
        headers = jwt.get_unverified_header(token)
        jwks = _get_jwks()
        key = next((k for k in jwks["keys"] if k["kid"] == headers.get("kid")), None)
        if not key:
            raise AuthError("Invalid token key")
        # Access tokens omit ``aud`` and carry ``client_id`` instead — verify manually.
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=(
                f"https://cognito-idp.{settings.aws_region}.amazonaws.com/"
                f"{settings.cognito_user_pool_id}"
            ),
            options={"verify_aud": False},
        )
        client_id = token_client_id(claims)
        if not client_id or client_id not in allowed:
            raise AuthError("Invalid token audience")
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
