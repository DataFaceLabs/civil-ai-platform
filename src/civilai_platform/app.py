from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from civilai_platform.api.router import api_router
from civilai_platform.auth.jwt import AuthError
from civilai_platform.services import platform_tenant as platform_tenant_svc
from civilai_platform.settings import get_settings
from civilai_platform.store import get_store

# Any localhost port — covers Vite (5173/3000), Lovable sandbox (8080/8081), etc.
_LOCALHOST_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"


def _git_sha() -> str:
    """The commit scripts/package-lambda.sh zipped, or "unknown" if absent.

    H3-DRIFT: baked into the deployment zip at package time (not a Terraform
    env var -- see package-lambda.sh for why), so deploy-uat.sh status can
    compare what's actually running against origin/main without console/API
    access to Lambda's own configuration.
    """
    sha_file = Path(__file__).with_name("_git_sha.txt")
    try:
        return sha_file.read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        return "unknown"


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.dev_auth and settings.environment not in {"dev", "local", "test"}:
        raise RuntimeError("CIVILAI_DEV_AUTH must not be enabled outside dev/local/test")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        store = get_store()
        platform_tenant_svc.ensure_platform_tenant(store)
        platform_tenant_svc.backfill_platform_admin_memberships(store)
        yield

    app = FastAPI(
        title="Civil AI Platform API",
        version="0.1.0-dev",
        description="Tenant, user, client, and project persistence control plane.",
        lifespan=lifespan,
    )

    @app.exception_handler(AuthError)
    async def auth_error_handler(_request: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"detail": str(exc)})

    cors_kwargs: dict = {
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }
    if settings.dev_auth:
        cors_kwargs["allow_origin_regex"] = _LOCALHOST_ORIGIN_REGEX
    else:
        cors_kwargs["allow_origins"] = settings.cors_origins
    app.add_middleware(CORSMiddleware, **cors_kwargs)
    app.include_router(api_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "civilai-platform", "git_sha": _git_sha()}

    return app
