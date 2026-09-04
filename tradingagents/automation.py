import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from cli.utils import detect_asset_type
from tradingagents.allocation import OrderIntent, conviction_targets, reconcile_targets
from tradingagents.automation_state import AutomationState
from tradingagents.execution import LIVE_OPTIONS_ACKNOWLEDGMENT, Broker, validate_execution_mode
from tradingagents.options import (
    CONTRACT_MULTIPLIER,
    OptionIntent,
    build_reservations,
    option_delta_exposure,
    option_intent_delta_exposure,
    plan_new_entry,
    plan_profit_exit,
)
from tradingagents.risk import scale_equity_targets

NEW_YORK = ZoneInfo("America/New_York")


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
    target_volatility: float = 0.15
    max_volatility: float = 0.20
    max_gross_leverage: float = 2.0
    options_enabled: bool = False
    options_auto_execute: bool = False
    options_max_equity_fraction: float = 0.20
    options_entry_time_et: str = "10:00"
    options_earnings_path: Path = Path("earnings.json")
    live_options_ack: str = ""

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

        target_volatility = config["target_volatility"]
        max_volatility = config["max_volatility"]
        max_gross_leverage = config["max_gross_leverage"]
        if not 0 < target_volatility <= max_volatility <= 0.20:
            raise ValueError(
                "volatility policy must satisfy 0 < target_volatility "
                "<= max_volatility <= 0.20"
            )
        if not 1.0 <= max_gross_leverage <= 2.0:
            raise ValueError("max_gross_leverage must be between 1.0 and 2.0")
        options_max_equity_fraction = config["options_max_equity_fraction"]
        if not 0 < options_max_equity_fraction <= 0.20:
            raise ValueError(
                "options_max_equity_fraction must be greater than 0 and no greater than 0.20"
            )
        options_entry_time_et = str(config["options_entry_time_et"])
        _entry_time(options_entry_time_et)
        options_earnings_path = Path(config["options_earnings_path"])

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
            target_volatility=target_volatility,
            max_volatility=max_volatility,
            max_gross_leverage=max_gross_leverage,
            options_enabled=config["options_enabled"],
            options_auto_execute=config["options_auto_execute"],
            options_max_equity_fraction=options_max_equity_fraction,
            options_entry_time_et=options_entry_time_et,
            options_earnings_path=options_earnings_path,
            live_options_ack=str(config["live_options_ack"]),
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


