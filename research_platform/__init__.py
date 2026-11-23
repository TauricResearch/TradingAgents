"""A research platform on top of TradingAgents: watchlist runs, a signal scorecard,
a paper portfolio and a local dashboard.

Research and study only. Nothing here connects to a broker or places an order: the
paper portfolio is a simulation over historical closes, and every figure it reports
is computed in Python from recorded decisions and prices, never by the model.
"""

__all__ = ["config", "store", "watchlist", "scorecard", "paper"]
