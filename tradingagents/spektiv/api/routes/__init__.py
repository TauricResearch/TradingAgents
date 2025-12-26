"""API routes."""

from spektiv.api.routes.auth import router as auth_router
from spektiv.api.routes.strategies import router as strategies_router

__all__ = ["auth_router", "strategies_router"]
