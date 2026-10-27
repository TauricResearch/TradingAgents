"""Brokerage adapters that feed TradingAgents PortfolioContext.

Official TradingAgents is broker-neutral. The agentRobin adapter loads paper
(FakeBroker) and live (Schwab / Alpaca / Robinhood) books through agentRobin's
internal bridge (ROBIN-1689).
"""

from tradingagents.brokerages.agentrobin import (
    AgentRobinBridgeError,
    fetch_portfolio,
    list_accounts,
    place_equity_order,
)

__all__ = [
    "AgentRobinBridgeError",
    "fetch_portfolio",
    "list_accounts",
    "place_equity_order",
]
