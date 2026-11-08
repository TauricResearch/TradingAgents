"""Frozen BRK-B regression fixture — the 2026-11-08 report case.

This module is the single source of truth for the temporal facts of the
regression case described in
``docs/specs/TRADINGAGENTS_RELIABILITY_CONTRACT.md`` (section 1, DEF-001/002
and section 9, tests 1, 2 and 16). Every test that needs the BRK-B timeline
imports these constants instead of restating dates, so a wrong date cannot
silently disagree between tests.

Timeline (all dates US/Eastern unless noted):

- Friday 2026-11-06: last completed XNYS session before the report. Close
  570.89 USD (BRK-B), prior close 572.33 USD — a -0.25% move, not -0.01%.
- Saturday 2026-11-07: Berkshire publishes Q3 2026 results. Markets are
  closed; no price can react to the release on this date.
- Sunday 2026-11-08: the report is generated. The next XNYS session
  (Monday 2026-11-09) has not happened yet, so no post-event price exists.

The fixture is data only: no network, no LLM, no live prices. Values that the
original report asserted (close, prior close, ATR, tranche/stop levels) are
recorded here as the *claims under test*, not as verified market data.
"""

from __future__ import annotations

from datetime import UTC, datetime

# --- Ticker identity (DEF-006 share-class hazard) ---------------------------
TICKER = "BRK-B"
# Berkshire Hathaway class A / class B conversion: 1 A share = 1500 B shares.
BRK_A_TO_B_RATIO = 1500

# --- Market calendar (XNYS, America/New_York) -------------------------------
LAST_SESSION_DATE = "2026-11-06"          # Friday: last completed session
EVENT_PUBLICATION_DATE = "2026-11-07"     # Saturday: Q3 release, market closed
REPORT_RUN_DATE = "2026-11-08"            # Sunday: report generated
NEXT_SESSION_DATE = "2026-11-09"          # Monday: first session after the event

# --- Prices as claimed by the original report -------------------------------
CLOSE_LAST_SESSION = 570.89   # Friday 2026-11-06 close (BRK-B)
CLOSE_PRIOR_SESSION = 572.33  # Thursday 2026-11-05 close (BRK-B)

# --- Event ------------------------------------------------------------------
EVENT_PERIOD = "2026-Q3"
EVENT_PERIOD_END = "2026-09-30"
# The release time of day is not verified by this fixture; the date is.
EVENT_PUBLISHED_AT = None  # unknown: must stay unknown until verified

# --- Risk plan as claimed by the original report (DEF-004) ------------------
TRANCHE_3_ENTRY = 543.70
STOP_LOSS = 543.50
ATR_14 = 9.408
# Contract's minimum entry-to-stop buffer, in ATR units (section 5).
MIN_ENTRY_STOP_ATR = 0.5

# --- Derived, deterministic helpers -----------------------------------------


def last_session_close_dt() -> datetime:
    """Friday 2026-11-06 16:00 US/Eastern == 21:00 UTC (EST, UTC-5 in November)."""
    return datetime(2026, 11, 6, 21, 0, tzinfo=UTC)


def event_publication_dt() -> datetime:
    """Saturday 2026-11-07: the release exists sometime this day (UTC date)."""
    return datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def report_run_dt() -> datetime:
    """Sunday 2026-11-08: the report is generated (UTC date)."""
    return datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def price_move_pct() -> float:
    """Friday's close-to-close move: (570.89 - 572.33) / 572.33 * 100.

    The original report called this -0.01%; the true value is about -0.25%.
    """
    return (CLOSE_LAST_SESSION - CLOSE_PRIOR_SESSION) / CLOSE_PRIOR_SESSION * 100


def entry_stop_distance() -> float:
    """Absolute distance between the third tranche entry and the stop."""
    return TRANCHE_3_ENTRY - STOP_LOSS


def entry_stop_atr_multiple() -> float:
    """Entry-to-stop distance expressed in ATR units.

    For the regression case this is ~0.021 ATR, far below the 0.5 ATR
    minimum buffer the contract requires (section 5).
    """
    return entry_stop_distance() / ATR_14
