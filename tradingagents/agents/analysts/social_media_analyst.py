"""Backwards-compatibility shim for the renamed social_media_analyst module.

The social media analyst has been renamed to ``sentiment_analyst`` because its
only data tool is ``get_news`` (Yahoo Finance), not a social media feed.

Import from ``tradingagents.agents.analysts.sentiment_analyst`` going forward.

See: https://github.com/TauricResearch/TradingAgents/issues/557
"""

import warnings as _warnings

from tradingagents.agents.analysts.sentiment_analyst import (  # noqa: F401
    create_sentiment_analyst,
    create_social_media_analyst,
)

_warnings.warn(
    "tradingagents.agents.analysts.social_media_analyst is deprecated. "
    "Import from tradingagents.agents.analysts.sentiment_analyst instead.",
    DeprecationWarning,
    stacklevel=2,
)
