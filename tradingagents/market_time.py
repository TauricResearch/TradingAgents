"""US equity market calendar helpers (timezone-aware "today").

The site queue and the CLI must agree on which calendar day is current.
Host ``date.today()`` follows the machine TZ (often America/Los_Angeles on
shimazu), while US equity sessions are dated in America/New_York. Between
00:00 ET and midnight PT the NY date is one day ahead of local ``date.today()``,
which made site ``--date`` fail with "is in the future".
"""

from __future__ import annotations

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo


def market_tz() -> ZoneInfo:
    return ZoneInfo(os.environ.get("TRADINGAGENTS_MARKET_TZ", "America/New_York"))


def market_today() -> date:
    """Today on the US equity calendar (default America/New_York)."""
    return datetime.now(market_tz()).date()


def market_today_iso() -> str:
    return market_today().isoformat()
