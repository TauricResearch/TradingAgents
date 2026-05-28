"""Mock trading system for TradingAgents."""

from .database import TradingDatabase
from .portfolio_manager import PortfolioManager
from .order_manager import OrderManager, PriceType, OrderStatus
from .corporate_actions import CorporateActionsHandler, CorporateActionType
from .async_analyzer import AsyncAnalyzer, AnalysisStatus
from .reward_calculator import RewardCalculator, RewardType
from .decision_maker import AIDecisionMaker
from .scheduler import TradingScheduler, TradingSession
from .dashboard import PerformanceDashboard
from .hindsight_rl import HindsightRLDatasetBuilder

try:
    from .benchmark_tracker import BenchmarkTracker, PerformanceComparison
except ImportError:
    BenchmarkTracker = None
    PerformanceComparison = None

# Lazy import MockTradingEngine to avoid yfinance dependency issues
try:
    from .engine import MockTradingEngine
except ImportError:
    MockTradingEngine = None

__all__ = [
    "TradingDatabase",
    "MockTradingEngine",
    "PortfolioManager",
    "OrderManager",
    "PriceType",
    "OrderStatus",
    "CorporateActionsHandler",
    "CorporateActionType",
    "AsyncAnalyzer",
    "AnalysisStatus",
    "RewardCalculator",
    "RewardType",
    "AIDecisionMaker",
    "TradingScheduler",
    "TradingSession",
    "BenchmarkTracker",
    "PerformanceComparison",
    "PerformanceDashboard",
    "HindsightRLDatasetBuilder",
]