@dataclass(frozen=True)
class OptionCycleResult:
    cycle_id: str
    intents: tuple[OptionIntent, ...]
    submitted_order_ids: tuple[str, ...]
    suppressed_reason: str | None


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
        self._last_equity_due_time: datetime | None = None
        self._last_equity_order_symbols: frozenset[str] = frozenset()

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

        graphs: dict[tuple[str, ...], object] = {}
        analyzed = []
        failed = []
        for symbol in eligible:
            asset_type = detect_asset_type(symbol).value
            analysts = ("market", "social", "news")
            if asset_type == "stock":
                analysts += ("fundamentals",)
            try:
                graph_time = self.broker.broker_time()
                _require_aware(graph_time)
                broker_date = graph_time.date().isoformat()
                if analysts not in graphs:
                    graphs[analysts] = self.graph_factory(analysts)
                graph = graphs[analysts]
                final_state, rating = graph.propagate(symbol, broker_date, asset_type)
                report_path = graph.save_reports(final_state, symbol)
                decision_time = self.broker.broker_time()
                _require_aware(decision_time)
                self.state.save_decision(
                    symbol,
                    rating,
                    decision_time,
                    broker_date,
                    str(report_path),
                )
            except Exception:
                failed.append(symbol)
            else:
                analyzed.append(symbol)

        self.state.advance_batch_index((batch_index + 1) % 3)
        try:
            freshness_time = self.broker.broker_time()
            _require_aware(freshness_time)
            decisions = self.state.fresh_decisions(
                self.settings.watchlist,
                freshness_time,
                self.settings.decision_max_age_minutes,
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
            snapshot_time = self.broker.broker_time()
            _require_aware(snapshot_time)
            self.state.record_position_snapshot(snapshot_time, account.cash, positions)
            executable = self._market_eligible_symbols(self.settings.watchlist)
            prices = {symbol: self.broker.latest_price(symbol) for symbol in executable}
            allocation_cash = account.cash
            minimum_positions = None
            fixed_option_exposure = {}
            if self.settings.options_enabled:
                equities, option_positions, option_orders = (
                    self.broker.wheel_positions_and_orders()
                )
                reservations = build_reservations(equities, option_positions, option_orders)
                allocation_cash = max(
                    account.cash - sum(reservations.put_collateral.values(), Decimal("0")),
                    Decimal("0"),
                )
                minimum_positions = {
                    symbol: shares * prices[symbol]
                    for symbol, shares in reservations.covered_shares.items()
                    if symbol in prices
                }
                fixed_option_exposure = option_delta_exposure(option_positions, prices)
            all_targets = conviction_targets(
                {symbol: decisions[symbol].rating for symbol in self.settings.watchlist},
                allocation_cash,
                self.settings.max_cash_allocation,
            )
            targets = {symbol: all_targets[symbol] for symbol in executable}
            if self.settings.options_enabled:
                targets = scale_equity_targets(
                    targets,
                    fixed_option_exposure,
                    account.equity,
                    self.broker.daily_closes(self.settings.watchlist),
                    self.settings.target_volatility,
                    self.settings.max_volatility,
                    self.settings.max_gross_leverage,
                ).targets
            open_orders = self.broker.open_order_exposure(prices)
            intents = tuple(
                reconcile_targets(
                    targets,
                    positions,
                    open_orders,
                    self.settings.rebalance_threshold_usd,
                    minimum_positions=minimum_positions,
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

        try:
            intent_time = self.broker.broker_time()
            _require_aware(intent_time)
        except Exception as error:
            return CycleResult(
                cycle_id,
                tuple(analyzed),
                tuple(failed),
                (),
                (),
                f"broker read failed: {error}",
            )
        self.state.record_order_intents(cycle_id, intent_time, intents)
        self._last_equity_due_time = due_time
        self._last_equity_order_symbols = frozenset(intent.symbol for intent in intents)
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
                    unresolved_id = self.state.unresolved_client_order_id(intent)
                    if unresolved_id is not None:
                        spec = replace(spec, client_order_id=unresolved_id)
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
            self.state.update_order_intent(
                cycle_id,
                intent.symbol,
                "pending",
                spec.client_order_id,
            )
            try:
                order_id = self.broker.submit_idempotent(spec)
            except Exception:
                submission_errors.append(intent.symbol)
                self.state.update_order_intent(
                    cycle_id,
                    intent.symbol,
                    "error",
                    spec.client_order_id,
                )
            else:
                submitted_ids.append(order_id)
                self.state.mark_order_intent_submitted(
                    cycle_id,
                    intent.symbol,
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

    def manage_options(self, due_time: datetime) -> OptionCycleResult:
        _require_aware(due_time)
        cycle_id = f"options-{due_time.isoformat()}"
        if not self.settings.options_enabled:
            return OptionCycleResult(cycle_id, (), (), "options disabled")
        if not self.broker.equity_market_is_open():
            return OptionCycleResult(cycle_id, (), (), "equity market is closed")

        try:
            now = self.broker.broker_time()
            _require_aware(now)
            cycle_id = f"options-{now.isoformat()}"
            account = self.broker.account()
            account_error = _account_error(account)
            if account_error is not None:
                return OptionCycleResult(cycle_id, (), (), account_error)
            if account.equity <= 0 or account.options_buying_power < 0:
                raise ValueError("invalid account equity or options buying power")
            equities, option_positions, option_orders = self.broker.wheel_positions_and_orders()
            prices = {
                symbol: self.broker.latest_price(symbol)
                for symbol in self.settings.watchlist
            }
            decisions = self.state.fresh_decisions(
                self.settings.watchlist,
                now,
                self.settings.decision_max_age_minutes,
            )
            equity_open_orders = self.broker.open_order_exposure(prices)
            close_history = self.broker.daily_closes(self.settings.watchlist)
            earnings = _read_earnings_cache(
                self.settings.options_earnings_path,
                self.settings.watchlist,
                now,
            )
            reservations = build_reservations(equities, option_positions, option_orders)
            existing_put_collateral = sum(
                reservations.put_collateral.values(), Decimal("0")
            )
            if (
                existing_put_collateral > account.cash
                or existing_put_collateral > account.options_buying_power
            ):
                raise ValueError("short-put collateral exceeds available funds")
            contracts = self._option_contract_snapshot(now, decisions, option_positions)
            fixed_exposure = option_delta_exposure(option_positions, prices)
        except Exception as error:
            return OptionCycleResult(cycle_id, (), (), f"option read failed: {error}")

        try:
            settling = self._observe_wheel_phases(
                now, equities, option_positions, option_orders
            )
        except Exception as error:
            return OptionCycleResult(cycle_id, (), (), f"option state failed: {error}")

        cancellation_failed = False
        if self.settings.options_auto_execute:
            for order in option_orders:
                if (
                    order.filled_qty == 0
                    and order.client_order_id.startswith("ta-wheel-")
                    and order.submitted_at is not None
                    and now - order.submitted_at >= timedelta(minutes=10)
                ):
                    try:
                        self.broker.cancel_stale_option_order(
                            order.order_id, order.client_order_id
                        )
                    except Exception:
                        cancellation_failed = True

        submitted_ids: list[str] = []
        persisted_intents: list[OptionIntent] = []
        ordered_underlyings = {order.underlying for order in option_orders}
        exits = []
        for position in option_positions:
            if position.underlying in ordered_underlyings:
                continue
            contract = next(
                (
                    item
                    for item in contracts.get(
                        (position.underlying, position.kind.casefold()), ()
                    )
                    if item.symbol == position.symbol
                ),
                None,
            )
            if contract is not None:
                intent = plan_profit_exit(position, contract, now)
                if intent is not None:
                    exits.append(intent)
        exit_error = self._persist_option_intents(
            cycle_id,
            now,
            tuple(exits),
            submitted_ids,
            persisted_intents,
        )
        if exit_error is not None:
            return OptionCycleResult(
                cycle_id,
                tuple(persisted_intents),
                tuple(submitted_ids),
                exit_error,
            )

        entry_reason = self._option_entry_gate(
            now, decisions, settling, cancellation_failed
        )
        if entry_reason is not None:
            return OptionCycleResult(
                cycle_id,
                tuple(persisted_intents),
                tuple(submitted_ids),
                entry_reason if not persisted_intents else None,
            )

        accepted_entries = []
        proposed_exposure = dict(fixed_exposure)
        put_collateral = sum(reservations.put_collateral.values(), Decimal("0"))
        wheel_exposure = put_collateral + sum(
            shares * prices[symbol]
            for symbol, shares in reservations.covered_shares.items()
        )
        risk_rejected = False
        for symbol in self.settings.watchlist:
            if symbol in settling or symbol in equity_open_orders:
                continue
            if (
                self._last_equity_due_time == due_time
                and symbol in self._last_equity_order_symbols
            ):
                continue
            decision = decisions[symbol].rating
            signal = decision.strip().casefold()
            if signal in {"buy", "overweight"}:
                kind = "put"
            elif signal in {"hold", "underweight"}:
                kind = "call"
            else:
                continue
            intent = plan_new_entry(
                symbol,
                decision,
                equities,
                option_positions,
                option_orders,
                contracts.get((symbol, kind), ()),
                now,
                earnings[symbol],
                min(account.cash, account.options_buying_power) - put_collateral,
            )
            if intent is None:
                continue
            added_collateral = (
                intent.qty * _intent_strike(intent) * CONTRACT_MULTIPLIER
                if intent.kind.casefold() == "put"
                else Decimal("0")
            )
            added_wheel = (
                added_collateral
                if intent.kind.casefold() == "put"
                else intent.qty * CONTRACT_MULTIPLIER * prices[symbol]
            )
            if (
                wheel_exposure + added_wheel
                > Decimal(str(self.settings.options_max_equity_fraction)) * account.equity
                or put_collateral + added_collateral > account.cash
                or put_collateral + added_collateral > account.options_buying_power
            ):
                continue
            candidate_exposure = dict(proposed_exposure)
            for underlying, exposure in option_intent_delta_exposure(
                (intent,), prices
            ).items():
                candidate_exposure[underlying] = (
                    candidate_exposure.get(underlying, Decimal("0")) + exposure
                )
            try:
                equity_targets = conviction_targets(
                    {
                        underlying: decisions[underlying].rating
                        for underlying in self.settings.watchlist
                    },
                    max(account.cash - put_collateral - added_collateral, Decimal("0")),
                    self.settings.max_cash_allocation,
                )
                scaled = scale_equity_targets(
                    equity_targets,
                    candidate_exposure,
                    account.equity,
                    close_history,
                    self.settings.target_volatility,
                    self.settings.max_volatility,
                    self.settings.max_gross_leverage,
                )
                if (
                    scaled.forecast_volatility
                    > Decimal(str(self.settings.target_volatility))
                    or scaled.gross_leverage
                    > Decimal(str(self.settings.max_gross_leverage))
                ):
                    raise ValueError("combined risk exceeds limit")
            except (ArithmeticError, ValueError):
                risk_rejected = True
                continue
            accepted_entries.append(intent)
            proposed_exposure = candidate_exposure
            put_collateral += added_collateral
            wheel_exposure += added_wheel

        if not accepted_entries:
            reason = (
                "combined portfolio risk exceeds limit"
                if risk_rejected
                else "no eligible option entry"
            )
            return OptionCycleResult(
                cycle_id,
                tuple(persisted_intents),
                tuple(submitted_ids),
                reason if not persisted_intents else None,
            )

        persisted_before_entries = len(persisted_intents)
        entry_error = self._persist_option_intents(
            cycle_id,
            now,
            tuple(accepted_entries),
            submitted_ids,
            persisted_intents,
        )
        if len(persisted_intents) > persisted_before_entries:
            self.state.mark_option_entry_date(now.astimezone(NEW_YORK).date())
        return OptionCycleResult(
            cycle_id,
            tuple(persisted_intents),
            tuple(submitted_ids),
            entry_error,
        )

    def _option_contract_snapshot(self, now, decisions, positions):
        requested = {
            (position.underlying, position.kind.casefold()) for position in positions
        }
        for symbol, decision in decisions.items():
            signal = decision.rating.strip().casefold()
            if signal in {"buy", "overweight"}:
                requested.add((symbol, "put"))
            elif signal in {"hold", "underweight"}:
                requested.add((symbol, "call"))
        return {
            key: self.broker.option_contracts(key[0], key[1], now)
            for key in requested
        }

    def _observe_wheel_phases(self, now, equities, positions, orders):
        settling = set()
        for symbol in self.settings.watchlist:
            symbol_positions = tuple(
                position for position in positions if position.underlying == symbol
            )
            symbol_orders = tuple(order for order in orders if order.underlying == symbol)
            shares = sum(
                (equity.qty for equity in equities if equity.symbol == symbol), Decimal("0")
            )
            short = next(
                (position for position in symbol_positions if position.qty < 0), None
            )
            opening = next(
                (
                    order
                    for order in symbol_orders
                    if order.position_intent.casefold() == "sell_to_open"
                ),
                None,
            )
            active = short or opening
            if active is not None:
                phase = f"short_{active.kind.casefold()}"
            elif shares >= CONTRACT_MULTIPLIER:
                phase = "long_shares"
            else:
                phase = "empty"
            fingerprint = "|".join(
                [f"shares={shares}"]
                + sorted(
                    f"position={item.symbol}:{item.qty}" for item in symbol_positions
                )
                + sorted(
                    f"order={item.symbol}:{item.position_intent}:{item.qty}:{item.filled_qty}"
                    for item in symbol_orders
                )
            )
            self.state.observe_wheel_phase(symbol, phase, fingerprint, now)
            if self.state.wheel_phase(symbol) == "settling":
                settling.add(symbol)
        return settling

    def _option_entry_gate(self, now, decisions, settling, cancellation_failed):
        if cancellation_failed:
            return "stale option cancellation failed"
        local = now.astimezone(NEW_YORK)
        if local.time().replace(tzinfo=None) < _entry_time(self.settings.options_entry_time_et):
            return "option entry time has not arrived"
        if self.state.last_option_entry_date() == local.date():
            return "option entry already planned today"
        if len(decisions) != len(self.settings.watchlist):
            return "waiting for fresh decisions for all 7 symbols"
        if len(settling) == len(self.settings.watchlist):
            return "wheel positions are settling"
        return None

    def _persist_option_intents(
        self,
        cycle_id,
        now,
        intents,
        submitted_ids,
        persisted_intents,
    ):
        if not intents:
            return None
        execution_error = None
        if self.settings.options_auto_execute:
            try:
                validate_execution_mode(
                    self.settings.alpaca_mode,
                    True,
                    self.settings.live_trading_ack,
                )
                if (
                    self.settings.alpaca_mode == "live"
                    and self.settings.live_options_ack != LIVE_OPTIONS_ACKNOWLEDGMENT
                ):
                    raise ValueError("live options acknowledgment is required")
            except ValueError as error:
                execution_error = str(error)
        errors = []
        for intent in intents:
            try:
                spec = self.broker.prepare_option_order(intent, cycle_id)
                unresolved = self.state.unresolved_option_client_order_id(
                    intent.symbol,
                    intent.position_intent,
                    intent.qty,
                    intent.limit_price,
                )
                if unresolved is not None:
                    spec = replace(spec, client_order_id=unresolved)
                self.state.record_option_intent(
                    cycle_id,
                    now,
                    intent.symbol,
                    intent.underlying,
                    intent.position_intent,
                    intent.qty,
                    intent.limit_price,
                    spec.client_order_id,
                )
                persisted_intents.append(intent)
                if execution_error is not None:
                    self.state.update_option_intent(
                        cycle_id, intent.symbol, "error", spec.client_order_id
                    )
                    continue
                if not self.settings.options_auto_execute:
                    self.state.update_option_intent(
                        cycle_id, intent.symbol, "planned", spec.client_order_id
                    )
                    continue
                try:
                    order_id = self.broker.submit_option_idempotent(spec)
                except Exception:
                    errors.append(intent.symbol)
                    self.state.update_option_intent(
                        cycle_id, intent.symbol, "error", spec.client_order_id
                    )
                else:
                    submitted_ids.append(order_id)
                    self.state.update_option_intent(
                        cycle_id, intent.symbol, "submitted", spec.client_order_id
                    )
            except Exception:
                errors.append(intent.symbol)
        if execution_error is not None:
            return execution_error
        if errors:
            return f"option submission errors: {', '.join(errors)}"
        return None

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
        return self._market_eligible_symbols(partition)

    def _market_eligible_symbols(self, symbols: tuple[str, ...]) -> tuple[str, ...]:
        has_equity = any(detect_asset_type(symbol).value == "stock" for symbol in symbols)
        equity_open = self.broker.equity_market_is_open() if has_equity else False
        return tuple(
            symbol
            for symbol in symbols
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


def _entry_time(value: str) -> time:
    try:
        parsed = datetime.strptime(value, "%H:%M").time()
    except (TypeError, ValueError) as error:
        raise ValueError("options_entry_time_et must use HH:MM") from error
    return parsed


def _intent_strike(intent: OptionIntent) -> Decimal:
    try:
        return Decimal(intent.symbol[-8:]) / Decimal("1000")
    except (ArithmeticError, ValueError) as error:
        raise ValueError("invalid option strike") from error


def _read_earnings_cache(
    path: Path,
    symbols: tuple[str, ...],
    now: datetime,
) -> dict[str, date]:
    payload = json.loads(path.read_text())
    if payload.get("source") != "Wall Street Horizon":
        raise ValueError("earnings cache source is invalid")
    retrieved_at = datetime.fromisoformat(payload["retrieved_at"])
    _require_aware(retrieved_at)
    age = now - retrieved_at
    if age < timedelta(0) or age >= timedelta(hours=24):
        raise ValueError("earnings cache is stale")
    raw_symbols = payload.get("symbols")
    if not isinstance(raw_symbols, dict) or set(raw_symbols) != set(symbols):
        raise ValueError("earnings cache does not match watchlist")
    result = {symbol: date.fromisoformat(raw_symbols[symbol]) for symbol in symbols}
    local_date = now.astimezone(NEW_YORK).date()
    if any(value <= local_date for value in result.values()):
        raise ValueError("earnings cache must contain future dates")
    return result
