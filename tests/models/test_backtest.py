from datetime import date, datetime
from decimal import Decimal

import pytest

from tradingagents.models.backtest import (
    BacktestConfig,
    BacktestResult,
    BacktestStatus,
    BacktestMetrics,
    EquityCurvePoint,
    TradeLog,
)
from tradingagents.models.portfolio import PortfolioConfig
from tradingagents.models.trading import Trade, OrderSide


class TestBacktestConfig:
    def test_basic_config(self):
        config = BacktestConfig(
            tickers=["AAPL"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
        )
        assert config.tickers == ["AAPL"]
        assert config.interval == "1d"
        assert config.benchmark_ticker == "SPY"

    def test_multi_ticker_config(self):
        config = BacktestConfig(
            name="Multi-Stock Test",
            tickers=["aapl", "googl", "msft"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        assert config.tickers == ["AAPL", "GOOGL", "MSFT"]

    def test_invalid_date_range(self):
        with pytest.raises(ValueError):
            BacktestConfig(
                tickers=["AAPL"],
                start_date=date(2024, 6, 30),
                end_date=date(2024, 1, 1),
            )

    def test_same_start_end_date(self):
        with pytest.raises(ValueError):
            BacktestConfig(
                tickers=["AAPL"],
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 1),
            )

    def test_empty_tickers(self):
        with pytest.raises(ValueError):
            BacktestConfig(
                tickers=[],
                start_date=date(2024, 1, 1),
                end_date=date(2024, 6, 30),
            )

    def test_trading_days_estimate(self):
        config = BacktestConfig(
            tickers=["AAPL"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        assert config.trading_days_estimate > 200
        assert config.trading_days_estimate < 260

    def test_custom_portfolio_config(self):
        portfolio_config = PortfolioConfig(
            initial_cash=Decimal("50000"),
            commission_per_trade=Decimal("5"),
        )
        config = BacktestConfig(
            tickers=["AAPL"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            portfolio_config=portfolio_config,
        )
        assert config.portfolio_config.initial_cash == Decimal("50000")


class TestTradeLog:
    def test_empty_trade_log(self):
        log = TradeLog()
        assert log.total_trades == 0
        assert log.win_rate is None
        assert log.profit_factor is None

    def test_add_winning_trade(self):
        log = TradeLog()
        trade = Trade(
            ticker="AAPL",
            side=OrderSide.BUY,
            entry_price=Decimal("100"),
            entry_quantity=100,
            entry_time=datetime(2024, 1, 15),
            exit_price=Decimal("110"),
            exit_quantity=100,
            exit_time=datetime(2024, 1, 20),
        )
        log.add_trade(trade)
        assert log.total_trades == 1
        assert log.winning_trades == 1
        assert log.win_rate == Decimal("100")

    def test_add_losing_trade(self):
        log = TradeLog()
        trade = Trade(
            ticker="AAPL",
            side=OrderSide.BUY,
            entry_price=Decimal("100"),
            entry_quantity=100,
            entry_time=datetime(2024, 1, 15),
            exit_price=Decimal("90"),
            exit_quantity=100,
            exit_time=datetime(2024, 1, 20),
        )
        log.add_trade(trade)
        assert log.total_trades == 1
        assert log.losing_trades == 1
        assert log.win_rate == Decimal("0")

    def test_mixed_trades(self):
        log = TradeLog()

        win_trade = Trade(
            ticker="AAPL",
            side=OrderSide.BUY,
            entry_price=Decimal("100"),
            entry_quantity=100,
            entry_time=datetime(2024, 1, 15),
            exit_price=Decimal("120"),
            exit_quantity=100,
            exit_time=datetime(2024, 1, 20),
        )
        log.add_trade(win_trade)

        loss_trade = Trade(
            ticker="GOOGL",
            side=OrderSide.BUY,
            entry_price=Decimal("100"),
            entry_quantity=100,
            entry_time=datetime(2024, 1, 15),
            exit_price=Decimal("90"),
            exit_quantity=100,
            exit_time=datetime(2024, 1, 20),
        )
        log.add_trade(loss_trade)

        assert log.total_trades == 2
        assert log.winning_trades == 1
        assert log.losing_trades == 1
        assert log.win_rate == Decimal("50")

    def test_gross_profit_loss(self):
        log = TradeLog()

        win_trade = Trade(
            ticker="AAPL",
            side=OrderSide.BUY,
            entry_price=Decimal("100"),
            entry_quantity=100,
            entry_time=datetime(2024, 1, 15),
            exit_price=Decimal("120"),
            exit_quantity=100,
            exit_time=datetime(2024, 1, 20),
        )
        log.add_trade(win_trade)

        loss_trade = Trade(
            ticker="GOOGL",
            side=OrderSide.BUY,
            entry_price=Decimal("100"),
            entry_quantity=100,
            entry_time=datetime(2024, 1, 15),
            exit_price=Decimal("90"),
            exit_quantity=100,
            exit_time=datetime(2024, 1, 20),
        )
        log.add_trade(loss_trade)

        assert log.gross_profit == Decimal("2000")
        assert log.gross_loss == Decimal("1000")
        assert log.profit_factor == Decimal("2")

    def test_avg_win_loss(self):
        log = TradeLog()

        for i in range(3):
            trade = Trade(
                ticker="AAPL",
                side=OrderSide.BUY,
                entry_price=Decimal("100"),
                entry_quantity=100,
                entry_time=datetime(2024, 1, 15),
                exit_price=Decimal("110"),
                exit_quantity=100,
                exit_time=datetime(2024, 1, 20),
            )
            log.add_trade(trade)

        assert log.avg_win == Decimal("1000")


class TestBacktestMetrics:
    def test_basic_metrics(self):
        metrics = BacktestMetrics(
            total_return=Decimal("10000"),
            total_return_percent=Decimal("10"),
            annualized_return=Decimal("15"),
            max_drawdown=Decimal("5000"),
            max_drawdown_percent=Decimal("5"),
            sharpe_ratio=Decimal("1.5"),
            total_trades=50,
            win_rate=Decimal("60"),
            start_equity=Decimal("100000"),
            end_equity=Decimal("110000"),
        )
        assert metrics.total_return_percent == Decimal("10")
        assert metrics.sharpe_ratio == Decimal("1.5")

    def test_to_summary_dict(self):
        metrics = BacktestMetrics(
            total_return=Decimal("10000"),
            total_return_percent=Decimal("10"),
            annualized_return=Decimal("15"),
            max_drawdown=Decimal("5000"),
            max_drawdown_percent=Decimal("5"),
            sharpe_ratio=Decimal("1.5"),
            sortino_ratio=Decimal("2.0"),
            volatility=Decimal("10"),
            annualized_volatility=Decimal("15"),
            total_trades=50,
            win_rate=Decimal("60"),
            profit_factor=Decimal("1.8"),
            total_commission=Decimal("500"),
            total_slippage=Decimal("200"),
            start_equity=Decimal("100000"),
            end_equity=Decimal("110000"),
        )
        summary = metrics.to_summary_dict()

        assert "Performance" in summary
        assert "Risk" in summary
        assert "Trading" in summary
        assert "Costs" in summary
        assert summary["Performance"]["Sharpe Ratio"] == "1.50"


class TestEquityCurvePoint:
    def test_equity_point(self):
        point = EquityCurvePoint(
            timestamp=datetime(2024, 1, 15),
            equity=Decimal("105000"),
            cash=Decimal("50000"),
            positions_value=Decimal("55000"),
            drawdown=Decimal("2000"),
            drawdown_percent=Decimal("1.9"),
        )
        assert point.equity == Decimal("105000")
        assert point.drawdown_percent == Decimal("1.9")


class TestBacktestResult:
    def test_backtest_result(self):
        config = BacktestConfig(
            tickers=["AAPL"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
        )
        metrics = BacktestMetrics(
            total_return=Decimal("10000"),
            total_return_percent=Decimal("10"),
            start_equity=Decimal("100000"),
            end_equity=Decimal("110000"),
        )
        trade_log = TradeLog(total_trades=10, winning_trades=6, losing_trades=4)

        result = BacktestResult(
            config=config,
            metrics=metrics,
            trade_log=trade_log,
            started_at=datetime(2024, 7, 1, 10, 0, 0),
            completed_at=datetime(2024, 7, 1, 10, 5, 30),
        )

        assert result.duration_seconds == 330.0
        assert result.status == BacktestStatus.COMPLETED

    def test_to_dict(self):
        config = BacktestConfig(
            name="Test Backtest",
            tickers=["AAPL"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
        )
        metrics = BacktestMetrics(
            total_return=Decimal("10000"),
            total_return_percent=Decimal("10"),
            start_equity=Decimal("100000"),
            end_equity=Decimal("110000"),
        )
        trade_log = TradeLog(total_trades=10, winning_trades=6, losing_trades=4)

        result = BacktestResult(
            config=config,
            metrics=metrics,
            trade_log=trade_log,
            started_at=datetime(2024, 7, 1, 10, 0, 0),
            completed_at=datetime(2024, 7, 1, 10, 5, 0),
        )

        result_dict = result.to_dict()
        assert result_dict["config"]["name"] == "Test Backtest"
        assert result_dict["trade_summary"]["total_trades"] == 10
        assert result_dict["trade_summary"]["win_rate"] == 60.0
