"""Minimal daily-bar backtest engine for validated trade signals."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from typing import Any

from .agent_contracts import TradeDirection, TradeSignal
from .backtest_contracts import (
    BacktestConfig,
    BacktestMetrics,
    BacktestResult,
    BacktestRoundTrip,
    BacktestTrade,
    BacktestWarning,
    BacktestWarningSeverity,
    EquityPoint,
    validate_signal_timing,
)
from .data_contracts import PriceBar


def run_daily_signal_backtest(
    *,
    config: BacktestConfig,
    price_bars: list[PriceBar],
    signals: list[TradeSignal],
) -> BacktestResult:
    """Run a small deterministic daily-bar simulation over TradeSignal inputs."""

    bar_map = _bars_by_date_symbol(price_bars)
    dates = sorted(d for d in bar_map if config.start_date <= d <= config.end_date)
    symbols = set(config.symbols)
    pending_signals = sorted(
        [signal for signal in signals if signal.symbol in symbols],
        key=lambda signal: (signal.as_of_date, signal.symbol),
    )

    cash = config.initial_cash
    positions: dict[str, float] = defaultdict(float)
    trades: list[BacktestTrade] = []
    equity_curve: list[EquityPoint] = []
    warning_events: list[BacktestWarning] = []
    executed_signal_ids: set[int] = set()

    if not dates:
        warning_events.append(
            _warning(
                code="no_price_bars",
                message="No price bars are available inside the configured backtest window.",
                severity=BacktestWarningSeverity.ERROR,
            )
        )

    for current_date in dates:
        prices = bar_map[current_date]
        equity_before = _portfolio_equity(cash, positions, prices)

        for idx, signal in enumerate(pending_signals):
            if idx in executed_signal_ids:
                continue
            if signal.as_of_date > current_date:
                continue
            if signal.as_of_date == current_date and not config.execution.allow_same_day_signal:
                continue
            if signal.symbol not in prices:
                continue
            try:
                validate_signal_timing(
                    signal,
                    current_date,
                    allow_same_day=config.execution.allow_same_day_signal,
                )
            except ValueError as exc:
                warning_events.append(
                    _warning(
                        code="invalid_signal_timing",
                        message=f"Skipped {signal.symbol} signal from {signal.as_of_date}: {exc}",
                        symbol=signal.symbol,
                        date=current_date,
                        signal_date=signal.as_of_date,
                    )
                )
                executed_signal_ids.add(idx)
                continue

            trade = _execute_signal(
                signal=signal,
                current_date=current_date,
                close_price=prices[signal.symbol].close,
                cash=cash,
                current_quantity=positions[signal.symbol],
                equity=equity_before,
                allow_short=config.execution.allow_short,
                commission_bps=config.execution.commission_bps,
                slippage_bps=config.execution.slippage_bps,
            )
            executed_signal_ids.add(idx)
            if trade is None:
                continue

            new_cash = cash - trade.quantity * trade.price - trade.commission
            new_position = positions[signal.symbol] + trade.quantity
            trade = trade.model_copy(
                update={
                    "cash_after": new_cash,
                    "position_after": new_position,
                }
            )
            cash = new_cash
            positions[signal.symbol] = new_position
            trades.append(trade)
            equity_before = _portfolio_equity(cash, positions, prices)

        equity = _portfolio_equity(cash, positions, prices)
        gross_exposure = _gross_exposure(positions, prices, equity)
        net_exposure = _net_exposure(positions, prices, equity)
        equity_curve.append(
            EquityPoint(
                date=current_date,
                equity=equity,
                cash=cash,
                gross_exposure_pct=gross_exposure,
                net_exposure_pct=net_exposure,
            )
        )

    for idx, signal in enumerate(pending_signals):
        if idx not in executed_signal_ids and signal.as_of_date <= config.end_date:
            warning_events.append(
                _warning(
                    code="signal_not_executed",
                    message=(
                        f"No eligible execution bar was found for {signal.symbol} "
                        f"signal from {signal.as_of_date}."
                    ),
                    symbol=signal.symbol,
                    signal_date=signal.as_of_date,
                )
            )

    round_trips = _compute_round_trips(trades)
    metrics = _compute_metrics(config, equity_curve, trades, round_trips)
    return BacktestResult(
        config=config,
        metrics=metrics,
        trades=trades,
        round_trips=round_trips,
        equity_curve=equity_curve,
        assumptions={
            "execution_price": "daily close with configured slippage",
            "signal_execution": "first eligible bar after signal.as_of_date unless same-day execution is enabled",
            "position_target": "signal.proposed_position_pct of current equity",
            "round_trip_method": "FIFO long-position matching; open positions are excluded from closed-trade metrics",
        },
        warnings=[event.message for event in warning_events],
        warning_events=warning_events,
    )


def _execute_signal(
    *,
    signal: TradeSignal,
    current_date: date,
    close_price: float,
    cash: float,
    current_quantity: float,
    equity: float,
    allow_short: bool,
    commission_bps: float,
    slippage_bps: float,
) -> BacktestTrade | None:
    target_pct = signal.proposed_position_pct or 0.0
    if signal.direction == TradeDirection.HOLD:
        return None
    if signal.direction == TradeDirection.SELL and not allow_short:
        target_pct = 0.0
    elif signal.direction == TradeDirection.SELL and allow_short:
        target_pct = -target_pct

    current_notional = current_quantity * close_price
    target_notional = equity * target_pct
    delta_notional = target_notional - current_notional
    if abs(delta_notional) < 1e-9:
        return None

    side = TradeDirection.BUY if delta_notional > 0 else TradeDirection.SELL
    slippage = slippage_bps / 10_000.0
    exec_price = close_price * (1.0 + slippage if side == TradeDirection.BUY else 1.0 - slippage)
    quantity = delta_notional / exec_price
    notional = quantity * exec_price
    commission = abs(notional) * commission_bps / 10_000.0
    if quantity > 0 and cash < notional + commission:
        affordable_notional = max(0.0, cash / (1.0 + commission_bps / 10_000.0))
        if affordable_notional <= 0:
            return None
        quantity = affordable_notional / exec_price
        notional = quantity * exec_price
        commission = abs(notional) * commission_bps / 10_000.0

    return BacktestTrade(
        symbol=signal.symbol,
        date=current_date,
        direction=side,
        quantity=quantity,
        price=exec_price,
        notional=notional,
        commission=commission,
        source_signal_date=signal.as_of_date,
    )


def _bars_by_date_symbol(price_bars: list[PriceBar]) -> dict[date, dict[str, PriceBar]]:
    by_date: dict[date, dict[str, PriceBar]] = defaultdict(dict)
    for bar in price_bars:
        by_date[bar.date][bar.symbol] = bar
    return by_date


def _portfolio_equity(
    cash: float,
    positions: dict[str, float],
    prices: dict[str, PriceBar],
) -> float:
    return cash + sum(quantity * prices[symbol].close for symbol, quantity in positions.items() if symbol in prices)


def _gross_exposure(
    positions: dict[str, float],
    prices: dict[str, PriceBar],
    equity: float,
) -> float:
    if equity <= 0:
        return 0.0
    exposure = sum(abs(quantity * prices[symbol].close) for symbol, quantity in positions.items() if symbol in prices)
    return exposure / equity


def _net_exposure(
    positions: dict[str, float],
    prices: dict[str, PriceBar],
    equity: float,
) -> float:
    if equity <= 0:
        return 0.0
    exposure = sum(quantity * prices[symbol].close for symbol, quantity in positions.items() if symbol in prices)
    return exposure / equity


def _compute_round_trips(trades: list[BacktestTrade]) -> list[BacktestRoundTrip]:
    open_lots: dict[str, list[dict[str, Any]]] = defaultdict(list)
    round_trips: list[BacktestRoundTrip] = []

    for trade in sorted(trades, key=lambda item: (item.date, item.symbol)):
        if trade.quantity > 0:
            open_lots[trade.symbol].append(
                {
                    "remaining_quantity": trade.quantity,
                    "original_quantity": trade.quantity,
                    "entry_date": trade.date,
                    "entry_price": trade.price,
                    "entry_commission_per_unit": trade.commission / trade.quantity,
                    "source_signal_date": trade.source_signal_date,
                }
            )
            continue

        if trade.quantity >= 0:
            continue

        quantity_to_close = abs(trade.quantity)
        original_exit_quantity = quantity_to_close
        exit_commission_per_unit = trade.commission / original_exit_quantity if original_exit_quantity else 0.0

        while quantity_to_close > 1e-9 and open_lots[trade.symbol]:
            lot = open_lots[trade.symbol][0]
            closed_quantity = min(quantity_to_close, lot["remaining_quantity"])
            entry_commission = closed_quantity * lot["entry_commission_per_unit"]
            exit_commission = closed_quantity * exit_commission_per_unit
            gross_pnl = closed_quantity * (trade.price - lot["entry_price"])
            net_pnl = gross_pnl - entry_commission - exit_commission
            cost_basis = closed_quantity * lot["entry_price"] + entry_commission
            return_pct = net_pnl / cost_basis if cost_basis else 0.0

            round_trips.append(
                BacktestRoundTrip(
                    symbol=trade.symbol,
                    entry_date=lot["entry_date"],
                    exit_date=trade.date,
                    entry_direction=TradeDirection.BUY,
                    quantity=closed_quantity,
                    entry_price=lot["entry_price"],
                    exit_price=trade.price,
                    gross_pnl=gross_pnl,
                    net_pnl=net_pnl,
                    return_pct=return_pct,
                    holding_days=(trade.date - lot["entry_date"]).days,
                    source_entry_signal_date=lot["source_signal_date"],
                    source_exit_signal_date=trade.source_signal_date,
                )
            )

            lot["remaining_quantity"] -= closed_quantity
            quantity_to_close -= closed_quantity
            if lot["remaining_quantity"] <= 1e-9:
                open_lots[trade.symbol].pop(0)

    return round_trips


def _compute_metrics(
    config: BacktestConfig,
    equity_curve: list[EquityPoint],
    trades: list[BacktestTrade],
    round_trips: list[BacktestRoundTrip],
) -> BacktestMetrics:
    if not equity_curve:
        return BacktestMetrics(
            total_return_pct=0.0,
            max_drawdown_pct=0.0,
            win_rate_pct=None,
            profit_factor=None,
            average_trade_return_pct=None,
            average_holding_days=None,
            max_consecutive_losses=None,
            turnover_pct=0.0,
            average_exposure_pct=0.0,
        )

    start_equity = config.initial_cash
    end_equity = equity_curve[-1].equity
    total_return = end_equity / start_equity - 1.0
    returns = _daily_returns(equity_curve)
    max_drawdown = _max_drawdown([point.equity for point in equity_curve])
    cagr = _cagr(start_equity, end_equity, equity_curve[0].date, equity_curve[-1].date)
    volatility = _annualized_volatility(returns)
    sharpe = _sharpe(returns, volatility)
    sortino = _sortino(returns)
    turnover = sum(abs(trade.notional) for trade in trades) / start_equity
    average_exposure = sum(point.gross_exposure_pct for point in equity_curve) / len(equity_curve)
    trade_quality = _trade_quality_metrics(round_trips)

    return BacktestMetrics(
        total_return_pct=total_return,
        cagr_pct=cagr,
        annualized_volatility_pct=volatility,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown_pct=max_drawdown,
        win_rate_pct=trade_quality["win_rate_pct"],
        profit_factor=trade_quality["profit_factor"],
        average_trade_return_pct=trade_quality["average_trade_return_pct"],
        average_holding_days=trade_quality["average_holding_days"],
        max_consecutive_losses=trade_quality["max_consecutive_losses"],
        turnover_pct=turnover,
        average_exposure_pct=average_exposure,
    )


def _trade_quality_metrics(round_trips: list[BacktestRoundTrip]) -> dict[str, float | int | None]:
    if not round_trips:
        return {
            "win_rate_pct": None,
            "profit_factor": None,
            "average_trade_return_pct": None,
            "average_holding_days": None,
            "max_consecutive_losses": None,
        }

    wins = [item for item in round_trips if item.net_pnl > 0]
    losses = [item for item in round_trips if item.net_pnl < 0]
    gross_profit = sum(item.net_pnl for item in wins)
    gross_loss = abs(sum(item.net_pnl for item in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    return {
        "win_rate_pct": len(wins) / len(round_trips),
        "profit_factor": profit_factor,
        "average_trade_return_pct": sum(item.return_pct for item in round_trips) / len(round_trips),
        "average_holding_days": sum(item.holding_days for item in round_trips) / len(round_trips),
        "max_consecutive_losses": _max_consecutive_losses(round_trips),
    }


def _max_consecutive_losses(round_trips: list[BacktestRoundTrip]) -> int:
    max_losses = 0
    current = 0
    for item in round_trips:
        if item.net_pnl < 0:
            current += 1
            max_losses = max(max_losses, current)
        else:
            current = 0
    return max_losses


def _daily_returns(equity_curve: list[EquityPoint]) -> list[float]:
    returns: list[float] = []
    for prev, curr in zip(equity_curve, equity_curve[1:], strict=False):
        if prev.equity > 0:
            returns.append(curr.equity / prev.equity - 1.0)
    return returns


def _max_drawdown(equity_values: list[float]) -> float:
    peak = equity_values[0]
    max_dd = 0.0
    for value in equity_values:
        peak = max(peak, value)
        if peak > 0:
            max_dd = min(max_dd, value / peak - 1.0)
    return abs(max_dd)


def _cagr(start_equity: float, end_equity: float, start: date, end: date) -> float | None:
    days = (end - start).days
    if days <= 0 or start_equity <= 0:
        return None
    years = days / 365.25
    return (end_equity / start_equity) ** (1 / years) - 1.0


def _annualized_volatility(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((item - mean) ** 2 for item in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(252)


def _sharpe(returns: list[float], annualized_volatility: float | None) -> float | None:
    if not returns or annualized_volatility in (None, 0.0):
        return None
    mean_daily = sum(returns) / len(returns)
    return mean_daily * 252 / annualized_volatility


def _sortino(returns: list[float]) -> float | None:
    if not returns:
        return None
    downside = [item for item in returns if item < 0]
    if not downside:
        return None
    downside_dev = math.sqrt(sum(item**2 for item in downside) / len(downside)) * math.sqrt(252)
    if downside_dev == 0:
        return None
    return (sum(returns) / len(returns)) * 252 / downside_dev


def _warning(
    *,
    code: str,
    message: str,
    severity: BacktestWarningSeverity = BacktestWarningSeverity.WARNING,
    symbol: str | None = None,
    date: date | None = None,
    signal_date: date | None = None,
) -> BacktestWarning:
    return BacktestWarning(
        code=code,
        message=message,
        severity=severity,
        symbol=symbol,
        date=date,
        signal_date=signal_date,
    )
