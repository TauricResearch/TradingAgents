"""Mock trading core — SQLite-backed order execution and portfolio management.

CLI-only modules (dashboard, hindsight_rl, scheduler, async_analyzer,
decision_maker, benchmark_tracker, reward_calculator) have been removed.
The web backend uses backend/services/mock_trading_service.py with
PostgreSQL instead.
"""

from .database import TradingDatabase
from .portfolio_manager import PortfolioManager
from .order_manager import OrderManager, PriceType, OrderStatus
from .corporate_actions import CorporateActionsHandler, CorporateActionType

try:
    from .engine import MockTradingEngine
except ImportError:
    MockTradingEngine = None  # type: ignore[assignment,misc]

__all__ = [
    "TradingDatabase",
    "MockTradingEngine",
    "PortfolioManager",
    "OrderManager",
    "PriceType",
    "OrderStatus",
    "CorporateActionsHandler",
    "CorporateActionType",
]
