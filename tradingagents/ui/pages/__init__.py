"""
Dashboard page modules for the Trading Agents UI.

This package contains all page modules that can be rendered in the dashboard.
Each module should have a render() function that displays the page content.
"""

import logging

_logger = logging.getLogger(__name__)

try:
    from tradingagents.ui.pages import home
except Exception as _e:
    _logger.error("Failed to import home page: %s", _e, exc_info=True)
    home = None

try:
    from tradingagents.ui.pages import todays_picks
except Exception as _e:
    _logger.error("Failed to import todays_picks page: %s", _e, exc_info=True)
    todays_picks = None

try:
    from tradingagents.ui.pages import portfolio
except Exception as _e:
    _logger.error("Failed to import portfolio page: %s", _e, exc_info=True)
    portfolio = None

try:
    from tradingagents.ui.pages import performance
except Exception as _e:
    _logger.error("Failed to import performance page: %s", _e, exc_info=True)
    performance = None

try:
    from tradingagents.ui.pages import settings
except Exception as _e:
    _logger.error("Failed to import settings page: %s", _e, exc_info=True)
    settings = None

try:
    from tradingagents.ui.pages import hypotheses
except Exception as _e:
    _logger.error("Failed to import hypotheses page: %s", _e, exc_info=True)
    hypotheses = None


__all__ = [
    "home",
    "todays_picks",
    "portfolio",
    "performance",
    "settings",
    "hypotheses",
]
