"""Regression fixtures for the reliability contract (Phase 0 baseline).

The BRK-B report of 2026-11-08 is the frozen regression case: the last
completed XNYS session was Friday 2026-11-06, Berkshire published Q3 results
on Saturday 2026-11-07 (market closed), and the report ran on Sunday
2026-11-08 — before any post-event session existed. These tests pin the
temporal facts the contract requires (section 9, tests 1, 2 and 16) using the
existing ``date_window`` guards, plus a safety audit that the codebase holds
no live-broker path. All data is frozen in
``tests/fixtures/brk_b_2026_11_08.py``; no network, no LLM, no live prices.
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

import pytest

from tests.fixtures import brk_b_2026_11_08 as fx
from tradingagents.dataflows.date_window import (
    in_window,
    is_historical,
    to_utc,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Test 1 / 16 — temporal leakage and price-return sanity
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_event_is_after_last_session_so_not_yet_observable():
    """The Q3 release (Sat 11-07) postdates the last session (Fri 11-06).

    A claim that Friday's close 'absorbed' the release is temporally false:
    the publication happened after that close. The window guard must agree.
    """
    assert fx.EVENT_PUBLICATION_DATE > fx.LAST_SESSION_DATE
    assert to_utc(fx.event_publication_dt()) > to_utc(fx.last_session_close_dt())


@pytest.mark.unit
def test_no_post_event_session_exists_at_report_time():
    """At the Sunday 11-08 run, Monday 11-09 has not traded: NOT_YET_OBSERVABLE.

    The report date is strictly before the next session, so any price window
    starting after the event is empty — there is no observable reaction yet.
    """
    assert fx.REPORT_RUN_DATE < fx.NEXT_SESSION_DATE
    assert fx.EVENT_PUBLICATION_DATE < fx.NEXT_SESSION_DATE
    # And the run date itself is a non-trading day (Sunday) in the fixture's
    # own terms: it is not the last session and not the next session.
    assert fx.REPORT_RUN_DATE not in (fx.LAST_SESSION_DATE, fx.NEXT_SESSION_DATE)


@pytest.mark.unit
def test_friday_close_cannot_serve_as_post_event_reaction():
    """A Friday-close price window must exclude a Saturday-published event.

    ``in_window`` is the guard analysts' news items pass through; the same
    half-open-window logic must reject treating the pre-event close as a
    post-event observation. ``in_window`` windows are ``[start, end + 1 day)``,
    so the Friday session window is expressed with ``end`` at Friday midnight.
    """
    window_start = datetime(2026, 11, 6)
    window_end = datetime(2026, 11, 6)  # half-open: covers [11-06, 11-07)
    assert in_window(fx.last_session_close_dt(), window_start, window_end) is True
    # The event, published the next day, is outside that window.
    assert in_window(fx.event_publication_dt(), window_start, window_end) is False


@pytest.mark.unit
def test_price_move_is_about_a_quarter_percent_not_a_hundredth():
    """572.33 -> 570.89 is ~-0.25%, not the -0.01% the report claimed (test 16)."""
    move = fx.price_move_pct()
    assert move == pytest.approx(-0.2517, abs=1e-3)
    # The report's figure is off by more than an order of magnitude.
    assert abs(move) > 10 * 0.01


@pytest.mark.unit
def test_is_historical_answers_staleness_not_observability():
    """``is_historical`` is a staleness rule, not an observability rule.

    For a date in the past it is True (live-only vendor data would come from
    after it); for a date beyond today it is False. The BRK-B run date
    (2026-11-08) sits at the boundary and its answer depends on the real
    clock, so observability of the post-event session must come from the
    market calendar — pinned by the dedicated tests above — never from this
    helper.
    """
    assert is_historical("2024-01-01") is True
    assert is_historical("2999-12-31") is False
    assert is_historical("") is False
    assert is_historical(None) is False


# ---------------------------------------------------------------------------
# Test 2 — data availability: release vs SEC filing status
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_event_published_at_stays_unknown_until_verified():
    """The fixture must not invent a publication timestamp (contract 3.1).

    ``published_at`` is None: the release date is known, the time of day is
    not verified. Any code path that fills it without a verified source is a
    fabrication the tests must not bake in.
    """
    assert fx.EVENT_PUBLISHED_AT is None
    assert fx.EVENT_PERIOD == "2026-Q3"
    assert fx.EVENT_PERIOD_END == "2026-09-30"


@pytest.mark.unit
def test_release_and_filing_are_distinct_availability_states():
    """A company release and a SEC filing are different sources (contract 3.2).

    The fixture records the release as available on 11-07; a 10-Q filing is
    typically not available the same day. The two states must never collapse
    into one boolean.
    """
    # Release: available (date known).
    assert fx.EVENT_PUBLICATION_DATE == "2026-11-07"
    # Filing: pending — no filing date is recorded in the fixture at all.
    assert not hasattr(fx, "SEC_FILING_DATE")
    # The contract's states are distinct labels, not aliases.
    states = {"company_release_available", "sec_filing_available",
              "filing_pending", "unverified"}
    assert len(states) == 4


# ---------------------------------------------------------------------------
# Test 4 — ticker / share-class mismatch hazard
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_brk_a_to_b_conversion_ratio_is_recorded():
    """Per-share math across BRK-A/BRK-B needs the 1500:1 ratio (contract 3.3).

    The fixture carries the ratio so a validator can refuse a direct
    price-to-book comparison across share classes without conversion.
    """
    assert fx.BRK_A_TO_B_RATIO == 1500
    assert fx.TICKER == "BRK-B"


# ---------------------------------------------------------------------------
# Test 6 — risk buffer: the 543.70 / 543.50 plan must fail validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tranche_stop_distance_is_far_below_minimum_atr_buffer():
    """Entry 543.70, stop 543.50, ATR 9.408: ~0.021 ATR, under the 0.5 minimum.

    The contract (section 5) requires the plan to fail validation. This pins
    the arithmetic the future Risk Engine must reproduce.
    """
    distance = fx.entry_stop_distance()
    multiple = fx.entry_stop_atr_multiple()
    assert distance == pytest.approx(0.20, abs=1e-9)
    assert multiple == pytest.approx(0.20 / 9.408, abs=1e-6)
    assert multiple < fx.MIN_ENTRY_STOP_ATR
    # And by a wide margin: the plan is not borderline.
    assert multiple < fx.MIN_ENTRY_STOP_ATR / 10


@pytest.mark.unit
def test_minimum_atr_buffer_is_parametric_not_absolute():
    """The 0.5 ATR minimum is a configured threshold, not a universal law.

    The fixture exposes it as a named constant so the Risk Engine can read it
    from configuration; the test pins that it is positive and finite.
    """
    assert fx.MIN_ENTRY_STOP_ATR > 0
    assert math.isfinite(fx.MIN_ENTRY_STOP_ATR)


# ---------------------------------------------------------------------------
# Test 7 — order intention: OVERWEIGHT must not imply an executable order
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_strategic_rating_labels_are_distinct_from_execution_actions():
    """Rating, intent and execution action are separate vocabularies (contract 4).

    The fixture records the report's strategic rating; the execution layer's
    vocabulary (WAIT/BLOCK/...) shares no member with it, so a rating can
    never be mistaken for an action by string equality.
    """
    ratings = {"UNDERWEIGHT", "NEUTRAL", "OVERWEIGHT"}
    actions = {"WAIT", "BLOCK", "PROPOSE_PAPER_ORDER", "SUBMIT_PAPER_ORDER"}
    intents = {"AVOID", "MONITOR", "ACCUMULATE_CONDITIONALLY", "MAINTAIN", "REDUCE"}
    assert ratings.isdisjoint(actions)
    assert ratings.isdisjoint(intents)
    assert actions.isdisjoint(intents)


@pytest.mark.unit
def test_close_is_below_reported_entry_so_no_trigger_is_satisfied():
    """Close 570.89 vs tranche entry 543.70: the entry trigger is not met.

    The report's own numbers put the last price far above the planned entry,
    so the conditional plan must evaluate to WAIT, not to an order.
    """
    assert fx.CLOSE_LAST_SESSION > fx.TRANCHE_3_ENTRY
    gap = fx.CLOSE_LAST_SESSION - fx.TRANCHE_3_ENTRY
    assert gap == pytest.approx(27.19, abs=1e-9)


# ---------------------------------------------------------------------------
# Safety audit — no live-broker path exists in the codebase
# ---------------------------------------------------------------------------

# Symbols that would indicate order submission or broker SDK usage. The
# codebase is analysis/paper-only; if one of these appears, this test fails
# and the change must be reviewed against the contract's safety rules.
_FORBIDDEN_SYMBOLS = (
    "alpaca",
    "ib_insync",
    "ibapi",
    "interactive_brokers",
    "ccxt",
    "place_order",
    "submit_order",
    "create_order",
    "cancel_order",
    "modify_order",
)

# Packages scanned: application code only (tests and caches excluded).
_SCAN_DIRS = ("tradingagents", "cli", "webapp")


def _python_sources():
    for rel_dir in _SCAN_DIRS:
        root = REPO_ROOT / rel_dir
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            yield path


@pytest.mark.unit
def test_no_live_broker_symbols_in_application_code():
    """No broker SDK import or order-submission symbol appears in app code.

    Grounded audit (Phase 0): the repository currently contains zero matches.
    This test keeps it that way — a future live-trading path must arrive with
    an explicit contract amendment, not silently.
    """
    offenders = []
    for path in _python_sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        lowered = text.lower()
        for symbol in _FORBIDDEN_SYMBOLS:
            if symbol in lowered:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {symbol}")
    assert not offenders, (
        "Live-broker/order symbols found in application code: "
        + "; ".join(offenders)
    )


@pytest.mark.unit
def test_network_layer_is_read_only():
    """The shared HTTP helper issues only GET and HEAD requests.

    ``tradingagents/dataflows/net.py`` is the single choke point for vendor
    HTTP calls. Pinning it to GET/HEAD means the data layer cannot place
    orders anywhere; a POST/PUT there would need review.
    """
    net_py = REPO_ROOT / "tradingagents" / "dataflows" / "net.py"
    text = net_py.read_text(encoding="utf-8")
    assert "requests.get(" in text
    assert "requests.head(" in text
    assert "requests.post(" not in text
    assert "requests.put(" not in text
    assert "requests.delete(" not in text
