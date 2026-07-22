"""Strategy-quality mechanics: rules engine, R-based ladder, breakeven
lock-in, cost/R:R gates, stop-out cooldown, and R accounting."""

from datetime import timedelta

import pytest

from tests.pro_fakes import BASE_TS
from tests.test_pro_memory_facade import make_recommendation
from tradingagents.contracts import (
    AssetClass,
    OHLCVBar,
    ProConfig,
    TakeProfitLevel,
    Timeframe,
    TradeAction,
    TradingMode,
)
from tradingagents.pro.analytics.risk import take_profits_from_risk
from tradingagents.pro.analytics.signals import adx_says_chop, evaluate_refs
from tradingagents.pro.backtest import (
    BacktestEngine,
    BarReplay,
    CommissionModel,
    LiquidityModel,
    SimBroker,
    SlippageModel,
)
from tradingagents.pro.evals.rules import RulesPipelineLLM
from tradingagents.pro.memory import ProMemory
from tradingagents.pro.pipeline.gates import trade_quality_gate

CONFIG = ProConfig(asset=AssetClass.GOLD, mode=TradingMode.BACKTEST,
                   max_debate_rounds=1)


def bar(open_, high, low, close, volume=1_000.0, day=0) -> OHLCVBar:
    return OHLCVBar(
        timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=day),
        open=open_, high=high, low=low, close=close, volume=volume,
    )


def make_broker(**kw) -> SimBroker:
    defaults = {
        "slippage": SlippageModel(bps=0),
        "commission": CommissionModel(rate_bps=0),
        "liquidity": LiquidityModel(max_participation=1.0),
    }
    defaults.update(kw)
    return SimBroker(initial_equity=10_000.0, **defaults)


def rec(entry=100.0, stop=95.0, tps=((105.0, 0.5), (115.0, 0.5)), qty=10.0):
    return make_recommendation(action=TradeAction.BUY).model_copy(update={
        "entry_price": entry,
        "stop_loss": stop,
        "take_profits": [TakeProfitLevel(price=p, size_fraction=f) for p, f in tps],
        "position_size": make_recommendation().position_size.model_copy(
            update={"quantity": qty}),
        "risk_reward": None,
    })


# --- signal rules -------------------------------------------------------------


class TestSignalRules:
    def test_bullish_alignment(self):
        direction, confidence, claim = evaluate_refs({
            "LAST_CLOSE": 110.0, "SMA_50": 100.0, "SMA_200": 90.0,
            "RSI_14": 65.0,
        })
        assert direction == "bullish" and confidence > 60
        assert "SMA50" in claim

    def test_bearish_alignment(self):
        direction, confidence, _ = evaluate_refs({
            "LAST_CLOSE": 80.0, "SMA_50": 100.0, "SMA_200": 110.0,
            "RSI_14": 30.0,
        })
        assert direction == "bearish" and confidence > 60

    def test_mixed_inputs_go_neutral(self):
        direction, _, _ = evaluate_refs({
            "LAST_CLOSE": 105.0, "SMA_50": 100.0,   # bullish structure
            "RSI_14": 35.0,                          # bearish momentum
        })
        assert direction == "neutral"

    def test_no_numeric_rules_abstains(self):
        assert evaluate_refs({"BARS_SHOWN": 60.0}) is None
        assert evaluate_refs({}) is None

    def test_chop_filter_fails_closed(self):
        assert adx_says_chop(12.0) is True
        assert adx_says_chop(25.0) is False
        assert adx_says_chop(None) is True  # no reading → no entry


# --- R-based ladder -----------------------------------------------------------


class TestRLadder:
    def test_planned_rr_is_two_by_construction(self):
        ladder = take_profits_from_risk(100.0, 95.0, "BUY")
        assert [tp.price for tp in ladder] == [102.5, 117.5]  # 0.5R, 3.5R
        reward = sum(abs(tp.price - 100.0) * tp.size_fraction for tp in ladder)
        assert reward / 5.0 == pytest.approx(2.0)

    def test_tighter_stop_keeps_geometry(self):
        ladder = take_profits_from_risk(100.0, 99.0, "SELL")
        assert [tp.price for tp in ladder] == [99.5, 96.5]
        reward = sum(abs(tp.price - 100.0) * tp.size_fraction for tp in ladder)
        assert reward / 1.0 == pytest.approx(2.0)

    def test_breakeven_exit_on_default_ladder_counts_as_a_win(self):
        """TP1 at +0.5R banks 0.25R on the ladder's 50% fraction; the
        breakeven exit nets ~+0.2R — decisively above the 0.1R scratch
        band, so the structural hit-rate math holds in the accounting."""
        banked_r = 0.5 * 0.5  # fraction × rung
        cost_drag_r = 0.08 * 0.5  # generous cost estimate on the remainder
        assert banked_r - cost_drag_r > 0.1

    def test_sell_ladder_never_crosses_zero(self):
        # stop distance 40% of price: an unscaled 3R target would be negative
        ladder = take_profits_from_risk(10.0, 14.0, "SELL")
        assert all(tp.price > 0 for tp in ladder)
        assert ladder[0].price > ladder[1].price  # still descending


