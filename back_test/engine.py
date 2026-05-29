"""Backtest engine.

Reads `back_test/strategy/{ticker}/{ticker}_*.json` weekly strategy files and replays them on
historical daily OHLCV using limit-order semantics.

Order semantics:
- Entry / add-position at price X: when daily Low <= X, fill at Open if
  Open <= X (gap-through), otherwise X.
- Take-profit at price Y (sell-on-rise): when daily High >= Y, fill at Open if
  Open >= Y, otherwise Y. size_pct=100 turns this into a full take-profit close.
- Reduce-stop at price R (partial sell-on-drop): when daily Low <= R, fill at
  Open if Open <= R, otherwise R. Sells `size_pct%` of the current shares.
- Stop-loss at price Z (full sell-on-drop): when daily Low <= Z, fill at Open
  if Open <= Z, otherwise Z. Always closes 100%.

Per-bar evaluation order: stop_loss -> reduce_stop -> take_profit -> entry/add.

Strategy lifecycle:
- Each weekly strategy is "active" from the next trading day after its
  `as_of_date` until its `valid_until`, the next strategy's active date, or
  backtest end, whichever comes first.
- When a new strategy activates, any UNFILLED entry / add / take_profit /
  reduce_stop orders from the prior strategy are cancelled. Already-filled
  positions may receive new add / take_profit / reduce_stop / stop_loss
  instructions from the active strategy.
- BUY/HOLD actions can issue entry or add-position orders when the respective
  price and size_pct fields are provided.
- SELL action with no current position is a no-op; with a position it issues
  immediate market-close on the next trading day's open.

Schema migration: legacy v1 (`take_profit`) and v2 (`reduce_position`) files
are migrated to v3 at load time. Both are mapped onto the v3 `take_profit`
field, since their fill semantics (sell-on-rise) match.

Reuses `tradingagents.dataflows.stockstats_utils.load_ohlcv` for both ticker
and ^IXIC benchmark data fetches.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import pandas as pd

from back_test.calendar import adjust_backtest_window, normalize_trading_days
from tradingagents.dataflows.stockstats_utils import load_ohlcv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STRATEGIES_ROOT = PROJECT_ROOT / "back_test" / "strategy"
SCHEMA_VERSION = "v3"
INDEX_CONTEXT_TICKERS = ("^GSPC", "^IXIC")


@dataclass
class Position:
    """A filled position waiting to be exited."""
    entry_date: str
    entry_price: float
    shares: float
    stop_loss: Optional[float] = None
    stop_loss_as_of: Optional[str] = None
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None  # realized $
    entry_commission: float = 0.0


@dataclass
class PendingOrder:
    """An unfilled parameter-driven order from the active strategy."""
    order_type: str  # entry, add, take_profit, reduce_stop
    strategy_as_of: str
    limit_price: Optional[float]
    size_pct: float
    stop_loss: Optional[float]


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame   # Date, Equity, Cash, Position, MarkPrice
    trades: List[dict]
    executions: List[dict]
    strategies_loaded: int
    effective_start_date: Optional[str] = None
    effective_end_date: Optional[str] = None
    report: Optional[dict] = None
    final_cash: Optional[float] = None
    final_position: Optional[dict] = None
    # Orders still unfilled at the end of the replay window, tagged by the
    # strategy_as_of date they originated from. Consumed by the iterative
    # backtest loop to feed prior-strategy unfilled orders into the next
    # decision cycle.
    final_pending_orders: List[dict] = None


class BacktestEngine:
    REDUCE_STOP_MAX_SIZE_PCT = 30.0

    def __init__(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        initial_capital: float = 1_000_000.0,
        strategies_dir: Optional[Path] = None,
        commission: float = 0.0,
        slippage_bps: float = 0.0,
        min_stop_distance_pct: float = 0.0,
    ):
        self.ticker = ticker
        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)
        self.initial_capital = initial_capital
        self.strategies_dir = strategies_dir or STRATEGIES_ROOT / ticker
        self.commission = float(commission)
        self.slippage_bps = float(slippage_bps)
        self.min_stop_distance_pct = float(min_stop_distance_pct)
        self.extraction_failures = 0
        self.schema_migrations = 0
        self.schema_rejections = 0
        self.invalid_sell_orders = 0
        self.reduce_stop_capped = 0
        self.entry_promoted_to_add = 0
        self.tp_below_cost_blocked = 0
        self.tp_downgrades_blocked = 0
        self.tp_upgrades_applied = 0
        self.stop_widened = 0
        self.stop_downgrades_blocked = 0
        self.stop_upgrades_applied = 0

    # ----------------------------------------------------------- load helpers
    def load_strategies(self) -> List[dict]:
        """Load all `{ticker}_*.json` strategies, sorted by as_of_date."""
        pattern = f"{self.ticker}_*.json"
        strategies = []
        self.extraction_failures = 0
        self.schema_migrations = 0
        self.schema_rejections = 0
        self.invalid_sell_orders = 0
        for path in sorted(self.strategies_dir.glob(pattern)):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "error" in data:
                # Skip extraction-failed entries but keep going.
                self.extraction_failures += 1
                continue
            if "as_of_date" not in data:
                continue
            data = self._normalize_strategy_schema(data)
            if data is None:
                self.schema_rejections += 1
                continue
            strategies.append(data)
        strategies.sort(key=lambda s: s["as_of_date"])
        return [
            s for s in strategies
            if pd.to_datetime(s["as_of_date"]) <= self.end_date
        ]

    def load_prices(self) -> pd.DataFrame:
        """Daily OHLCV filtered to the effective trading-day window.

        Returns an empty DataFrame (preserving columns) if the requested
        window contains no trading days, so callers can short-circuit instead
        of needing to catch ValueError.
        """
        df = load_ohlcv(self.ticker, self.end_date.strftime("%Y-%m-%d"))
        try:
            effective_start, effective_end = adjust_backtest_window(
                df["Date"],
                self.start_date.strftime("%Y-%m-%d"),
                self.end_date.strftime("%Y-%m-%d"),
            )
        except ValueError:
            return df.iloc[0:0].reset_index(drop=True)
        start = pd.to_datetime(effective_start)
        end = pd.to_datetime(effective_end)
        df = df[(df["Date"] >= start) & (df["Date"] <= end)]
        return df.sort_values("Date").reset_index(drop=True)

    def load_index_context_prices(
        self,
        effective_start_date: Optional[str],
        effective_end_date: Optional[str],
    ) -> dict[str, pd.DataFrame]:
        """Load index OHLCV used only to annotate trade_route output."""
        if (
            self.ticker.upper() == "TEST"
            or effective_start_date is None
            or effective_end_date is None
        ):
            return {}
        start = pd.to_datetime(effective_start_date)
        end = pd.to_datetime(effective_end_date)
        index_prices: dict[str, pd.DataFrame] = {}
        for ticker in INDEX_CONTEXT_TICKERS:
            try:
                df = load_ohlcv(ticker, end.strftime("%Y-%m-%d"))
            except Exception:
                continue
            if df.empty:
                continue
            df = df[(df["Date"] >= start) & (df["Date"] <= end)]
            index_prices[ticker] = df.sort_values("Date").reset_index(drop=True)
        return index_prices

    # ----------------------------------------------------------- main loop
    def run(self) -> BacktestResult:
        prices = self.load_prices()
        if prices.empty:
            return BacktestResult(
                equity_curve=pd.DataFrame(
                    columns=["Date", "Equity", "Cash", "Position", "MarkPrice"]
                ),
                trades=[],
                executions=[],
                strategies_loaded=0,
                effective_start_date=None,
                effective_end_date=None,
                report=None,
                final_cash=self.initial_capital,
                final_position=None,
                final_pending_orders=[],
            )

        effective_start_date = prices.iloc[0]["Date"].strftime("%Y-%m-%d")
        effective_end_date = prices.iloc[-1]["Date"].strftime("%Y-%m-%d")
        effective_end = pd.to_datetime(effective_end_date)

        strategies = [
            s for s in self.load_strategies()
            if pd.to_datetime(s["as_of_date"]) <= effective_end
        ]

        cash = self.initial_capital
        position: Optional[Position] = None
        pending_orders: List[PendingOrder] = []
        trades: List[dict] = []
        executions: List[dict] = []
        orders_created = 0
        expired_orders = 0

        # Map each strategy to its effective active window. valid_until is the
        # strategy's real expiry. A newer strategy can replace same-type
        # pending orders, but it no longer cancels every older pending order
        # just because the weekly review rotated.
        trading_days = normalize_trading_days(prices["Date"])
        for strat in strategies:
            strat["_active_from"] = self._next_trading_day(trading_days, strat["as_of_date"])

        strategies = [s for s in strategies if s["_active_from"] is not None and s["_active_from"] <= effective_end]

        for i, strat in enumerate(strategies):
            active_until_candidates = [effective_end]
            if strat.get("valid_until"):
                active_until_candidates.append(pd.to_datetime(strat["valid_until"]))
            if i + 1 < len(strategies):
                active_until_candidates.append(
                    strategies[i + 1]["_active_from"] - pd.Timedelta(days=1)
                )
            strat["_active_until"] = min(active_until_candidates)
        strategies = [s for s in strategies if s["_active_from"] <= s["_active_until"]]

        equity_rows = []
        active_strategy: Optional[dict] = None

        for _, row in prices.iterrows():
            date = row["Date"]
            day_open = float(row["Open"])
            day_high = float(row["High"])
            day_low = float(row["Low"])
            day_close = float(row["Close"])

            # 1) Activate / rotate strategy if today >= next strategy's as_of_date
            new_active = self._strategy_for_date(strategies, date)
            if new_active is not active_strategy:
                active_strategy = new_active
                if active_strategy is None:
                    expired_orders += len(pending_orders)
                    pending_orders = []
                else:
                    # Handle SELL action immediately on activation if a position exists
                    if active_strategy.get("action") == "SELL":
                        expired_orders += len(pending_orders)
                        pending_orders = []
                    if active_strategy.get("action") == "SELL" and position is not None:
                        cash, trades = self._close_position_market(
                            position,
                            day_open,
                            str(date.date()),
                            cash,
                            trades,
                            executions,
                            signal_date=active_strategy["as_of_date"],
                            reason="market_close",
                            fill_basis="next_open",
                        )
                        position = None
                    # Note: position.stop_loss is intentionally not refreshed
                    # from active_strategy.stop_loss here. The pending order
                    # is the single source of truth for sl — when an
                    # entry/add order fills, its snapshot sl is propagated
                    # to the position. A strategy that wants to change sl
                    # must do so by issuing a new order with that sl.
                    new_orders = self._build_pending_orders(active_strategy, cash, position)
                    expired_count, pending_orders = self._merge_pending_orders(
                        pending_orders,
                        new_orders,
                        position,
                    )
                    expired_orders += expired_count
                    orders_created += len(new_orders)

            # 2) Check stop-loss on the open position FIRST (more conservative).
            # A position opened later in this same bar is not checked again until the next bar.
            if position is not None:
                if position.stop_loss is not None and day_low <= position.stop_loss:
                    fill_price, fill_basis = self._stop_fill_price(day_open, position.stop_loss)
                    cash, trades = self._close_position_limit(
                        position,
                        fill_price,
                        str(date.date()),
                        cash,
                        trades,
                        executions,
                        signal_date=position.stop_loss_as_of,
                        reason="stop_loss",
                        fill_basis=fill_basis,
                    )
                    position = None
                    expired_count, pending_orders = self._prune_pending_orders(
                        pending_orders,
                        position,
                    )
                    expired_orders += expired_count

            # 3a) Check reduce_stop (partial sell-on-drop) before take-profit.
            # Defensive trim runs on the same day_low touch as stop_loss but
            # only sells size_pct%; stop_loss above already handled full exits.
            if position is not None and pending_orders:
                still_pending = []
                for order in pending_orders:
                    fill = self._reduce_stop_fill_price(day_open, day_low, order)
                    if order.order_type == "reduce_stop" and fill is not None:
                        fill_price, fill_basis = fill
                        cash, trades, position = self._reduce_position_limit(
                            position,
                            fill_price,
                            order.size_pct,
                            str(date.date()),
                            cash,
                            trades,
                            executions,
                            signal_date=order.strategy_as_of,
                            fill_basis=fill_basis,
                            order_type="reduce_stop",
                            reason="reduce_stop",
                        )
                    else:
                        still_pending.append(order)
                pending_orders = still_pending
                if position is None:
                    expired_count, pending_orders = self._prune_pending_orders(
                        pending_orders,
                        position,
                    )
                    expired_orders += expired_count

            # 3b) Check take_profit (sell-on-rise) after defensive trims.
            if position is not None and pending_orders:
                still_pending = []
                for order in pending_orders:
                    fill = self._sell_order_fill_price(day_open, day_high, order)
                    if order.order_type == "take_profit" and fill is not None:
                        fill_price, fill_basis = fill
                        cash, trades, position = self._reduce_position_limit(
                            position,
                            fill_price,
                            order.size_pct,
                            str(date.date()),
                            cash,
                            trades,
                            executions,
                            signal_date=order.strategy_as_of,
                            fill_basis=fill_basis,
                            order_type="take_profit",
                            reason="take_profit",
                        )
                    else:
                        still_pending.append(order)
                pending_orders = still_pending
                if position is None:
                    expired_count, pending_orders = self._prune_pending_orders(
                        pending_orders,
                        position,
                    )
                    expired_orders += expired_count

            # 4) Check entry/add limit-buys after existing-position exits.
            if pending_orders:
                still_pending = []
                for order in pending_orders:
                    fill = self._buy_order_fill_price(day_open, day_low, order)
                    if order.order_type in {"entry", "add"} and fill is not None:
                        fill_price, fill_basis = fill
                        cash, position = self._execute_buy_order(
                            order,
                            fill_price,
                            str(date.date()),
                            cash,
                            position,
                            executions,
                            fill_basis=fill_basis,
                        )
                    else:
                        still_pending.append(order)
                pending_orders = still_pending
                expired_count, pending_orders = self._prune_pending_orders(
                    pending_orders,
                    position,
                )
                expired_orders += expired_count

            # 5) Mark-to-market
            mark_price = day_close
            position_value = position.shares * mark_price if position else 0.0
            equity = cash + position_value
            equity_rows.append({
                "Date": date,
                "Equity": equity,
                "Cash": cash,
                "Position": position.shares if position else 0,
                "MarkPrice": mark_price,
            })

        final_cash = cash
        final_position = None
        if position is not None:
            final_position = {
                "entry_date": position.entry_date,
                "entry_price": position.entry_price,
                "shares": position.shares,
                "stop_loss": position.stop_loss,
                "stop_loss_as_of": position.stop_loss_as_of,
            }

        final_pending_orders = [
            {
                "order_type": o.order_type,
                "strategy_as_of": o.strategy_as_of,
                "limit_price": o.limit_price,
                "size_pct": o.size_pct,
                "stop_loss": o.stop_loss,
            }
            for o in pending_orders
        ]

        # Close any leftover open position at final close (mark-to-market exit, not a real fill).
        if position is not None and equity_rows:
            final_price = equity_rows[-1]["MarkPrice"]
            cash, trades = self._close_position_market(
                position, final_price, str(prices.iloc[-1]["Date"].date()),
                cash, trades, executions, reason="end_of_backtest", fill_basis="final_close_mark"
            )
        expired_orders += len(pending_orders)

        equity_df = pd.DataFrame(equity_rows)
        index_prices = self.load_index_context_prices(effective_start_date, effective_end_date)
        self._attach_trade_route_price_context(trades, executions, prices, index_prices)
        audit = self._audit_bias(strategies, executions, prices, equity_df)
        report = {
            "extraction_failures": self.extraction_failures,
            "empty_strategies": sum(1 for s in strategies if self._is_empty_strategy(s)),
            "orders_created": orders_created,
            "expired_orders": expired_orders,
            "expired_order_rate": (expired_orders / orders_created) if orders_created else 0.0,
            "schema_migrations": self.schema_migrations,
            "schema_rejections": self.schema_rejections,
            "invalid_sell_orders": self.invalid_sell_orders,
            "reduce_stop_capped": self.reduce_stop_capped,
            "entry_promoted_to_add": self.entry_promoted_to_add,
            "tp_below_cost_blocked": self.tp_below_cost_blocked,
            "tp_downgrades_blocked": self.tp_downgrades_blocked,
            "tp_upgrades_applied": self.tp_upgrades_applied,
            "stop_widened": self.stop_widened,
            "stop_downgrades_blocked": self.stop_downgrades_blocked,
            "stop_upgrades_applied": self.stop_upgrades_applied,
            "commission": self.commission,
            "slippage_bps": self.slippage_bps,
            "min_stop_distance_pct": self.min_stop_distance_pct,
            "bias_audit": audit,
        }
        return BacktestResult(
            equity_curve=equity_df,
            trades=trades,
            executions=executions,
            strategies_loaded=len(strategies),
            effective_start_date=effective_start_date,
            effective_end_date=effective_end_date,
            report=report,
            final_cash=final_cash,
            final_position=final_position,
            final_pending_orders=final_pending_orders,
        )

    # ----------------------------------------------------------- helpers
    @staticmethod
    def _next_trading_day(trading_days: pd.Series, date: str) -> Optional[pd.Timestamp]:
        target = pd.to_datetime(date).normalize()
        matches = trading_days[trading_days > target]
        if matches.empty:
            return None
        return matches.iloc[0]

    def _normalize_strategy_schema(self, strategy: dict) -> Optional[dict]:
        version = strategy.get("schema_version")
        if version not in (None, "v2", SCHEMA_VERSION):
            return None

        if version != SCHEMA_VERSION:
            migrated_from = version or "legacy"
            # v2 used `reduce_position` for sell-on-rise; v1 used `take_profit`.
            # Both map onto v3 `take_profit` (same fill semantics).
            if not strategy.get("take_profit"):
                source = strategy.pop("reduce_position", None)
                if not source or source.get("price") is None:
                    legacy_tp = strategy.get("take_profit")
                    source = legacy_tp or source or {"price": None, "size_pct": 0}
                strategy["take_profit"] = source
            else:
                strategy.pop("reduce_position", None)
            strategy.setdefault("reduce_stop", {"price": None, "size_pct": 0})
            strategy["schema_version"] = SCHEMA_VERSION
            strategy["_migrated_from_schema"] = migrated_from
            self.schema_migrations += 1
        else:
            strategy.setdefault("take_profit", {"price": None, "size_pct": 0})
            strategy.setdefault("reduce_stop", {"price": None, "size_pct": 0})

        if strategy.get("action") == "SELL":
            changed = False
            for key in ("entry", "add_position", "take_profit", "reduce_stop"):
                block = strategy.get(key) or {}
                try:
                    size_pct = float(block.get("size_pct") or 0)
                except (TypeError, ValueError):
                    size_pct = 0.0
                if block.get("price") is not None or size_pct != 0:
                    changed = True
                strategy[key] = {"price": None, "size_pct": 0}
            if changed:
                self.invalid_sell_orders += 1

        return strategy

    @staticmethod
    def _strategy_for_date(strategies: List[dict], date: pd.Timestamp) -> Optional[dict]:
        active = None
        for s in strategies:
            if s["_active_from"] <= date <= s["_active_until"]:
                active = s
        return active

    def _build_pending_orders(
        self,
        strategy: dict,
        cash: float,
        existing_position: Optional[Position],
    ) -> List[PendingOrder]:
        action = strategy.get("action")
        if action == "SELL":
            return []

        orders = []
        sl = strategy.get("stop_loss") or {}
        stop_loss = float(sl["price"]) if sl.get("price") is not None else None

        if existing_position is None:
            entry = strategy.get("entry") or {}
            entry_order = self._build_order("entry", strategy, entry, stop_loss)
            if entry_order is not None:
                orders.append(entry_order)
        else:
            add = strategy.get("add_position") or {}
            add_size = float(add.get("size_pct") or 0)
            if add_size <= 0:
                # LLMs sometimes write a fresh "entry" while a position exists.
                # Map it onto add_position rather than silently dropping it.
                entry = strategy.get("entry") or {}
                if float(entry.get("size_pct") or 0) > 0:
                    add = entry
                    self.entry_promoted_to_add += 1

            take_profit = strategy.get("take_profit") or {}
            tp_price = take_profit.get("price")
            if tp_price is not None:
                if float(tp_price) < existing_position.entry_price:
                    self.tp_below_cost_blocked += 1
                    take_profit = {"price": None, "size_pct": 0}
                elif add.get("price") is not None and float(tp_price) < float(add["price"]):
                    self.tp_below_cost_blocked += 1
                    take_profit = {"price": None, "size_pct": 0}

            reduce_stop = strategy.get("reduce_stop") or {}
            add_order = self._build_order("add", strategy, add, stop_loss)
            tp_order = self._build_order("take_profit", strategy, take_profit, stop_loss)
            rs_order = self._build_order("reduce_stop", strategy, reduce_stop, stop_loss)
            if add_order is not None:
                orders.append(add_order)
            if tp_order is not None:
                orders.append(tp_order)
            if rs_order is not None:
                orders.append(rs_order)

        return orders

    def _build_order(
        self,
        order_type: str,
        strategy: dict,
        block: dict,
        stop_loss: Optional[float],
    ) -> Optional[PendingOrder]:
        price = block.get("price")
        size_pct = float(block.get("size_pct") or 0.0)
        if size_pct <= 0:
            return None
        if order_type == "reduce_stop" and size_pct > self.REDUCE_STOP_MAX_SIZE_PCT:
            size_pct = self.REDUCE_STOP_MAX_SIZE_PCT
            self.reduce_stop_capped += 1
        return PendingOrder(
            order_type=order_type,
            strategy_as_of=strategy["as_of_date"],
            limit_price=float(price) if price is not None else None,
            size_pct=float(size_pct),
            stop_loss=stop_loss,
        )

    def _merge_pending_orders(
        self,
        pending_orders: List[PendingOrder],
        new_orders: List[PendingOrder],
        existing_position: Optional[Position],
    ) -> tuple[int, List[PendingOrder]]:
        """Replace only pending orders that a new strategy explicitly updates."""
        if not new_orders:
            return BacktestEngine._prune_pending_orders(pending_orders, existing_position)

        self._preserve_non_decreasing_pending_stops(pending_orders, new_orders)
        new_orders = self._preserve_non_decreasing_take_profits(
            pending_orders,
            new_orders,
        )

        replacement_types = {order.order_type for order in new_orders}
        kept = [
            order for order in pending_orders
            if order.order_type not in replacement_types
        ]
        expired = len(pending_orders) - len(kept)
        kept.extend(new_orders)
        prune_expired, pruned = BacktestEngine._prune_pending_orders(kept, existing_position)
        return expired + prune_expired, pruned

    def _preserve_non_decreasing_take_profits(
        self,
        pending_orders: List[PendingOrder],
        new_orders: List[PendingOrder],
    ) -> List[PendingOrder]:
        """Keep pending take-profit targets unless the new strategy raises them."""
        existing_tp = next(
            (
                order
                for order in pending_orders
                if order.order_type == "take_profit" and order.limit_price is not None
            ),
            None,
        )
        if existing_tp is None:
            return new_orders

        filtered_new: List[PendingOrder] = []
        for order in new_orders:
            if order.order_type != "take_profit" or order.limit_price is None:
                filtered_new.append(order)
                continue
            if order.limit_price < existing_tp.limit_price:
                self.tp_downgrades_blocked += 1
                continue
            if order.limit_price > existing_tp.limit_price:
                self.tp_upgrades_applied += 1
            filtered_new.append(order)
        return filtered_new

    def _preserve_non_decreasing_pending_stops(
        self,
        pending_orders: List[PendingOrder],
        new_orders: List[PendingOrder],
    ) -> None:
        """Carry forward pending buy-order stops unless the new strategy raises them."""
        existing_stops = {
            order.order_type: order.stop_loss
            for order in pending_orders
            if order.order_type in {"entry", "add"} and order.stop_loss is not None
        }
        if not existing_stops:
            return

        for order in new_orders:
            if order.order_type not in {"entry", "add"}:
                continue
            previous_stop = existing_stops.get(order.order_type)
            if previous_stop is None:
                continue
            if order.stop_loss is None:
                order.stop_loss = previous_stop
                self.stop_downgrades_blocked += 1
            elif order.stop_loss < previous_stop:
                order.stop_loss = previous_stop
                self.stop_downgrades_blocked += 1
            elif order.stop_loss > previous_stop:
                self.stop_upgrades_applied += 1

    @staticmethod
    def _prune_pending_orders(
        pending_orders: List[PendingOrder],
        existing_position: Optional[Position],
    ) -> tuple[int, List[PendingOrder]]:
        """Drop order types that no longer match the current position state."""
        if existing_position is None:
            valid_types = {"entry"}
        else:
            valid_types = {"add", "take_profit", "reduce_stop"}
        kept = [
            order for order in pending_orders
            if order.order_type in valid_types
        ]
        return len(pending_orders) - len(kept), kept

    def _widen_stop(
        self,
        stop_loss: Optional[float],
        reference_price: float,
    ) -> Optional[float]:
        """Floor a stop-loss to be at least min_stop_distance_pct below reference."""
        if stop_loss is None or self.min_stop_distance_pct <= 0 or reference_price <= 0:
            return stop_loss
        min_stop = reference_price * (1.0 - self.min_stop_distance_pct)
        if stop_loss > min_stop:
            self.stop_widened += 1
            return min_stop
        return stop_loss

    @staticmethod
    def _is_empty_strategy(strategy: dict) -> bool:
        if strategy.get("action") == "SELL":
            return False
        for key in ("entry", "add_position", "take_profit", "reduce_stop"):
            block = strategy.get(key) or {}
            try:
                size_pct = float(block.get("size_pct") or 0)
            except (TypeError, ValueError):
                size_pct = 0.0
            if block.get("price") is not None and size_pct > 0:
                return False
        sl = strategy.get("stop_loss") or {}
        return sl.get("price") is None

    @staticmethod
    def _buy_order_fill_price(day_open: float, day_low: float, order: PendingOrder) -> Optional[tuple[float, str]]:
        if order.order_type not in {"entry", "add"}:
            return None
        if order.limit_price is None:
            return day_open, "next_open"
        if day_open <= order.limit_price:
            return day_open, "open_gap"
        if day_low <= order.limit_price:
            return order.limit_price, "limit_touch"
        return None

    @staticmethod
    def _sell_order_fill_price(day_open: float, day_high: float, order: PendingOrder) -> Optional[tuple[float, str]]:
        if order.order_type != "take_profit":
            return None
        if order.limit_price is None:
            return day_open, "next_open"
        if day_open >= order.limit_price:
            return day_open, "open_gap"
        if day_high >= order.limit_price:
            return order.limit_price, "limit_touch"
        return None

    @staticmethod
    def _reduce_stop_fill_price(day_open: float, day_low: float, order: PendingOrder) -> Optional[tuple[float, str]]:
        if order.order_type != "reduce_stop":
            return None
        if order.limit_price is None:
            return None
        if day_open <= order.limit_price:
            return day_open, "reduce_stop_gap"
        if day_low <= order.limit_price:
            return order.limit_price, "reduce_stop_touch"
        return None

    @staticmethod
    def _stop_fill_price(day_open: float, stop_price: float) -> tuple[float, str]:
        return (day_open, "stop_gap") if day_open <= stop_price else (stop_price, "stop_touch")

    def _buy_execution_price(self, fill_price: float) -> float:
        return fill_price * (1.0 + self.slippage_bps / 10_000.0)

    def _sell_execution_price(self, fill_price: float) -> float:
        return max(0.0, fill_price * (1.0 - self.slippage_bps / 10_000.0))

    def _execute_buy_order(
        self,
        order: PendingOrder,
        fill_price: float,
        entry_date: str,
        cash: float,
        position: Optional[Position],
        executions: List[dict],
        fill_basis: str,
    ) -> tuple[float, Optional[Position]]:
        execution_price = self._buy_execution_price(fill_price)
        position_value = position.shares * fill_price if position else 0.0
        equity = cash + position_value
        target_spend = equity * (order.size_pct / 100.0)
        spend = min(cash, target_spend)
        notional = max(0.0, spend - self.commission)
        if notional <= 0 or execution_price <= 0:
            return cash, position
        shares = notional / execution_price
        if shares <= 0:
            return cash, position
        cash -= shares * execution_price + self.commission
        effective_stop = self._widen_stop(order.stop_loss, execution_price)
        if position is None:
            position = Position(
                entry_date=entry_date,
                entry_price=execution_price,
                shares=shares,
                stop_loss=effective_stop,
                stop_loss_as_of=order.strategy_as_of if effective_stop is not None else None,
                entry_commission=self.commission,
            )
            self._record_execution(
                executions, "BUY", order.order_type, order.strategy_as_of, entry_date,
                fill_price, execution_price, shares, self.commission, fill_basis
            )
            return cash, position

        total_cost = position.entry_price * position.shares + execution_price * shares
        position.shares = position.shares + shares
        position.entry_price = total_cost / position.shares
        position.entry_commission += self.commission
        if effective_stop is not None:
            position.stop_loss = effective_stop
            position.stop_loss_as_of = order.strategy_as_of
        self._record_execution(
            executions, "BUY", order.order_type, order.strategy_as_of, entry_date,
            fill_price, execution_price, shares, self.commission, fill_basis
        )
        return cash, position

    def _reduce_position_limit(
        self, position, fill_price, size_pct, exit_date, cash, trades, executions,
        signal_date=None, fill_basis="limit_touch",
        order_type="take_profit", reason="take_profit",
    ):
        shares_to_sell = max(0.0, min(position.shares, position.shares * (size_pct / 100.0)))
        if shares_to_sell <= 0:
            return cash, trades, position
        execution_price = self._sell_execution_price(fill_price)
        entry_commission = position.entry_commission * (shares_to_sell / position.shares)
        proceeds = max(0.0, shares_to_sell * execution_price - self.commission)
        pnl = (execution_price - position.entry_price) * shares_to_sell - self.commission - entry_commission
        cash += proceeds
        position.shares = position.shares - shares_to_sell
        position.entry_commission -= entry_commission
        trades.append({
            "entry_date": position.entry_date,
            "entry_price": position.entry_price,
            "shares": shares_to_sell,
            "exit_date": exit_date,
            "exit_price": execution_price,
            "raw_exit_price": fill_price,
            "pnl": pnl,
            "commission": self.commission + entry_commission,
            "slippage_bps": self.slippage_bps,
            "reason": reason,
        })
        self._record_execution(
            executions, "SELL", order_type, signal_date, exit_date, fill_price,
            execution_price, shares_to_sell, self.commission + entry_commission, fill_basis
        )
        if position.shares <= 0:
            position.exit_date = exit_date
            position.exit_price = fill_price
            position.pnl = pnl
            return cash, trades, None
        return cash, trades, position

    def _close_position_limit(
        self, position, fill_price, exit_date, cash, trades, executions,
        signal_date=None, reason="exit", fill_basis="limit_touch"
    ):
        execution_price = self._sell_execution_price(fill_price)
        proceeds = max(0.0, position.shares * execution_price - self.commission)
        entry_commission = position.entry_commission
        pnl = (execution_price - position.entry_price) * position.shares - self.commission - entry_commission
        position.exit_date = exit_date
        position.exit_price = execution_price
        position.pnl = pnl
        trades.append({
            "entry_date": position.entry_date,
            "entry_price": position.entry_price,
            "shares": position.shares,
            "exit_date": exit_date,
            "exit_price": execution_price,
            "raw_exit_price": fill_price,
            "pnl": pnl,
            "commission": self.commission + entry_commission,
            "slippage_bps": self.slippage_bps,
            "reason": reason,
        })
        self._record_execution(
            executions, "SELL", reason, signal_date, exit_date, fill_price,
            execution_price, position.shares, self.commission + entry_commission, fill_basis
        )
        return cash + proceeds, trades

    def _close_position_market(
        self, position, market_price, exit_date, cash, trades, executions,
        signal_date=None, reason="market_close", fill_basis="next_open"
    ):
        return self._close_position_limit(
            position, market_price, exit_date, cash, trades, executions,
            signal_date=signal_date, reason=reason, fill_basis=fill_basis
        )

    @staticmethod
    def _record_execution(
        executions: List[dict],
        side: str,
        order_type: str,
        signal_date: Optional[str],
        fill_date: str,
        raw_fill_price: float,
        execution_price: float,
        shares: float,
        commission: float,
        fill_basis: str,
    ) -> None:
        executions.append({
            "side": side,
            "order_type": order_type,
            "signal_date": signal_date,
            "fill_date": fill_date,
            "raw_fill_price": raw_fill_price,
            "execution_price": execution_price,
            "shares": shares,
            "commission": commission,
            "fill_basis": fill_basis,
        })

    @staticmethod
    def _price_context_lookup(prices: pd.DataFrame) -> dict[str, dict]:
        lookup: dict[str, dict] = {}
        if prices.empty:
            return lookup
        for row in prices.itertuples(index=False):
            date = row.Date.strftime("%Y-%m-%d")
            lookup[date] = {
                "date": date,
                "open": float(row.Open),
                "high": float(row.High),
                "low": float(row.Low),
                "close": float(row.Close),
                "volume": float(row.Volume) if hasattr(row, "Volume") else None,
            }
        return lookup

    @classmethod
    def _context_for_date(
        cls,
        date: Optional[str],
        stock_lookup: dict[str, dict],
        index_lookups: dict[str, dict[str, dict]],
    ) -> dict:
        if not date:
            return {"stock": None, "indices": {}}
        return {
            "stock": stock_lookup.get(date),
            "indices": {
                ticker: lookup.get(date)
                for ticker, lookup in index_lookups.items()
            },
        }

    @classmethod
    def _attach_trade_route_price_context(
        cls,
        trades: List[dict],
        executions: List[dict],
        prices: pd.DataFrame,
        index_prices: dict[str, pd.DataFrame],
    ) -> None:
        stock_lookup = cls._price_context_lookup(prices)
        index_lookups = {
            ticker: cls._price_context_lookup(df)
            for ticker, df in index_prices.items()
        }
        for execution in executions:
            execution["fill_price_context"] = cls._context_for_date(
                execution.get("fill_date"),
                stock_lookup,
                index_lookups,
            )
        for trade in trades:
            trade["entry_price_context"] = cls._context_for_date(
                trade.get("entry_date"),
                stock_lookup,
                index_lookups,
            )
            trade["exit_price_context"] = cls._context_for_date(
                trade.get("exit_date"),
                stock_lookup,
                index_lookups,
            )

    def _audit_bias(
        self,
        strategies: List[dict],
        executions: List[dict],
        prices: pd.DataFrame,
        equity_df: pd.DataFrame,
    ) -> dict:
        same_bar = []
        future_signal = []
        missing_signal = []
        current_close_fills = []
        for exe in executions:
            reason = exe.get("order_type")
            if reason == "end_of_backtest":
                continue
            signal_date = exe.get("signal_date")
            fill_date = exe.get("fill_date")
            if not signal_date:
                missing_signal.append(exe)
                continue
            signal_ts = pd.to_datetime(signal_date).normalize()
            fill_ts = pd.to_datetime(fill_date).normalize()
            if signal_ts == fill_ts:
                same_bar.append(exe)
            if signal_ts > fill_ts:
                future_signal.append(exe)
            if exe.get("fill_basis") in {"current_close", "same_bar_close"}:
                current_close_fills.append(exe)

        same_bar_profit = [
            exe for exe in executions
            if exe.get("side") == "BUY"
            and exe.get("signal_date")
            and pd.to_datetime(exe["signal_date"]).normalize() == pd.to_datetime(exe["fill_date"]).normalize()
        ]
        valid_fills = self._audit_fill_prices(executions, prices)

        return {
            "event_timing": {
                "signal_generated_after_close": True,
                "orders_execute_next_trading_day_or_later": len(same_bar) == 0 and len(future_signal) == 0,
                "same_bar_signal_fills": len(same_bar),
                "future_signal_fills": len(future_signal),
                "missing_signal_dates": len(missing_signal),
                "same_bar_profit_flags": len(same_bar_profit),
            },
            "execution_quality": {
                "uses_current_close_for_entry": False,
                "current_close_fills": len(current_close_fills),
                "fill_prices_inside_bar_before_slippage": valid_fills["inside_bar"],
                "raw_fill_outside_bar": valid_fills["outside_bar"],
                "market_entries_use_next_open": True,
                "slippage_bps": self.slippage_bps,
                "commission": self.commission,
            },
            "data_leakage": {
                "engine_uses_future_returns": False,
                "engine_uses_rolling_features": False,
                "benchmark_alignment": "inner_join_only",
                "price_data_sorted_unique": bool(prices["Date"].is_monotonic_increasing and not prices["Date"].duplicated().any()),
                "equity_marked_after_execution_at_close": True,
            },
            "survivorship_bias": {
                "single_ticker_backtest": True,
                "warning": "Universe membership is supplied by the user; delisted symbols and historical index membership are not modeled.",
            },
        }

    @staticmethod
    def _audit_fill_prices(executions: List[dict], prices: pd.DataFrame) -> dict:
        by_date = {
            row.Date.strftime("%Y-%m-%d"): (float(row.Low), float(row.High))
            for row in prices.itertuples(index=False)
        }
        inside = 0
        outside = 0
        for exe in executions:
            if exe.get("order_type") == "end_of_backtest":
                continue
            bounds = by_date.get(exe.get("fill_date"))
            if bounds is None:
                continue
            low, high = bounds
            raw = float(exe["raw_fill_price"])
            if low <= raw <= high:
                inside += 1
            else:
                outside += 1
        return {"inside_bar": outside == 0, "outside_bar": outside, "inside_count": inside}
