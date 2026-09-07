"""Vietnam Swing Trading 3-Agent Minimalist Architecture.

Consists of:
1. RegimeAgent: Evaluates market health (VN-Index > MA20, distribution days) -> Traffic light (Green/Yellow/Red).
2. SetupAgent: Technical stock screener for VCP (Volatility Contraction Pattern), Base Breakout, and Volume Dry-Up.
3. RiskAgent: Sizing (100-share lot, max NAV risk), T+2.5 settlement tracking, and stop-loss / trailing stop rules.
"""

from .regime_agent import MarketRegimeResult, RegimeAgent, RegimeStatus
from .risk_agent import ExitAction, ExitSignal, PortfolioPosition, RiskAgent, TPlusStatus
from .setup_agent import SetupAgent, SetupResult, SetupStatus

__all__ = [
    "ExitAction",
    "ExitSignal",
    "MarketRegimeResult",
    "PortfolioPosition",
    "RegimeAgent",
    "RegimeStatus",
    "RiskAgent",
    "SetupAgent",
    "SetupResult",
    "SetupStatus",
    "TPlusStatus",
]
