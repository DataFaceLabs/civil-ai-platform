from fastapi import APIRouter

from civilai_platform.api.routes import clients, core, projects, users

api_router = APIRouter()
api_router.include_router(core.router)
api_router.include_router(users.router)
api_router.include_router(clients.router)
api_router.include_router(projects.router)
