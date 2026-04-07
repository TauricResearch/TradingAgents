"""Default configuration for Trading Agents ADK.

Mirrors the original DEFAULT_CONFIG but adapted for Google ADK.
"""

import os

DEFAULT_CONFIG = {
    # Model configuration
    "quick_model": "gemini-2.5-flash",        # Fast model for analysts, researchers, trader
    "deep_model": "gemini-2.5-pro",            # Deep model for managers (research mgr, portfolio mgr)

    # Pipeline configuration
    "selected_analysts": ["market", "fundamentals", "news"],
    "max_debate_rounds": 1,          # Bull/Bear debate rounds
    "max_risk_rounds": 1,            # Risk debate rounds

    # Debug
    "debug": False,
}
