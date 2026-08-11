from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from cli.utils import detect_asset_type
from tradingagents.allocation import OrderIntent, conviction_targets, reconcile_targets
from tradingagents.automation_state import AutomationState
from tradingagents.execution import Broker, validate_execution_mode


@dataclass(frozen=True)
class AutomationSettings:
    watchlist: tuple[str, ...]
    batch_size: int
    analysis_interval_minutes: int
    position_interval_minutes: int
    max_cash_allocation: float
    decision_max_age_minutes: int
    rebalance_threshold_usd: float
    state_path: Path
    auto_execute: bool
    alpaca_mode: str
    live_trading_ack: str

    @classmethod
    def from_config(cls, config: Mapping[str, object]) -> "AutomationSettings":
        symbols = tuple(symbol.strip().upper() for symbol in str(config["watchlist"]).split(","))
        if not all(symbols) or len(symbols) != 7 or len(set(symbols)) != 7:
            raise ValueError("watchlist must contain exactly 7 unique symbols")

        batch_size = config["batch_size"]
        if batch_size not in (2, 3):
            raise ValueError("batch_size must be 2 or 3")

        alpaca_mode = config["alpaca_mode"]
        if alpaca_mode not in ("paper", "live"):
            raise ValueError("alpaca_mode must be paper or live")

        analysis_interval_minutes = config["analysis_interval_minutes"]
        position_interval_minutes = config["position_interval_minutes"]
        decision_max_age_minutes = config["decision_max_age_minutes"]
        if any(
            value <= 0
            for value in (
                analysis_interval_minutes,
                position_interval_minutes,
                decision_max_age_minutes,
            )
        ):
            raise ValueError("intervals and decision age must be positive")

        max_cash_allocation = config["max_cash_allocation"]
        if not 0 < max_cash_allocation <= 0.30:
            raise ValueError("max_cash_allocation must be greater than 0 and no greater than 0.30")

        rebalance_threshold_usd = config["rebalance_threshold_usd"]
        if rebalance_threshold_usd < 0:
            raise ValueError("rebalance_threshold_usd must be non-negative")

        return cls(
            watchlist=symbols,
            batch_size=batch_size,
            analysis_interval_minutes=analysis_interval_minutes,
            position_interval_minutes=position_interval_minutes,
            max_cash_allocation=max_cash_allocation,
            decision_max_age_minutes=decision_max_age_minutes,
            rebalance_threshold_usd=rebalance_threshold_usd,
            state_path=Path(config["automation_state_path"]),
            auto_execute=config["auto_execute"],
            alpaca_mode=alpaca_mode,
            live_trading_ack=config["live_trading_ack"],
        )


def partition_watchlist(
    symbols: tuple[str, ...], preferred_size: int
) -> tuple[tuple[str, ...], ...]:
    if len(symbols) != 7 or preferred_size not in (2, 3):
        raise ValueError("seven symbols and a preferred batch size of 2 or 3 are required")
    cut_points = (2, 4) if preferred_size == 2 else (3, 5)
    first, second = cut_points
    return (symbols[:first], symbols[first:second], symbols[second:])


@dataclass(frozen=True)
class CycleResult:
    cycle_id: str
    analyzed_symbols: tuple[str, ...]
    failed_symbols: tuple[str, ...]
    order_intents: tuple[OrderIntent, ...]
    submitted_order_ids: tuple[str, ...]
    trade_suppressed_reason: str | None


