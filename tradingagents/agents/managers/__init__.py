"""Manager agents for portfolio and risk management.

This module provides manager agents for orchestrating research and risk:
- Research Manager: Coordinates research activities
- Risk Manager: Manages risk assessment
- Position Sizing Manager: Optimal position sizing (Issue #16)
"""

from .research_manager import create_research_manager
from .risk_manager import create_risk_manager
from .position_sizing_manager import create_position_sizing_manager

__all__ = [
    "create_research_manager",
    "create_risk_manager",
    "create_position_sizing_manager",
]
