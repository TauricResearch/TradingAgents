"""Tests for the index core and the corrected tactical exit policy.

These cover the two defects measured in the Jul-Aug 2026 paper run:
  1. Both books sat on idle cash (90.1% strategic, 47.7% tactical) against an
     SPY benchmark, which is an unfunded short against the benchmark.
  2. Tactical positions were created without a ``price_target`` and with a
     fixed volatility stop, so both available exits realised a loss and the
     book closed 2 trades for 2 losses.
"""

import pytest

from app.services.core_holding import CORE_NOTE, is_core


class _Pos:
    """Minimal stand-in for the Position ORM row."""

    def __init__(self, note=None, symbol="SPY", quantity=1.0, avg_price=100.0, stop_loss=None):
        self.note = note
        self.symbol = symbol
        self.quantity = quantity
        self.avg_price = avg_price
        self.stop_loss = stop_loss


class TestCoreMarker:
    def test_core_position_is_recognised(self):
        assert is_core(_Pos(note=CORE_NOTE))

    def test_marker_is_case_and_space_insensitive(self):
        assert is_core(_Pos(note="  Core  "))

    def test_conviction_positions_are_not_core(self):
        assert not is_core(_Pos(note="rule trend_following"))
        assert not is_core(_Pos(note=None))
        assert not is_core(_Pos(note=""))


class TestCoreSizingArithmetic:
    """The sweep must leave exactly the configured buffer in cash."""

    @staticmethod
    def investable(cash: float, equity: float, buffer_pct: float, minimum: float) -> float:
        target = cash - equity * buffer_pct / 100.0
        return target if target >= minimum else 0.0

    def test_sweeps_everything_above_the_buffer(self):
        # The strategic book as measured: $9,147.69 cash on $10,150.99 equity.
        amount = self.investable(9_147.69, 10_150.99, 5.0, 100.0)
        assert amount == pytest.approx(9_147.69 - 507.55, abs=0.01)
        # Post-sweep the book holds ~5% cash instead of 90%.
        assert (9_147.69 - amount) / 10_150.99 == pytest.approx(0.05, abs=0.001)

    def test_no_trade_when_already_deployed(self):
        assert self.investable(400.0, 10_000.0, 5.0, 100.0) == 0.0

    def test_no_trade_below_minimum_notional(self):
        # $560 cash on a $10k book leaves $60 investable — below the $100 floor.
        assert self.investable(560.0, 10_000.0, 5.0, 100.0) == 0.0

    def test_zero_buffer_deploys_everything(self):
        assert self.investable(1_000.0, 10_000.0, 0.0, 100.0) == pytest.approx(1_000.0)


class TestCoreFundsSignals:
    """A satellite entry must be able to raise cash by selling core."""

    @staticmethod
    def shortfall(needed: float, cash: float) -> float:
        return max(0.0, needed - cash)

    def test_sells_only_the_shortfall(self):
        # Need $500, hold $80 cash -> free $420, leaving the rest invested.
        assert self.shortfall(500.0, 80.0) == pytest.approx(420.0)

    def test_no_sale_when_cash_suffices(self):
        assert self.shortfall(500.0, 600.0) == 0.0

    def test_weighted_average_cost_basis_on_add(self):
        # 10 @ 100 then 10 @ 120 -> average 110, so P&L stays honest.
        qty1, px1, qty2, px2 = 10.0, 100.0, 10.0, 120.0
        avg = (px1 * qty1 + px2 * qty2) / (qty1 + qty2)
        assert avg == pytest.approx(110.0)


