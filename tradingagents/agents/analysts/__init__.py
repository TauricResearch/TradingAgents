"""Analyst agents for market analysis.

This module provides specialized analyst agents for different types of analysis:
- Fundamentals Analyst: Company financial analysis
- Market Analyst: Technical and market structure analysis
- News Analyst: News sentiment and event analysis
- Social Media Analyst: Social sentiment analysis
- Momentum Analyst: Multi-timeframe momentum analysis (Issue #13)
- Macro Analyst: Macroeconomic and FRED data analysis (Issue #14)
- Correlation Analyst: Cross-asset correlation and sector rotation (Issue #15)
"""

from .fundamentals_analyst import create_fundamentals_analyst
from .market_analyst import create_market_analyst
from .news_analyst import create_news_analyst
from .social_media_analyst import create_social_media_analyst
from .momentum_analyst import create_momentum_analyst
from .macro_analyst import create_macro_analyst
from .correlation_analyst import create_correlation_analyst

__all__ = [
    "create_fundamentals_analyst",
    "create_market_analyst",
    "create_news_analyst",
    "create_social_media_analyst",
    "create_momentum_analyst",
    "create_macro_analyst",
    "create_correlation_analyst",
]