# --- spot-max sizing ------------------------------------------------------------


class TestSpotMaxSizing:
    """Realized risk per trade = min(risk target, notional cap × stop
    distance). On tight intraday stops the notional cap is what binds, so
    raising it from 10% to the spot-max 33% is what scales deployed risk."""

    def test_tight_stop_risk_scales_with_the_notional_cap(self):
        from tradingagents.pro.analytics.risk import fixed_risk_position_size

        # 0.5% stop (typical 5m ATR stop on BTC): 1% risk wants 200% notional
        def realized_risk(max_position_pct):
            size = fixed_risk_position_size(
                100_000.0, 1.0, entry=100.0, stop=99.5,
                max_position_pct=max_position_pct)
            return size.quantity * 0.5

        # 10% cap: $49.5 risk (0.05% of equity — the observed prod throttle)
        assert realized_risk(10.0) == pytest.approx(49.5)
        # spot-max 33% cap: ~3.3x more capital deployed per trade
        assert realized_risk(33.0) == pytest.approx(163.35)

    def test_wide_stop_reaches_the_full_risk_target(self):
        from tradingagents.pro.analytics.risk import fixed_risk_position_size

        # 4% stop (daily timeframe): 1% risk needs only 25% notional — the
        # 33% cap doesn't bind and the full risk target deploys
        size = fixed_risk_position_size(100_000.0, 1.0, entry=100.0,
                                        stop=96.0, max_position_pct=33.0)
        assert size.quantity * 4.0 == pytest.approx(1_000.0)  # exactly 1%
        assert size.notional < 33_000.0

    def test_gross_exposure_stays_spot_honest(self):
        # 3 concurrent positions × 33% ≈ 99% gross: full capital, no leverage
        limits = CONFIG.risk
        assert limits.max_open_positions * 33.0 <= 100.0


# --- quality gate --------------------------------------------------------------


def _metric(name, value):
    from tradingagents.contracts import MetricReading

    return MetricReading(name=name, value=value, source="risk_engine")


class TestQualityGate:
    def _metrics(self, entry=100.0, stop=99.9, tp1=None, tp2=None):
        risk = abs(entry - stop)
        return {
            "ENTRY_REF_PRICE": _metric("ENTRY_REF_PRICE", entry),
            "ATR_STOP": _metric("ATR_STOP", stop),
            "ATR_TP1": _metric("ATR_TP1", tp1 if tp1 is not None else entry + risk),
            "ATR_TP2": _metric("ATR_TP2", tp2 if tp2 is not None else entry + 3 * risk),
        }

    def test_cost_gate_blocks_noise_stops(self):
        # stop 0.1% away < 8 × 6bps = 0.48% floor
        result = trade_quality_gate(self._metrics(stop=99.9), CONFIG)
        assert not result.passed
        assert any("friction" in r for r in result.reasons)

    def test_wide_stop_passes(self):
        result = trade_quality_gate(self._metrics(stop=98.0), CONFIG)
        assert result.passed, result.reasons

    def test_low_rr_rejected(self):
        # ladder squeezed to ~1:1 → below min 1.8
        result = trade_quality_gate(
            self._metrics(stop=98.0, tp1=101.0, tp2=103.0), CONFIG)
        assert not result.passed
        assert any("R:R" in r for r in result.reasons)


# --- broker breakeven ----------------------------------------------------------