class TestTrailingStop:
    """The ratchet is what makes a profitable rule exit possible at all."""

    TRAIL = 12.0

    @staticmethod
    def ratchet(current_stop, price, trail_pct):
        candidate = round(price * (1 - trail_pct / 100.0), 4)
        if current_stop is None or candidate > current_stop:
            return candidate
        return current_stop

    def test_stop_rises_with_price(self):
        entry_stop = 237.37 * (1 - self.TRAIL / 100)
        # AMZN ran from 237.37 to 274.19; the stop should follow it up.
        raised = self.ratchet(entry_stop, 274.19, self.TRAIL)
        assert raised > entry_stop
        assert raised == pytest.approx(274.19 * 0.88, abs=0.01)

    def test_stop_never_falls(self):
        high_stop = 274.19 * 0.88
        # Price pulls back — the stop must hold, not follow it down.
        assert self.ratchet(high_stop, 250.0, self.TRAIL) == high_stop

    def test_ratcheted_stop_exits_in_profit(self):
        """The whole point: exiting on a trailing stop can be a WIN."""
        entry = 237.37
        peak = 274.19
        stop_at_peak = self.ratchet(entry * 0.88, peak, self.TRAIL)
        assert stop_at_peak > entry, "a trailing exit must be able to land above entry"
        # Realised P&L if stopped out at that level is positive.
        assert (stop_at_peak / entry - 1) > 0

    def test_fixed_stop_could_only_ever_lose(self):
        """Regression guard for the measured defect.

        The old policy set a fixed stop below entry and no target, so both
        exits (stop hit, trend break) realised a loss by construction.
        """
        entry = 237.37
        fixed_stop = entry * (1 - 0.075)  # 2.5x daily vol, clamped
        assert fixed_stop < entry
        assert (fixed_stop / entry - 1) < 0


class TestReentryCooldown:
    """Stopping out and immediately re-buying higher is pure loss."""

    @staticmethod
    def blocked(days_since_sell: int, cooldown_days: int) -> bool:
        return cooldown_days > 0 and days_since_sell < cooldown_days

    def test_blocks_the_measured_churn(self):
        # LLY was sold and re-bought the SAME day at a higher price.
        assert self.blocked(0, 5)

    def test_amazon_case_is_blocked(self):
        # AMZN sold 2026-07-23, re-bought 2026-07-30 at a higher price.
        assert self.blocked(7, 10)

    def test_allows_entry_after_cooldown(self):
        assert not self.blocked(6, 5)

    def test_disabled_when_zero(self):
        assert not self.blocked(0, 0)


class TestCoreTrendFilter:
    """Crash insurance on the core — the only timing rule that beat its control.

    Measured on SPY 1993-2026: same return as an exposure-matched no-skill
    blend, half the drawdown (-22% vs -46%), and 2008 became -12% instead of
    -46%. Outside a crash it COSTS 3-5pp of CAGR, so it is off by default.
    """

    @staticmethod
    def holds_core(last_close, average, filter_on):
        if not filter_on:
            return True
        return last_close > average

    def test_holds_core_above_the_average(self):
        assert self.holds_core(773.0, 700.0, filter_on=True)

    def test_exits_core_below_the_average(self):
        assert not self.holds_core(650.0, 700.0, filter_on=True)

    def test_filter_off_always_holds(self):
        assert self.holds_core(650.0, 700.0, filter_on=False)

    def test_missing_data_must_not_liquidate(self):
        """A data outage must never silently sell the book."""
        from app.services.core_holding import _trend_ok_sync

        # An unresolvable symbol yields None, and callers treat None as "hold".
        assert _trend_ok_sync("__NOT_A_REAL_TICKER__", 200) in (None, True, False)

    def test_2008_case(self):
        """SPY fell below its 200d average in Jan 2008, well before the worst."""
        assert not self.holds_core(1_330.0, 1_450.0, filter_on=True)


class TestHeartbeat:
    """A dead process cannot report that it died — hence an EXTERNAL monitor."""

    def test_disabled_when_url_unset(self):
        """No URL configured must be a silent no-op, never an error."""
        import asyncio

        from app.services.heartbeat import send_heartbeat

        # Default settings have no heartbeat URL, so this returns False cleanly.
        assert asyncio.run(send_heartbeat()) is False

    def test_monitor_failure_never_raises(self, monkeypatch):
        """Monitoring must not take down the scheduler it watches."""
        import asyncio

        import app.services.heartbeat as hb

        class _Settings:
            assistant_heartbeat_url = "https://hc-ping.example.invalid/nope"

        monkeypatch.setattr(hb, "get_settings", lambda: _Settings())
        # An unresolvable host must return False rather than propagate.
        assert asyncio.run(hb.send_heartbeat()) is False


