"""Backwards-compatibility shim for the renamed module.

The agent is now ``sentiment_analyst`` and aggregates Yahoo Finance news,
StockTwits cashtag streams, and Reddit posts into a single sentiment
report. Import from ``handelsagenten.agents.analysts.sentiment_analyst``
going forward; this module will be removed in a future release.

See: https://github.com/TauricResearch/TradingAgents/issues/557
"""

import warnings as _warnings

from handelsagenten.agents.analysts.sentiment_analyst import (  # noqa: F401
    create_sentiment_analyst,
    create_social_media_analyst,
)

_warnings.warn(
    "handelsagenten.agents.analysts.social_media_analyst is deprecated. "
    "Import from handelsagenten.agents.analysts.sentiment_analyst instead.",
    DeprecationWarning,
    stacklevel=2,
)
