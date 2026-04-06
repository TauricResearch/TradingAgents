"""Discovery scanners for modular pipeline architecture."""

# Import all scanners to trigger registration
from . import (
    analyst_upgrades,  # noqa: F401
    earnings_calendar,  # noqa: F401
    insider_buying,  # noqa: F401
    market_movers,  # noqa: F401
    minervini,  # noqa: F401
    ml_signal,  # noqa: F401
    options_flow,  # noqa: F401
    reddit_dd,  # noqa: F401
    reddit_trending,  # noqa: F401
    sector_rotation,  # noqa: F401
    semantic_news,  # noqa: F401
    technical_breakout,  # noqa: F401
    volume_accumulation,  # noqa: F401
)