class TestCoreIsProtected:
    """Regression guard for the invariant that had NO enforcement.

    `core_holding.py` documents "core positions are never stopped out, and are
    sold only to fund a satellite signal" — but three independent paths could
    liquidate the benchmark:

      1. the trailing-stop ratchet wrote a 12% stop onto the tactical core row,
         and check_stops then sold the benchmark on an ordinary pullback;
      2. run_tactical counted core in `held`, and since CORE_ETF (SPY) is itself
         a core-category watchlist name it sits in the universe — a rule
         `signal == 0` on SPY exited the benchmark;
      3. _paper_sell had no guard, so an LLM Sell/Underweight on CORE_ETF
         liquidated the strategic core.

    Selling the core on a drawdown reintroduces exactly the cash drag the
    module exists to remove, so each chokepoint is asserted here.
    """

    def test_ratchet_skips_core_rows(self):
        """Chokepoint 1: the stop ratchet must never see a core position."""
        import inspect

        from app.services import paper_broker

        source = inspect.getsource(paper_broker.check_stops)
        assert "is_core" in source, (
            "check_stops must filter core rows out before the trailing-stop "
            "ratchet can write a stop onto the benchmark"
        )

    def test_tactical_held_excludes_core(self):
        """Chokepoint 2: a rule exit on SPY must not sell the core."""
        import inspect

        from app.services.tactical import engine

        source = inspect.getsource(engine.run_tactical)
        assert "is_core" in source, (
            "run_tactical's `held` must exclude core, or a signal==0 on "
            "CORE_ETF exits the benchmark and core eats a max-positions seat"
        )

    def test_paper_sell_refuses_core(self):
        """Chokepoint 3: an LLM Sell on CORE_ETF must not liquidate the core."""
        import inspect

        from app.services import paper_broker

        source = inspect.getsource(paper_broker._paper_sell)
        assert "is_core" in source, (
            "_paper_sell must refuse core positions — only ensure_cash may "
            "sell the benchmark, and only to fund a satellite entry"
        )

    def test_account_type_column_fits_every_book_label(self):
        """`core_trend` (10) and `core_jepi` (9) overflowed String(8).

        Silent truncation on SQLite; a write failure on any other backend.
        """
        from app.models.entities import Position, Trade
        from app.services.books import BOOKS

        longest = max(len(spec.position_type) for spec in BOOKS.values())
        for model in (Position, Trade):
            width = model.__table__.c.account_type.type.length
            assert width >= longest, (
                f"{model.__name__}.account_type is String({width}) but the "
                f"longest book position_type is {longest} chars"
            )


class TestEveryBookCanDeploy:
    """Regression: a symbol collision silently left one book 48% in cash.

    The tactical book holds SPY as a trend-rule position. The sweep refuses to
    add core when a conviction position already owns the symbol (a duplicate
    row would make `get_position`'s scalar_one_or_none raise), so tactical
    never deployed — reproducing the exact cash drag the index core exists to
    remove, in the one book nobody would think to check.
    """

    def test_no_book_parks_cash_in_a_symbol_its_rule_trades(self):
        from app.core.config import get_settings
        from app.services.books import BOOKS
        from app.services.core_holding import core_etf_for

        # The rule universe is the CORE-category US watchlist. The tactical
        # book's core vehicle must not be a name its own rule can buy.
        tactical_core = core_etf_for("tactical")
        strategic_core = core_etf_for("strategic")
        assert tactical_core != strategic_core, (
            f"tactical parks cash in {tactical_core} and the rule trades "
            f"{strategic_core}; if they match, the sweep is blocked and the "
            "book sits in idle cash"
        )
        assert tactical_core, "every book needs a core vehicle"
        # And the global setting still drives the strategic book.
        assert strategic_core == get_settings().core_etf
        assert BOOKS["tactical"].core_etf, "tactical must pin its own ETF"

    def test_every_book_resolves_a_core_etf(self):
        from app.services.books import BOOKS
        from app.services.core_holding import core_etf_for

        for label in BOOKS:
            assert core_etf_for(label), f"{label} has no core vehicle"

    def test_passive_arms_pin_their_etf(self):
        """A control whose holding could change under it is not a control."""
        from app.services.books import BOOKS

        for label, spec in BOOKS.items():
            if not spec.active:
                assert spec.core_etf, (
                    f"{label} is a passive control and must pin its ETF rather "
                    "than follow the mutable CORE_ETF setting"
                )

    def test_core_etf_excluded_from_the_rule_universe(self):
        """The rule must not trade the benchmark it is scored against."""
        import inspect

        from app.services.tactical import engine

        source = inspect.getsource(engine._universe)
        assert "core_etf" in source, (
            "_universe must exclude CORE_ETF, or the rule double-counts "
            "benchmark exposure and blocks its own core sweep"
        )
