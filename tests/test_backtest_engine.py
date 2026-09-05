from datetime import date, datetime, timezone

from tradingagents.research_platform.agent_contracts import (
    TradeDirection,
    TradeHorizon,
    TradeSignal,
)
from tradingagents.research_platform.backtest_contracts import (
    BacktestConfig,
    ExecutionConfig,
)
from tradingagents.research_platform.backtest_engine import run_daily_signal_backtest
from tradingagents.research_platform.data_contracts import DataProvenance, PriceBar


def _bar(symbol: str, day: date, close: float) -> PriceBar:
    return PriceBar(
        symbol=symbol,
        date=day,
        open=close,
        high=close,
        low=close,
        close=close,
        adjusted_close=close,
        volume=1000,
        provenance=DataProvenance(
            provider="fixture",
            as_of_date=day,
            retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            source="fixture",
            vendor_symbol=symbol,
        ),
    )


def _signal(
    *,
    as_of_date: date,
    direction: TradeDirection = TradeDirection.BUY,
    position_pct: float | None = 0.5,
) -> TradeSignal:
    return TradeSignal(
        symbol="NVDA",
        as_of_date=as_of_date,
        direction=direction,
        horizon=TradeHorizon.MEDIUM,
        confidence=0.8,
        rationale="Fixture signal.",
        proposed_position_pct=position_pct,
    )


def test_backtest_executes_signal_on_next_available_bar():
    result = run_daily_signal_backtest(
        config=BacktestConfig(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 3),
            initial_cash=1000,
            symbols=["NVDA"],
        ),
        price_bars=[
            _bar("NVDA", date(2026, 1, 1), 100),
            _bar("NVDA", date(2026, 1, 2), 110),
            _bar("NVDA", date(2026, 1, 3), 120),
        ],
        signals=[_signal(as_of_date=date(2026, 1, 1), position_pct=0.5)],
    )

    assert len(result.trades) == 1
    assert result.trades[0].date == date(2026, 1, 2)
    assert result.trades[0].source_signal_date == date(2026, 1, 1)
    assert result.trades[0].cash_after is not None
    assert result.trades[0].position_after is not None
    assert result.equity_curve[-1].equity > 1000


def test_backtest_allows_same_day_execution_when_configured():
    result = run_daily_signal_backtest(
        config=BacktestConfig(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
            initial_cash=1000,
            symbols=["NVDA"],
            execution=ExecutionConfig(allow_same_day_signal=True),
        ),
        price_bars=[
            _bar("NVDA", date(2026, 1, 1), 100),
            _bar("NVDA", date(2026, 1, 2), 105),
        ],
        signals=[_signal(as_of_date=date(2026, 1, 1), position_pct=0.5)],
    )

    assert len(result.trades) == 1
    assert result.trades[0].date == date(2026, 1, 1)
    assert result.assumptions["signal_execution"].startswith("first eligible bar")


def test_backtest_closes_long_on_sell_when_shorts_disabled():
    result = run_daily_signal_backtest(
        config=BacktestConfig(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 4),
            initial_cash=1000,
            symbols=["NVDA"],
        ),
        price_bars=[
            _bar("NVDA", date(2026, 1, 1), 100),
            _bar("NVDA", date(2026, 1, 2), 100),
            _bar("NVDA", date(2026, 1, 3), 100),
            _bar("NVDA", date(2026, 1, 4), 100),
        ],
        signals=[
            _signal(as_of_date=date(2026, 1, 1), position_pct=0.5),
            _signal(
                as_of_date=date(2026, 1, 2),
                direction=TradeDirection.SELL,
                position_pct=0.5,
            ),
        ],
    )

    assert [trade.direction for trade in result.trades] == [
        TradeDirection.BUY,
        TradeDirection.SELL,
    ]
    assert result.equity_curve[-1].gross_exposure_pct == 0.0
    assert len(result.round_trips) == 1
    assert result.round_trips[0].holding_days == 1


def test_backtest_applies_commission_and_slippage():
    result = run_daily_signal_backtest(
        config=BacktestConfig(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
            initial_cash=1000,
            symbols=["NVDA"],
            execution=ExecutionConfig(commission_bps=10, slippage_bps=10),
        ),
        price_bars=[
            _bar("NVDA", date(2026, 1, 1), 100),
            _bar("NVDA", date(2026, 1, 2), 100),
        ],
        signals=[_signal(as_of_date=date(2026, 1, 1), position_pct=0.5)],
    )

    assert len(result.trades) == 1
    assert result.trades[0].price == 100.1
    assert result.trades[0].commission > 0
    assert result.equity_curve[-1].equity < 1000


def test_backtest_metrics_include_turnover_and_drawdown():
    result = run_daily_signal_backtest(
        config=BacktestConfig(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 4),
            initial_cash=1000,
            symbols=["NVDA"],
        ),
        price_bars=[
            _bar("NVDA", date(2026, 1, 1), 100),
            _bar("NVDA", date(2026, 1, 2), 100),
            _bar("NVDA", date(2026, 1, 3), 90),
            _bar("NVDA", date(2026, 1, 4), 95),
        ],
        signals=[_signal(as_of_date=date(2026, 1, 1), position_pct=1.0)],
    )

    assert result.metrics.turnover_pct == 1.0
    assert result.metrics.max_drawdown_pct > 0
    assert result.metrics.average_exposure_pct > 0
    assert result.metrics.win_rate_pct is None


def test_backtest_trade_quality_metrics_use_closed_round_trips():
    result = run_daily_signal_backtest(
        config=BacktestConfig(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 6),
            initial_cash=1000,
            symbols=["NVDA"],
        ),
        price_bars=[
            _bar("NVDA", date(2026, 1, 1), 100),
            _bar("NVDA", date(2026, 1, 2), 100),
            _bar("NVDA", date(2026, 1, 3), 110),
            _bar("NVDA", date(2026, 1, 4), 110),
            _bar("NVDA", date(2026, 1, 5), 100),
            _bar("NVDA", date(2026, 1, 6), 100),
        ],
        signals=[
            _signal(as_of_date=date(2026, 1, 1), position_pct=0.5),
            _signal(as_of_date=date(2026, 1, 2), direction=TradeDirection.SELL, position_pct=0.5),
            _signal(as_of_date=date(2026, 1, 3), position_pct=0.5),
            _signal(as_of_date=date(2026, 1, 4), direction=TradeDirection.SELL, position_pct=0.5),
        ],
    )

    assert len(result.round_trips) == 2
    assert result.metrics.win_rate_pct == 0.5
    assert result.metrics.profit_factor is not None
    assert result.metrics.average_holding_days == 1.0
    assert result.metrics.max_consecutive_losses == 1


def test_backtest_emits_structured_warning_for_unexecuted_signal():
    result = run_daily_signal_backtest(
        config=BacktestConfig(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            initial_cash=1000,
            symbols=["NVDA"],
        ),
        price_bars=[_bar("NVDA", date(2026, 1, 1), 100)],
        signals=[_signal(as_of_date=date(2026, 1, 1), position_pct=0.5)],
    )

    assert result.warning_events[0].code == "signal_not_executed"
    assert result.warning_events[0].symbol == "NVDA"
    assert result.warnings == [result.warning_events[0].message]
