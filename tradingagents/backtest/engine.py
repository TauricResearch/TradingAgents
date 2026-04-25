# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Backtest engine that runs TradingAgentsGraph.propagate() at each rebalance
date and tracks positions to produce a BacktestResult."""

import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import yfinance as yf

from tradingagents.graph.trading_graph import TradingAgentsGraph

from .models import BacktestResult, PerformanceMetrics, TradeRecord
from .performance import PerformanceCalculator
from .state_utils import extract_reports, extract_debate, extract_risk

logger = logging.getLogger(__name__)


class BacktestEngine:
    """Runs a historical backtest by invoking the multi-agent trading pipeline
    at each rebalance date and tracking positions.

    Workflow per rebalance date:
      1. Fetch the closing price via yfinance.
      2. Call ``TradingAgentsGraph.propagate()`` to obtain BUY/SELL/HOLD.
      3. Manage position: BUY opens a new position (if flat), SELL closes an
         existing position, HOLD does nothing.
      4. At the end of the date range, any remaining open position is closed
         at the last available price.
      5. Performance metrics are computed by ``PerformanceCalculator``.
      6. Results are optionally saved as JSON to ``{results_dir}/backtest/``.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = config
        self._signal_cache: Dict[str, Dict[str, Any]] = {}
        self._calculator = PerformanceCalculator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        rebalance_freq: str = "monthly",
        benchmark: str = "SPY",
        initial_capital: float = 100_000.0,
        save_signals: bool = False,
        skip_llm: bool = False,
    ) -> BacktestResult:
        """Execute a full backtest over the given date range.

        Args:
            ticker: Stock ticker symbol (e.g. ``"NVDA"``).
            start_date: Start of backtest window (``"YYYY-MM-DD"``).
            end_date: End of backtest window (``"YYYY-MM-DD"``).
            rebalance_freq: One of ``"weekly"``, ``"biweekly"``, ``"monthly"``.
            benchmark: Benchmark ticker for alpha/beta (default ``"SPY"``).
            initial_capital: Starting portfolio value in USD.
            save_signals: If *True*, cache raw agent signals in
                ``self._signal_cache``.
            skip_llm: If *True*, skip ``TradingAgentsGraph`` creation and
                signal generation (useful for price-only testing).

        Returns:
            A :class:`BacktestResult` containing trades and metrics.
        """
        rebalance_dates = self._generate_rebalance_dates(
            start_date, end_date, rebalance_freq
        )

        if not rebalance_dates:
            logger.warning("No rebalance dates generated for %s -> %s", start_date, end_date)
            empty_metrics = self._calculator.calculate(
                [], initial_capital, benchmark, start_date, end_date
            )
            return BacktestResult(
                ticker=ticker,
                config_snapshot=self._config.copy(),
                start_date=start_date,
                end_date=end_date,
                benchmark=benchmark,
                trades=[],
                metrics=empty_metrics,
            )

        # Create the agent graph (unless skip_llm mode)
        graph: Optional[TradingAgentsGraph] = None
        if not skip_llm:
            graph = TradingAgentsGraph(self._config)

        trades: List[TradeRecord] = []
        open_trade: Optional[TradeRecord] = None
        capital = initial_capital

        for rebal_date in rebalance_dates:
            date_str = rebal_date.strftime("%Y-%m-%d")
            price = self._get_price_at_date(ticker, date_str)
            if price is None:
                logger.warning("No price data for %s on %s, skipping", ticker, date_str)
                continue

            # Get signal from the agent pipeline
            if graph is not None:
                state, signal = graph.propagate(ticker, date_str)
            elif skip_llm:
                signal = "HOLD"
                state = {}
            else:
                signal = "HOLD"
                state = {}

            signal = signal.upper().strip()
            if signal not in ("BUY", "SELL", "HOLD"):
                logger.warning("Unknown signal '%s' on %s, treating as HOLD", signal, date_str)
                signal = "HOLD"

            # Cache raw signals if requested
            if save_signals:
                self._signal_cache[date_str] = {
                    "signal": signal,
                    "state": state,
                    "price": price,
                }

            # Position management
            if signal == "BUY" and open_trade is None:
                # Calculate quantity: invest all available capital
                quantity = int(capital // price) if price > 0 else 0
                if quantity > 0:
                    open_trade = TradeRecord(
                        ticker=ticker,
                        trade_date=date_str,
                        signal="BUY",
                        entry_price=price,
                        quantity=quantity,
                        source="backtest",
                        analyst_reports=extract_reports(state),
                        debate_summary=extract_debate(state),
                        risk_decision=extract_risk(state),
                    )
                    logger.info(
                        "BUY %d shares of %s @ %.2f on %s",
                        quantity, ticker, price, date_str,
                    )

            elif signal == "SELL" and open_trade is not None:
                # Close the open position
                pnl = (price - open_trade.entry_price) * open_trade.quantity
                pnl_pct = (
                    ((price - open_trade.entry_price) / open_trade.entry_price) * 100
                    if open_trade.entry_price > 0
                    else 0.0
                )
                open_trade.exit_price = price
                open_trade.exit_date = date_str
                open_trade.pnl = round(pnl, 2)
                open_trade.pnl_pct = round(pnl_pct, 4)
                trades.append(open_trade)
                capital += pnl
                logger.info(
                    "SELL %d shares of %s @ %.2f on %s (PnL: %.2f)",
                    open_trade.quantity, ticker, price, date_str, pnl,
                )
                open_trade = None

            # HOLD or duplicate signal -> do nothing

        # Close any remaining open position at the last available price
        if open_trade is not None:
            last_date_str = rebalance_dates[-1].strftime("%Y-%m-%d")
            last_price = self._get_price_at_date(ticker, last_date_str)
            if last_price is None:
                last_price = open_trade.entry_price  # fallback

            pnl = (last_price - open_trade.entry_price) * open_trade.quantity
            pnl_pct = (
                ((last_price - open_trade.entry_price) / open_trade.entry_price) * 100
                if open_trade.entry_price > 0
                else 0.0
            )
            open_trade.exit_price = last_price
            open_trade.exit_date = last_date_str
            open_trade.pnl = round(pnl, 2)
            open_trade.pnl_pct = round(pnl_pct, 4)
            trades.append(open_trade)
            logger.info(
                "CLOSE remaining position: %d shares of %s @ %.2f on %s (PnL: %.2f)",
                open_trade.quantity, ticker, last_price, last_date_str, pnl,
            )

        # Calculate performance metrics
        metrics = self._calculator.calculate(
            trades, initial_capital, benchmark, start_date, end_date
        )

        result = BacktestResult(
            ticker=ticker,
            config_snapshot=self._config.copy(),
            start_date=start_date,
            end_date=end_date,
            benchmark=benchmark,
            trades=trades,
            metrics=metrics,
        )

        self._save_result(result)
        return result

    # ------------------------------------------------------------------
    # Rebalance date generation
    # ------------------------------------------------------------------

    def _generate_rebalance_dates(
        self, start: str, end: str, freq: str
    ) -> List[date]:
        """Generate a list of business-day-adjusted rebalance dates.

        Args:
            start: Start date string (``"YYYY-MM-DD"``).
            end: End date string (``"YYYY-MM-DD"``).
            freq: ``"weekly"``, ``"biweekly"``, or ``"monthly"``.

        Returns:
            Sorted list of :class:`datetime.date` objects.
        """
        start_dt = datetime.strptime(start, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end, "%Y-%m-%d").date()

        dates: List[date] = []

        if freq == "monthly":
            current = start_dt
            while current <= end_dt:
                dates.append(self._next_business_day(current))
                # Advance to 1st of next month
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1, day=1)
                else:
                    current = current.replace(month=current.month + 1, day=1)

        elif freq == "weekly":
            current = start_dt
            while current <= end_dt:
                dates.append(self._next_business_day(current))
                current += timedelta(weeks=1)

        elif freq == "biweekly":
            current = start_dt
            while current <= end_dt:
                dates.append(self._next_business_day(current))
                current += timedelta(weeks=2)

        else:
            raise ValueError(
                f"Unsupported rebalance frequency: {freq!r}. "
                f"Use 'weekly', 'biweekly', or 'monthly'."
            )

        # Remove duplicates and ensure within range
        seen = set()
        unique: List[date] = []
        for d in dates:
            if d not in seen and d <= end_dt:
                seen.add(d)
                unique.append(d)

        return sorted(unique)

    @staticmethod
    def _next_business_day(d: date) -> date:
        """Return *d* if it is a weekday, otherwise the next Monday."""
        while d.weekday() >= 5:  # Saturday=5, Sunday=6
            d += timedelta(days=1)
        return d

    # ------------------------------------------------------------------
    # Price fetching
    # ------------------------------------------------------------------

    def _get_price_at_date(self, ticker: str, date_str: str) -> Optional[float]:
        """Fetch the closing price for *ticker* on *date_str* using yfinance.

        Uses a 5-day lookback window to handle weekends and holidays.

        Returns:
            The closing price as a float, or *None* if no data is available.
        """
        try:
            target = datetime.strptime(date_str, "%Y-%m-%d").date()
            start = target - timedelta(days=5)
            end = target + timedelta(days=1)

            tk = yf.Ticker(ticker)
            hist = tk.history(
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
            )

            if hist.empty:
                return None

            close = hist["Close"]
            return float(close.iloc[-1])
        except Exception:
            logger.exception("Failed to fetch price for %s on %s", ticker, date_str)
            return None

    # ------------------------------------------------------------------
    # Result persistence
    # ------------------------------------------------------------------

    def _save_result(self, result: BacktestResult) -> None:
        """Write *result* as JSON to ``{results_dir}/backtest/``."""
        results_dir = self._config.get("results_dir", "./results")
        backtest_dir = os.path.join(results_dir, "backtest")

        try:
            os.makedirs(backtest_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{result.ticker}_{result.start_date}_{result.end_date}_{timestamp}.json"
            filepath = os.path.join(backtest_dir, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, indent=2, default=str)

            logger.info("Backtest result saved to %s", filepath)
        except Exception:
            logger.exception("Failed to save backtest result")
