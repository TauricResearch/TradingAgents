from .analysis import router as analysis_router
from .history import router as history_router
from .config import router as config_router

__all__ = ["analysis_router", "history_router", "config_router"]

