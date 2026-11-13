"""How the demo account trades on the exchange (ADR 0008). Its sizing, stop and
rebalance constants are the intraday account's (``trader.intraday.settings``): the
demo makes the same decisions, only the fills are real."""

from __future__ import annotations

MARGIN_MODE = "cross"  # one margin pool, as the paper accounts size against total equity
LEVERAGE = 3           # the exchange's gate: the rules themselves stop at MAX_GROSS_EXPOSURE (2x)

RUN_MINUTE = 10               # the job runs at this minute of every hour (UTC); intraday decides at :03
INTRADAY_WAIT_MS = 15 * 60_000  # how long a run waits for the intraday account to decide the hour
INTRADAY_POLL_SECONDS = 60

ORDER_POLLS = 10         # how many times a placed market order is looked up before giving up
ORDER_POLL_SECONDS = 1.0
# Pause between close orders (a kill's, or a position closed for want of a stop) and
# the sync that books them.
KILL_SETTLE_SECONDS = 3.0
# How many such syncs a halt by hand waits through while each still sends closes: the
# sync after a close that failed sends it again.
HALT_SYNCS = 3

# A position left without a stop for its whole size: how many times the stop is placed
# before the position is closed at market instead, and the pause between the tries. The
# close itself is tried as often.
STOP_TRIES = 3
STOP_RETRY_SECONDS = 2.0

SYNC_OVERLAP_MS = 10 * 60_000  # each sync re-reads this far before the last one, deduplicating by bill id
# The exchange stamps fills and bills with its own clock, which can run seconds ahead of
# ours (the mini's was 1-3 s behind on 2026-11-10 and a sync cut off two fills it had
# just awaited): a sync reads this far past its own now. Overlap and bill ids cover the rest.
CLOCK_SKEW_MS = 60_000
ALERT_INTERVAL_MS = 6 * 3_600_000  # a failing run or a standing problem alerts at most this often

# Client order id prefixes: how a fill is attributed when it comes back from the exchange.
TRADE_PREFIX = "trd"
STOP_PREFIX = "stp"
KILL_PREFIX = "kil"
