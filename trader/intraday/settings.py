"""Strategy constants of the intraday account, frozen for its validation period.

The daily account's constants stay in ``trader.settings``; only what differs is
here. Machine settings (paths, capital, prices, Telegram) come from
``trader.settings.Settings`` for both accounts.
"""

from __future__ import annotations

# A full position unit loses RISK_PER_UNIT of equity when its stop, STOP_ATR_MULT
# hourly ATRs from entry, is hit. Half the daily account's risk: there are many
# more decisions a day.
RISK_PER_UNIT = 0.01
STOP_ATR_MULT = 2.5
ATR_BAR = "1H"   # OKX bar size the ATR is measured on
ATR_BARS = 14

# Target position per signal, in full position units. Symmetric: the intraday
# prompt is written for both sides (ADR 0006). A missing signal (None: the call
# failed or gave no usable answer) keeps the current position.
WEIGHTS = {"Long": 1.0, "Short": -1.0, "Flat": 0.0}

# Trades smaller than this many full units are skipped; wider than the daily
# account's, since the unit is re-measured every hour.
REBALANCE_THRESHOLD = 0.25

# What the hourly decision looks at.
SIGNAL_BAR = "15m"   # OKX bar size of the candles in the prompt
SIGNAL_HOURS = 24    # hours of those candles

DECISION_MINUTE = 3  # the job runs at this minute of every hour (UTC)
