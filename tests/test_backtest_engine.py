import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from back_test.engine import BacktestEngine


class StaticPriceBacktestEngine(BacktestEngine):
    def __init__(self, *args, prices: pd.DataFrame, index_prices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._prices = prices
        self._index_prices = index_prices or {}

    def load_prices(self) -> pd.DataFrame:
        return self._prices.copy()

    def load_index_context_prices(self, _effective_end_date):
        return {ticker: df.copy() for ticker, df in self._index_prices.items()}


def write_strategy(strategy_dir, ticker, trade_date, **overrides):
    strategy = {
        "schema_version": "v3",
        "ticker": ticker,
        "as_of_date": trade_date,
        "valid_until": trade_date,
        "action": "BUY",
        "entry": {"price": 10.0, "size_pct": 100.0},
        "add_position": {"price": None, "size_pct": 0.0},
        "take_profit": {"price": 12.0, "size_pct": 100.0},
        "reduce_stop": {"price": None, "size_pct": 0.0},
        "stop_loss": {"price": 8.0},
        "rationale_summary": "test",
    }
    strategy.update(overrides)
    path = strategy_dir / f"{ticker}_{trade_date}.json"
    path.write_text(json.dumps(strategy), encoding="utf-8")
    return path


class BacktestEngineTest(unittest.TestCase):
    def test_valid_until_expires_pending_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            write_strategy(
                strategy_dir,
                ticker,
                "2025-01-01",
                valid_until="2025-01-02",
                entry={"price": 10.0, "size_pct": 100.0},
            )
            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-01"), "Open": 11.0, "High": 11.0, "Low": 11.0, "Close": 11.0},
                    {"Date": pd.Timestamp("2025-01-02"), "Open": 11.0, "High": 11.0, "Low": 11.0, "Close": 11.0},
                    {"Date": pd.Timestamp("2025-01-03"), "Open": 11.0, "High": 12.0, "Low": 9.0, "Close": 10.0},
                ]
            )

            result = StaticPriceBacktestEngine(
                ticker,
                "2025-01-01",
                "2025-01-03",
                initial_capital=100.0,
                strategies_dir=strategy_dir,
                prices=prices,
            ).run()

        self.assertEqual(result.trades, [])
        self.assertEqual(result.equity_curve["Position"].tolist(), [0.0, 0.0, 0.0])
        self.assertEqual(result.equity_curve["Equity"].tolist(), [100.0, 100.0, 100.0])

    def test_new_entry_does_not_exit_on_same_day_touch(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            write_strategy(
                strategy_dir,
                ticker,
                "2025-01-01",
                valid_until="2025-01-02",
                entry={"price": 10.0, "size_pct": 100.0},
                take_profit={"price": 12.0, "size_pct": 100.0},
                stop_loss={"price": 8.0},
            )
            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-01"), "Open": 10.0, "High": 15.0, "Low": 7.0, "Close": 11.0},
                    {"Date": pd.Timestamp("2025-01-02"), "Open": 10.0, "High": 15.0, "Low": 7.0, "Close": 11.0},
                ]
            )

            result = StaticPriceBacktestEngine(
                ticker,
                "2025-01-01",
                "2025-01-02",
                initial_capital=100.0,
                strategies_dir=strategy_dir,
                prices=prices,
            ).run()

        self.assertEqual(result.equity_curve["Position"].tolist(), [0.0, 10.0])
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0]["reason"], "end_of_backtest")
        self.assertEqual(result.trades[0]["exit_price"], 11.0)
        self.assertEqual(result.executions[0]["signal_date"], "2025-01-01")
        self.assertEqual(result.executions[0]["fill_date"], "2025-01-02")
        self.assertEqual(result.report["bias_audit"]["event_timing"]["same_bar_signal_fills"], 0)

    def test_trade_route_records_stock_and_index_context_on_fills(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            write_strategy(
                strategy_dir,
                ticker,
                "2025-01-01",
                valid_until="2025-01-02",
                entry={"price": 10.0, "size_pct": 100.0},
                take_profit={"price": 12.0, "size_pct": 100.0},
                stop_loss={"price": 8.0},
            )
            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-01"), "Open": 10.0, "High": 15.0, "Low": 7.0, "Close": 11.0, "Volume": 1000},
                    {"Date": pd.Timestamp("2025-01-02"), "Open": 10.0, "High": 15.0, "Low": 7.0, "Close": 11.0, "Volume": 1100},
                ]
            )
            index_prices = {
                "^GSPC": pd.DataFrame(
                    [
                        {"Date": pd.Timestamp("2025-01-01"), "Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 2000},
                        {"Date": pd.Timestamp("2025-01-02"), "Open": 101.0, "High": 102.0, "Low": 100.0, "Close": 101.5, "Volume": 2100},
                    ]
                )
            }

            result = StaticPriceBacktestEngine(
                ticker,
                "2025-01-01",
                "2025-01-02",
                initial_capital=100.0,
                strategies_dir=strategy_dir,
                prices=prices,
                index_prices=index_prices,
            ).run()

        fill_context = result.executions[0]["fill_price_context"]
        self.assertEqual(fill_context["stock"]["date"], "2025-01-02")
        self.assertEqual(fill_context["stock"]["open"], 10.0)
        self.assertEqual(fill_context["indices"]["^GSPC"]["close"], 101.5)
        self.assertEqual(result.trades[0]["entry_price_context"]["stock"]["date"], "2025-01-02")
        self.assertEqual(result.trades[0]["exit_price_context"]["indices"]["^GSPC"]["close"], 101.5)

    def test_hold_strategy_with_entry_places_pending_buy(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            write_strategy(
                strategy_dir,
                ticker,
                "2025-01-01",
                valid_until="2025-01-02",
                action="HOLD",
                entry={"price": 10.0, "size_pct": 50.0},
                take_profit={"price": 13.0, "size_pct": 100.0},
                stop_loss={"price": 8.0},
            )
            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-01"), "Open": 11.0, "High": 11.0, "Low": 11.0, "Close": 11.0},
                    {"Date": pd.Timestamp("2025-01-02"), "Open": 11.0, "High": 12.0, "Low": 10.0, "Close": 12.0},
                ]
            )

            result = StaticPriceBacktestEngine(
                ticker,
                "2025-01-01",
                "2025-01-02",
                initial_capital=100.0,
                strategies_dir=strategy_dir,
                prices=prices,
            ).run()

        self.assertEqual(result.equity_curve["Position"].tolist(), [0.0, 5.0])
        self.assertEqual(result.equity_curve["Cash"].tolist(), [100.0, 50.0])
        self.assertEqual(result.trades[0]["reason"], "end_of_backtest")
        self.assertEqual(result.trades[0]["exit_price"], 12.0)

    def test_market_entry_defaults_to_next_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            write_strategy(
                strategy_dir,
                ticker,
                "2025-01-01",
                valid_until="2025-01-02",
                action="BUY",
                entry={"price": None, "size_pct": 50.0},
                take_profit={"price": None, "size_pct": 0.0},
                stop_loss={"price": None},
            )
            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-01"), "Open": 10.0, "High": 10.0, "Low": 10.0, "Close": 99.0},
                    {"Date": pd.Timestamp("2025-01-02"), "Open": 12.0, "High": 13.0, "Low": 11.0, "Close": 13.0},
                ]
            )

            result = StaticPriceBacktestEngine(
                ticker,
                "2025-01-01",
                "2025-01-02",
                initial_capital=120.0,
                strategies_dir=strategy_dir,
                prices=prices,
            ).run()

        self.assertEqual(result.executions[0]["fill_basis"], "next_open")
        self.assertEqual(result.executions[0]["raw_fill_price"], 12.0)
        self.assertEqual(result.equity_curve["Position"].tolist(), [0.0, 5.0])

    def test_new_strategy_updates_existing_position_risk_levels(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            write_strategy(
                strategy_dir,
                ticker,
                "2024-12-31",
                valid_until="2025-01-06",
                action="BUY",
                entry={"price": 10.0, "size_pct": 100.0},
                take_profit={"price": 20.0, "size_pct": 100.0},
                stop_loss={"price": 5.0},
            )
            write_strategy(
                strategy_dir,
                ticker,
                "2025-01-01",
                valid_until="2025-01-02",
                action="HOLD",
                entry={"price": None, "size_pct": 0.0},
                take_profit={"price": 12.0, "size_pct": 100.0},
                stop_loss={"price": 8.0},
            )
            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-01"), "Open": 10.0, "High": 11.0, "Low": 10.0, "Close": 10.0},
                    {"Date": pd.Timestamp("2025-01-02"), "Open": 10.0, "High": 12.5, "Low": 9.0, "Close": 12.0},
                ]
            )

            result = StaticPriceBacktestEngine(
                ticker,
                "2025-01-01",
                "2025-01-02",
                initial_capital=100.0,
                strategies_dir=strategy_dir,
                prices=prices,
            ).run()

        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0]["reason"], "take_profit")
        self.assertEqual(result.trades[0]["exit_price"], 12.0)
        self.assertEqual(result.equity_curve["Position"].tolist(), [10.0, 0.0])

    def test_add_position_increases_existing_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            write_strategy(
                strategy_dir,
                ticker,
                "2024-12-31",
                valid_until="2025-01-06",
                action="BUY",
                entry={"price": 10.0, "size_pct": 50.0},
                stop_loss={"price": 7.0},
            )
            write_strategy(
                strategy_dir,
                ticker,
                "2025-01-01",
                valid_until="2025-01-02",
                action="HOLD",
                entry={"price": None, "size_pct": 0.0},
                add_position={"price": 8.0, "size_pct": 50.0},
                take_profit={"price": None, "size_pct": 0.0},
                stop_loss={"price": 6.0},
            )
            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-01"), "Open": 10.0, "High": 10.0, "Low": 10.0, "Close": 10.0},
                    {"Date": pd.Timestamp("2025-01-02"), "Open": 9.0, "High": 9.0, "Low": 8.0, "Close": 8.0},
                ]
            )

            result = StaticPriceBacktestEngine(
                ticker,
                "2025-01-01",
                "2025-01-02",
                initial_capital=100.0,
                strategies_dir=strategy_dir,
                prices=prices,
            ).run()

        # Equity-based sizing: at add time equity = cash 50 + 5 shares * 8 = 90.
        # Spend = min(cash 50, 90 * 50%) = 45 → 45/8 = 5.625 added shares.
        self.assertEqual(result.equity_curve["Position"].tolist(), [5.0, 10.625])
        self.assertEqual(result.equity_curve["Cash"].tolist(), [50.0, 5.0])

    def test_take_profit_partially_sells_existing_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            write_strategy(
                strategy_dir,
                ticker,
                "2024-12-31",
                valid_until="2025-01-06",
                action="BUY",
                entry={"price": 10.0, "size_pct": 100.0},
                stop_loss={"price": 5.0},
            )
            write_strategy(
                strategy_dir,
                ticker,
                "2025-01-01",
                valid_until="2025-01-02",
                action="HOLD",
                entry={"price": None, "size_pct": 0.0},
                add_position={"price": None, "size_pct": 0.0},
                take_profit={"price": 12.0, "size_pct": 40.0},
                stop_loss={"price": 5.0},
            )
            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-01"), "Open": 10.0, "High": 10.0, "Low": 10.0, "Close": 10.0},
                    {"Date": pd.Timestamp("2025-01-02"), "Open": 11.0, "High": 12.0, "Low": 11.0, "Close": 11.0},
                ]
            )

            result = StaticPriceBacktestEngine(
                ticker,
                "2025-01-01",
                "2025-01-02",
                initial_capital=100.0,
                strategies_dir=strategy_dir,
                prices=prices,
            ).run()

        self.assertEqual(result.equity_curve["Position"].tolist(), [10.0, 6.0])
        self.assertEqual(len(result.trades), 2)
        self.assertEqual(result.trades[0]["reason"], "take_profit")
        self.assertEqual(result.trades[0]["shares"], 4.0)

    def test_reduce_stop_partially_sells_on_price_drop(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            write_strategy(
                strategy_dir,
                ticker,
                "2024-12-31",
                valid_until="2025-01-06",
                action="BUY",
                entry={"price": 10.0, "size_pct": 100.0},
                stop_loss={"price": 5.0},
            )
            write_strategy(
                strategy_dir,
                ticker,
                "2025-01-01",
                valid_until="2025-01-02",
                action="HOLD",
                entry={"price": None, "size_pct": 0.0},
                add_position={"price": None, "size_pct": 0.0},
                take_profit={"price": None, "size_pct": 0.0},
                reduce_stop={"price": 8.0, "size_pct": 25.0},
                stop_loss={"price": 5.0},
            )
            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-01"), "Open": 10.0, "High": 10.0, "Low": 10.0, "Close": 10.0},
                    {"Date": pd.Timestamp("2025-01-02"), "Open": 9.0, "High": 9.5, "Low": 7.5, "Close": 8.5},
                ]
            )

            result = StaticPriceBacktestEngine(
                ticker,
                "2025-01-01",
                "2025-01-02",
                initial_capital=100.0,
                strategies_dir=strategy_dir,
                prices=prices,
            ).run()

        # 25% of 10 shares trimmed at 8.0 (limit_touch since open 9.0 > 8.0).
        self.assertEqual(result.equity_curve["Position"].tolist(), [10.0, 7.5])
        self.assertEqual(len(result.trades), 2)
        self.assertEqual(result.trades[0]["reason"], "reduce_stop")
        self.assertEqual(result.trades[0]["shares"], 2.5)
        self.assertEqual(result.trades[0]["raw_exit_price"], 8.0)
        self.assertEqual(result.executions[1]["fill_basis"], "reduce_stop_touch")

    def test_stop_loss_takes_priority_over_reduce_stop_same_bar(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            write_strategy(
                strategy_dir,
                ticker,
                "2024-12-31",
                valid_until="2025-01-06",
                action="BUY",
                entry={"price": 10.0, "size_pct": 100.0},
                stop_loss={"price": 7.0},
            )
            write_strategy(
                strategy_dir,
                ticker,
                "2025-01-01",
                valid_until="2025-01-02",
                action="HOLD",
                entry={"price": None, "size_pct": 0.0},
                add_position={"price": None, "size_pct": 0.0},
                take_profit={"price": None, "size_pct": 0.0},
                reduce_stop={"price": 8.0, "size_pct": 50.0},
                stop_loss={"price": 7.0},
            )
            # Day 2 gaps below both reduce_stop and stop_loss.
            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-01"), "Open": 10.0, "High": 10.0, "Low": 10.0, "Close": 10.0},
                    {"Date": pd.Timestamp("2025-01-02"), "Open": 6.5, "High": 7.0, "Low": 6.0, "Close": 6.5},
                ]
            )

            result = StaticPriceBacktestEngine(
                ticker,
                "2025-01-01",
                "2025-01-02",
                initial_capital=100.0,
                strategies_dir=strategy_dir,
                prices=prices,
            ).run()

        # Stop runs first and closes 100% of the position; reduce_stop never fires.
        self.assertEqual(result.equity_curve["Position"].tolist(), [10.0, 0.0])
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0]["reason"], "stop_loss")

    def test_legacy_v2_reduce_position_is_migrated_to_take_profit(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            # Two unversioned strategies use the v2 `reduce_position` field.
            write_strategy(
                strategy_dir,
                ticker,
                "2024-12-31",
                valid_until="2025-01-06",
                schema_version=None,
                action="BUY",
                entry={"price": 10.0, "size_pct": 100.0},
                reduce_position={"price": None, "size_pct": 0.0},
                stop_loss={"price": 5.0},
                take_profit=None,
                reduce_stop=None,
            )
            write_strategy(
                strategy_dir,
                ticker,
                "2025-01-01",
                valid_until="2025-01-02",
                schema_version="v2",
                action="HOLD",
                entry={"price": None, "size_pct": 0.0},
                add_position={"price": None, "size_pct": 0.0},
                reduce_position={"price": 12.0, "size_pct": 40.0},
                stop_loss={"price": 5.0},
                take_profit=None,
                reduce_stop=None,
            )
            # Strip the take_profit/reduce_stop defaults injected by write_strategy
            # so the on-disk file mimics a real v2 document.
            for path in strategy_dir.glob("TEST_*.json"):
                with open(path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                payload.pop("take_profit", None)
                payload.pop("reduce_stop", None)
                if payload.get("schema_version") is None:
                    payload.pop("schema_version", None)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(payload, f)

            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-01"), "Open": 10.0, "High": 10.0, "Low": 10.0, "Close": 10.0},
                    {"Date": pd.Timestamp("2025-01-02"), "Open": 11.0, "High": 12.0, "Low": 11.0, "Close": 11.0},
                ]
            )

            result = StaticPriceBacktestEngine(
                ticker,
                "2025-01-01",
                "2025-01-02",
                initial_capital=100.0,
                strategies_dir=strategy_dir,
                prices=prices,
            ).run()

        self.assertEqual(result.trades[0]["reason"], "take_profit")
        self.assertEqual(result.trades[0]["shares"], 4.0)
        self.assertEqual(result.report["schema_migrations"], 2)

    def test_sell_strategy_clears_conflicting_entry_orders(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            write_strategy(
                strategy_dir,
                ticker,
                "2025-01-01",
                valid_until="2025-01-02",
                action="SELL",
                entry={"price": 10.0, "size_pct": 50.0},
                add_position={"price": 9.0, "size_pct": 50.0},
                take_profit={"price": 12.0, "size_pct": 100.0},
            )
            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-01"), "Open": 10.0, "High": 11.0, "Low": 9.0, "Close": 10.0},
                    {"Date": pd.Timestamp("2025-01-02"), "Open": 10.0, "High": 11.0, "Low": 9.0, "Close": 10.0},
                ]
            )

            result = StaticPriceBacktestEngine(
                ticker,
                "2025-01-01",
                "2025-01-02",
                initial_capital=100.0,
                strategies_dir=strategy_dir,
                prices=prices,
            ).run()

        self.assertEqual(result.trades, [])
        self.assertEqual(result.equity_curve["Position"].tolist(), [0.0, 0.0])
        self.assertEqual(result.report["invalid_sell_orders"], 1)

    def test_effective_window_uses_first_and_last_trading_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            write_strategy(
                strategy_dir,
                ticker,
                "2025-01-06",
                valid_until="2025-01-10",
                action="HOLD",
                entry={"price": None, "size_pct": 0.0},
            )
            write_strategy(
                strategy_dir,
                ticker,
                "2025-01-11",
                valid_until="2025-01-11",
                action="HOLD",
                entry={"price": None, "size_pct": 0.0},
            )
            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-06"), "Open": 10.0, "High": 10.0, "Low": 10.0, "Close": 10.0},
                    {"Date": pd.Timestamp("2025-01-10"), "Open": 11.0, "High": 11.0, "Low": 11.0, "Close": 11.0},
                ]
            )

            result = StaticPriceBacktestEngine(
                ticker,
                "2025-01-04",
                "2025-01-11",
                initial_capital=100.0,
                strategies_dir=strategy_dir,
                prices=prices,
            ).run()

        self.assertEqual(result.effective_start_date, "2025-01-06")
        self.assertEqual(result.effective_end_date, "2025-01-10")
        self.assertEqual(result.strategies_loaded, 1)
        self.assertEqual(result.equity_curve["Date"].dt.strftime("%Y-%m-%d").tolist(), ["2025-01-06", "2025-01-10"])


    def test_reduce_stop_size_pct_is_capped(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            write_strategy(
                strategy_dir, ticker, "2024-12-31",
                valid_until="2025-01-06",
                action="BUY",
                entry={"price": 10.0, "size_pct": 100.0},
                stop_loss={"price": 5.0},
            )
            write_strategy(
                strategy_dir, ticker, "2025-01-01",
                valid_until="2025-01-02",
                action="HOLD",
                entry={"price": None, "size_pct": 0.0},
                add_position={"price": None, "size_pct": 0.0},
                take_profit={"price": None, "size_pct": 0.0},
                reduce_stop={"price": 8.0, "size_pct": 70.0},
                stop_loss={"price": 5.0},
            )
            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-01"), "Open": 10.0, "High": 10.0, "Low": 10.0, "Close": 10.0},
                    {"Date": pd.Timestamp("2025-01-02"), "Open": 9.0, "High": 9.5, "Low": 7.5, "Close": 8.5},
                ]
            )

            result = StaticPriceBacktestEngine(
                ticker, "2025-01-01", "2025-01-02",
                initial_capital=100.0, strategies_dir=strategy_dir, prices=prices,
            ).run()

        # 70% requested → capped at REDUCE_STOP_MAX_SIZE_PCT (30%).
        self.assertEqual(result.trades[0]["reason"], "reduce_stop")
        self.assertAlmostEqual(result.trades[0]["shares"], 3.0)
        self.assertEqual(result.report["reduce_stop_capped"], 1)

    def test_entry_with_existing_position_is_promoted_to_add(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            write_strategy(
                strategy_dir, ticker, "2024-12-31",
                valid_until="2025-01-06",
                action="BUY",
                entry={"price": 10.0, "size_pct": 50.0},
                stop_loss={"price": 5.0},
            )
            # LLM-style mistake: ships a fresh "entry" while a position already exists.
            write_strategy(
                strategy_dir, ticker, "2025-01-01",
                valid_until="2025-01-02",
                action="BUY",
                entry={"price": 9.0, "size_pct": 30.0},
                add_position={"price": None, "size_pct": 0.0},
                take_profit={"price": None, "size_pct": 0.0},
                stop_loss={"price": 6.0},
            )
            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-01"), "Open": 10.0, "High": 10.0, "Low": 10.0, "Close": 10.0},
                    {"Date": pd.Timestamp("2025-01-02"), "Open": 9.0, "High": 9.0, "Low": 8.5, "Close": 9.0},
                ]
            )

            result = StaticPriceBacktestEngine(
                ticker, "2025-01-01", "2025-01-02",
                initial_capital=100.0, strategies_dir=strategy_dir, prices=prices,
            ).run()

        # Day1: entry 50% → 5 shares @ $10, cash $50, equity $50.
        # Day2: entry-promoted-to-add 30% of equity (50+5*9=95) → spend min(50, 28.5)=28.5
        #       → 28.5/9 = 3.166... added shares.
        self.assertEqual(result.report["entry_promoted_to_add"], 1)
        self.assertGreater(result.equity_curve["Position"].tolist()[1], 5.0)

    def test_take_profit_below_cost_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            write_strategy(
                strategy_dir, ticker, "2024-12-31",
                valid_until="2025-01-06",
                action="BUY",
                entry={"price": 10.0, "size_pct": 100.0},
                stop_loss={"price": 5.0},
            )
            write_strategy(
                strategy_dir, ticker, "2025-01-01",
                valid_until="2025-01-02",
                action="HOLD",
                entry={"price": None, "size_pct": 0.0},
                add_position={"price": None, "size_pct": 0.0},
                take_profit={"price": 9.0, "size_pct": 50.0},  # below cost basis $10
                stop_loss={"price": 5.0},
            )
            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-01"), "Open": 10.0, "High": 10.0, "Low": 10.0, "Close": 10.0},
                    {"Date": pd.Timestamp("2025-01-02"), "Open": 9.5, "High": 9.5, "Low": 9.0, "Close": 9.5},
                ]
            )

            result = StaticPriceBacktestEngine(
                ticker, "2025-01-01", "2025-01-02",
                initial_capital=100.0, strategies_dir=strategy_dir, prices=prices,
            ).run()

        # TP at $9 below entry $10 → blocked, no take_profit fill.
        self.assertEqual(result.report["tp_below_cost_blocked"], 1)
        non_eob = [t for t in result.trades if t["reason"] != "end_of_backtest"]
        self.assertEqual(non_eob, [])

    def test_take_profit_downgrade_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            # Strategy 1: opens the position on day 1 (no pending TP yet — engine
            # only builds TP orders once a position exists).
            write_strategy(
                strategy_dir, ticker, "2024-12-31",
                valid_until="2025-01-01",
                action="BUY",
                entry={"price": 10.0, "size_pct": 100.0},
                stop_loss={"price": 5.0},
            )
            # Strategy 2: with position now open, registers a pending TP at 15.
            write_strategy(
                strategy_dir, ticker, "2025-01-01",
                valid_until="2025-01-02",
                action="HOLD",
                entry={"price": None, "size_pct": 0.0},
                add_position={"price": None, "size_pct": 0.0},
                take_profit={"price": 15.0, "size_pct": 100.0},
                stop_loss={"price": 5.0},
            )
            # Strategy 3: weekly rotation tries to lower TP from 15 → 12.
            write_strategy(
                strategy_dir, ticker, "2025-01-02",
                valid_until="2025-01-08",
                action="HOLD",
                entry={"price": None, "size_pct": 0.0},
                add_position={"price": None, "size_pct": 0.0},
                take_profit={"price": 12.0, "size_pct": 100.0},
                stop_loss={"price": 5.0},
            )
            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-01"), "Open": 10.0, "High": 10.0, "Low": 10.0, "Close": 10.0},
                    {"Date": pd.Timestamp("2025-01-02"), "Open": 11.0, "High": 11.0, "Low": 10.5, "Close": 11.0},
                    {"Date": pd.Timestamp("2025-01-03"), "Open": 12.5, "High": 13.0, "Low": 12.5, "Close": 13.0},
                ]
            )

            result = StaticPriceBacktestEngine(
                ticker, "2025-01-01", "2025-01-03",
                initial_capital=100.0, strategies_dir=strategy_dir, prices=prices,
            ).run()

        # 12 < 15 → new TP rejected, original TP=15 remains, never fires in this window.
        self.assertEqual(result.report["tp_downgrades_blocked"], 1)
        non_eob = [t for t in result.trades if t["reason"] != "end_of_backtest"]
        self.assertEqual(non_eob, [])

    def test_min_stop_distance_widens_tight_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_dir = Path(tmp)
            ticker = "TEST"
            # Stop at 9.9 is only 1% below entry $10; with min_stop_distance_pct=2.5%
            # it should be widened to 9.75.
            write_strategy(
                strategy_dir, ticker, "2024-12-31",
                valid_until="2025-01-06",
                action="BUY",
                entry={"price": 10.0, "size_pct": 100.0},
                stop_loss={"price": 9.9},
            )
            prices = pd.DataFrame(
                [
                    {"Date": pd.Timestamp("2025-01-01"), "Open": 10.0, "High": 10.0, "Low": 10.0, "Close": 10.0},
                    # Day2 dips to 9.85: tight stop at 9.9 would fire, widened stop at 9.75 holds.
                    {"Date": pd.Timestamp("2025-01-02"), "Open": 9.95, "High": 10.0, "Low": 9.85, "Close": 9.95},
                ]
            )

            result = StaticPriceBacktestEngine(
                ticker, "2025-01-01", "2025-01-02",
                initial_capital=100.0, strategies_dir=strategy_dir, prices=prices,
                min_stop_distance_pct=0.025,
            ).run()

        self.assertEqual(result.report["stop_widened"], 1)
        # Stop did not fire — only the end_of_backtest mark remains.
        reasons = [t["reason"] for t in result.trades]
        self.assertNotIn("stop_loss", reasons)


if __name__ == "__main__":
    unittest.main()