class AutomationCycleService:
    def __init__(
        self,
        settings: AutomationSettings,
        state: AutomationState,
        broker: Broker,
        graph_factory: Callable[[tuple[str, ...]], object],
    ) -> None:
        self.settings = settings
        self.state = state
        self.broker = broker
        self.graph_factory = graph_factory

    def run_analysis_cycle(self, due_time: datetime) -> CycleResult:
        _require_aware(due_time)
        broker_time = self.broker.broker_time()
        _require_aware(broker_time)
        batch_index = self.state.get_batch_index()
        cycle_id = f"{broker_time.isoformat()}-{batch_index}"
        partition = partition_watchlist(self.settings.watchlist, self.settings.batch_size)[
            batch_index
        ]
        eligible = self._eligible_symbols(partition)
        if len(eligible) < 2:
            return CycleResult(
                cycle_id,
                (),
                (),
                (),
                (),
                "fewer than 2 eligible symbols in current partition",
            )

        broker_date = broker_time.date().isoformat()
        graphs: dict[tuple[str, ...], object] = {}
        analyzed = []
        failed = []
        for symbol in eligible:
            asset_type = detect_asset_type(symbol).value
            analysts = ("market", "social", "news")
            if asset_type == "stock":
                analysts += ("fundamentals",)
            if analysts not in graphs:
                graphs[analysts] = self.graph_factory(analysts)
            graph = graphs[analysts]
            try:
                final_state, rating = graph.propagate(symbol, broker_date, asset_type)
                report_path = graph.save_reports(final_state, symbol)
                self.state.save_decision(
                    symbol,
                    rating,
                    broker_time,
                    broker_date,
                    str(report_path),
                )
            except Exception:
                failed.append(symbol)
            else:
                analyzed.append(symbol)

        self.state.advance_batch_index((batch_index + 1) % 3)
        decisions = self.state.fresh_decisions(
            self.settings.watchlist,
            broker_time,
            self.settings.decision_max_age_minutes,
        )
        if failed:
            return CycleResult(
                cycle_id,
                tuple(analyzed),
                tuple(failed),
                (),
                (),
                f"analysis failed for: {', '.join(failed)}",
            )
        missing = tuple(symbol for symbol in self.settings.watchlist if symbol not in decisions)
        if missing:
            reason = "waiting for fresh decisions for all 7 symbols"
            if len(missing) == 1:
                reason = f"waiting for fresh decision: {missing[0]}"
            return CycleResult(
                cycle_id,
                tuple(analyzed),
                tuple(failed),
                (),
                (),
                reason,
            )

        try:
            account = self.broker.account()
            account_error = _account_error(account)
            if account_error is not None:
                return CycleResult(
                    cycle_id,
                    tuple(analyzed),
                    tuple(failed),
                    (),
                    (),
                    account_error,
                )
            positions = self.broker.positions()
            self.state.record_position_snapshot(broker_time, account.cash, positions)
            targets = conviction_targets(
                {symbol: decisions[symbol].rating for symbol in self.settings.watchlist},
                account.cash,
                self.settings.max_cash_allocation,
            )
            prices = {
                symbol: self.broker.latest_price(symbol) for symbol in self.settings.watchlist
            }
            open_orders = self.broker.open_order_exposure(prices)
            intents = tuple(
                reconcile_targets(
                    targets,
                    positions,
                    open_orders,
                    self.settings.rebalance_threshold_usd,
                )
            )
        except Exception as error:
            return CycleResult(
                cycle_id,
                tuple(analyzed),
                tuple(failed),
                (),
                (),
                f"broker read failed: {error}",
            )

        self.state.record_order_intents(cycle_id, broker_time, intents)
        if not self.settings.auto_execute:
            for intent in intents:
                self.state.update_order_intent(cycle_id, intent.symbol, "planned")
            return CycleResult(
                cycle_id,
                tuple(analyzed),
                tuple(failed),
                intents,
                (),
                None,
            )

        try:
            validate_execution_mode(
                self.settings.alpaca_mode,
                self.settings.auto_execute,
                self.settings.live_trading_ack,
            )
        except ValueError as error:
            self._mark_all(cycle_id, intents, "error")
            return CycleResult(
                cycle_id,
                tuple(analyzed),
                tuple(failed),
                intents,
                (),
                str(error),
            )

        buy_notional = sum(
            (intent.notional for intent in intents if intent.side == "buy"),
            Decimal("0"),
        )
        if buy_notional > account.buying_power:
            self._mark_all(cycle_id, intents, "error")
            return CycleResult(
                cycle_id,
                tuple(analyzed),
                tuple(failed),
                intents,
                (),
                "insufficient buying power",
            )

        prepared = []
        skipped = []
        try:
            for intent in intents:
                try:
                    asset = self.broker.asset(intent.symbol)
                    spec = self.broker.prepare_order(
                        intent,
                        asset,
                        prices[intent.symbol],
                        cycle_id,
                    )
                except ValueError:
                    skipped.append(intent.symbol)
                    self.state.update_order_intent(cycle_id, intent.symbol, "skipped")
                else:
                    prepared.append((intent, spec))
        except Exception as error:
            for intent in intents:
                if intent.symbol not in skipped:
                    self.state.update_order_intent(cycle_id, intent.symbol, "error")
            return CycleResult(
                cycle_id,
                tuple(analyzed),
                tuple(failed),
                intents,
                (),
                f"broker read failed: {error}",
            )

        submitted_ids = []
        submission_errors = []
        for intent, spec in prepared:
            try:
                order_id = self.broker.submit_idempotent(spec)
            except Exception:
                submission_errors.append(intent.symbol)
                self.state.update_order_intent(cycle_id, intent.symbol, "error")
            else:
                submitted_ids.append(order_id)
                self.state.update_order_intent(
                    cycle_id,
                    intent.symbol,
                    "submitted",
                    spec.client_order_id,
                )

        reasons = []
        if skipped:
            reasons.append(f"skipped unsupported symbols: {', '.join(skipped)}")
        if submission_errors:
            reasons.append(f"submission errors: {', '.join(submission_errors)}")
        return CycleResult(
            cycle_id,
            tuple(analyzed),
            tuple(failed),
            intents,
            tuple(submitted_ids),
            "; ".join(reasons) or None,
        )

    def track_positions(self, due_time: datetime) -> None:
        _require_aware(due_time)
        has_crypto = any(
            detect_asset_type(symbol).value == "crypto" for symbol in self.settings.watchlist
        )
        if not has_crypto and not self.broker.equity_market_is_open():
            return
        broker_time = self.broker.broker_time()
        _require_aware(broker_time)
        account = self.broker.account()
        account_error = _account_error(account)
        if account_error is not None:
            raise RuntimeError(account_error)
        positions = self.broker.positions()
        self.state.record_position_snapshot(broker_time, account.cash, positions)

    def _eligible_symbols(self, partition: tuple[str, ...]) -> tuple[str, ...]:
        has_equity = any(detect_asset_type(symbol).value == "stock" for symbol in partition)
        equity_open = self.broker.equity_market_is_open() if has_equity else False
        return tuple(
            symbol
            for symbol in partition
            if detect_asset_type(symbol).value == "crypto" or equity_open
        )

    def _mark_all(self, cycle_id: str, intents: tuple[OrderIntent, ...], status: str) -> None:
        for intent in intents:
            self.state.update_order_intent(cycle_id, intent.symbol, status)


def _account_error(account) -> str | None:
    if account.trading_blocked:
        return "account is blocked from trading"
    if account.status.upper() != "ACTIVE":
        return "account is not active"
    return None


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
