from fastapi import APIRouter

from civilai_platform.api.routes import agent_runs, clients, core, projects, users

api_router = APIRouter()
api_router.include_router(core.router)
api_router.include_router(users.router)
api_router.include_router(clients.router)
api_router.include_router(projects.router)
api_router.include_router(agent_runs.router)