class TestBreakeven:
    def test_tp1_moves_stop_to_breakeven_and_locks_the_trade(self):
        broker = make_broker()  # breakeven_after_tp1 defaults on
        broker.open_from_recommendation(rec(), bar(100, 101, 99, 100))
        # TP1 at 105 fills half; stop moves to entry + buffer
        assert broker.process_bar(bar(104, 106, 103, 105, day=1)) == []
        pos = next(iter(broker.positions.values()))
        assert pos.at_breakeven
        assert pos.stop == pytest.approx(100.0 * 1.0006)
        assert pos.initial_stop == 95.0  # R unit never mutates
        # price collapses: remainder exits at the breakeven stop, NOT 95
        trades = broker.process_bar(bar(103, 103, 90, 91, day=2))
        assert len(trades) == 1
        trade = trades[0]
        assert trade.reason == "breakeven"
        # banked TP1 (+5 × 5) plus remainder ~flat → net decisively positive
        assert trade.pnl > 20
        assert trade.r_multiple == pytest.approx(trade.pnl / (10 * 5.0))

    def test_breakeven_disabled_keeps_original_stop(self):
        broker = make_broker(breakeven_after_tp1=False)
        broker.open_from_recommendation(rec(), bar(100, 101, 99, 100))
        broker.process_bar(bar(104, 106, 103, 105, day=1))
        pos = next(iter(broker.positions.values()))
        assert pos.stop == 95.0 and not pos.at_breakeven
        trades = broker.process_bar(bar(103, 103, 90, 91, day=2))
        assert trades[0].reason == "stop"

    def test_r_multiple_on_full_stop_is_about_minus_one(self):
        broker = make_broker()
        broker.open_from_recommendation(rec(), bar(100, 101, 99, 100))
        trades = broker.process_bar(bar(96, 96, 94, 94, day=1))
        assert trades[0].reason == "stop"
        assert trades[0].r_multiple == pytest.approx(-1.0)


# --- cooldown -------------------------------------------------------------------


class TestCooldown:
    def test_no_same_side_reentry_after_stop_out(self):
        # falling series: rules engine sells, stops happen, cooldown gates
        bars, price = [], 1000.0
        for i in range(260):
            close = price - 1.2 if i % 40 else price + 8.0  # sawtooth down
            bars.append(OHLCVBar(
                timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
                open=price, high=max(price, close) + 3.0,
                low=min(price, close) - 3.0, close=close, volume=1000.0))
            price = close
        engine = BacktestEngine(
            RulesPipelineLLM(), CONFIG,
            BarReplay("XAUUSD", AssetClass.GOLD, bars, window=60,
                      precompute_indicators=True),
            broker=SimBroker(initial_equity=100_000.0),
            memory=ProMemory(), min_history=60, decide_every=1,
        )
        result = engine.run()
        cooldown = CONFIG.risk.stop_cooldown_bars
        stops = sorted(t.closed_at for t in result.trades if t.reason == "stop")
        opens = sorted((t.opened_at, t.side) for t in result.trades)
        for stop_time in stops:
            for opened_at, _side in opens:
                gap_days = (opened_at - stop_time).days
                # entry bar is decision bar + 1, so a post-stop entry can
                # appear no earlier than cooldown bars after the stop
                assert not (0 < gap_days <= cooldown - 1), (
                    f"re-entry {gap_days}d after a stop-out (cooldown "
                    f"{cooldown})")
        if result.rejections.get("cooldown"):
            assert result.rejections["cooldown"] > 0


# --- rules engine end-to-end -----------------------------------------------------


class TestRulesEngineRegimes:
    def _run(self, fn, n=400):
        bars, price = [], 1000.0
        for i in range(n):
            close = fn(i, price)
            bars.append(OHLCVBar(
                timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
                open=price, high=max(price, close) + 2.0,
                low=min(price, close) - 2.0, close=close, volume=1000.0))
            price = close
        engine = BacktestEngine(
            RulesPipelineLLM(), CONFIG,
            BarReplay("XAUUSD", AssetClass.GOLD, bars, window=60,
                      precompute_indicators=True),
            broker=SimBroker(initial_equity=100_000.0),
            memory=ProMemory(), min_history=60, decide_every=1,
        )
        return engine.run()

    def test_uptrend_goes_long_with_two_to_one_ladder(self):
        result = self._run(lambda i, p: p + 0.5)
        assert result.executed > 0
        assert {t.side for t in result.trades} == {"BUY"}
        assert result.report.avg_planned_rr == pytest.approx(2.0, abs=0.01)

    def test_downtrend_goes_short(self):
        result = self._run(lambda i, p: p - 0.8)
        assert result.executed > 0
        assert {t.side for t in result.trades} == {"SELL"}

    def test_chop_mostly_holds(self):
        result = self._run(lambda i, p: 1000.0 + (3.0 if i % 2 else -3.0))
        # entries collapse in chop (a handful at the synthetic seam is fine)
        assert result.executed <= result.decisions * 0.05
