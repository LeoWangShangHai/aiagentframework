from fastapi import APIRouter

from app.api.routes.agent import router as agent_router
from app.api.routes.health import router as health_router
from app.api.routes.hello import router as hello_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(hello_router, tags=["hello"])
api_router.include_router(agent_router, tags=["agent-framework"])
