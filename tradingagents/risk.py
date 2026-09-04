from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class RiskScaleResult:
    targets: dict[str, Decimal]
    baseline_volatility: Decimal
    forecast_volatility: Decimal
    scale: Decimal
    gross_leverage: Decimal


def close_returns(
    history: Mapping[str, Sequence[tuple[date, Decimal]]],
) -> dict[str, tuple[Decimal, ...]]:
    if not history:
        raise ValueError("close history is required")
    date_sets = [{day for day, _ in rows} for rows in history.values()]
    common_dates = set.intersection(*date_sets)
    ordered_dates = sorted(common_dates)[-61:]
    if len(ordered_dates) < 41:
        raise ValueError("at least 40 aligned return observations are required")

    result = {}
    for symbol, rows in history.items():
        by_date = {day: _decimal(value, "close price") for day, value in rows}
        closes = [by_date[day] for day in ordered_dates]
        if any(value <= 0 for value in closes):
            raise ValueError("close prices must be positive and finite")
        result[symbol] = tuple(
            closes[index] / closes[index - 1] - Decimal("1")
            for index in range(1, len(closes))
        )
    return result


def forecast_volatility(exposure, equity, returns):
    equity = _decimal(equity, "equity")
    if equity <= 0:
        raise ValueError("equity must be positive and finite")
    portfolio = _portfolio_returns(exposure, equity, returns)
    variance = _annualized_variance(portfolio)
    return variance.sqrt()


def scale_equity_targets(
    equity_targets,
    fixed_option_exposure,
    equity,
    close_history,
    target_volatility,
    max_volatility,
    max_gross_leverage,
):
    returns = close_returns(close_history)
    equity = _decimal(equity, "equity")
    target = _decimal(target_volatility, "target volatility")
    maximum = _decimal(max_volatility, "maximum volatility")
    maximum_gross = _decimal(max_gross_leverage, "maximum gross leverage")
    if target <= 0:
        raise ValueError("target volatility must be positive")
    if maximum <= 0:
        raise ValueError("maximum volatility must be positive")
    if maximum_gross <= 0:
        raise ValueError("maximum gross leverage must be positive")
    gross_limit = maximum_gross * equity
    option_values = {
        symbol: _decimal(value, "fixed option exposure")
        for symbol, value in fixed_option_exposure.items()
    }
    equity_values = {
        symbol: _decimal(value, "equity target") for symbol, value in equity_targets.items()
    }
    option_gross = sum(abs(value) for value in option_values.values())
    equity_gross = sum(abs(value) for value in equity_values.values())
    if equity <= 0 or equity_gross <= 0 or option_gross > gross_limit:
        raise ValueError("valid equity targets and gross capacity are required")

    gross_scale = (gross_limit - option_gross) / equity_gross
    equity_series = _portfolio_returns(equity_values, equity, returns)
    option_series = _portfolio_returns(option_values, equity, returns)
    a = _annualized_variance(equity_series)
    b = _annualized_covariance(equity_series, option_series)
    c = _annualized_variance(option_series)
    discriminant = b * b - a * (c - target * target)
    if a <= 0 or discriminant < 0:
        raise ValueError("portfolio volatility target is infeasible")
    square_root = discriminant.sqrt()
    lower = max(Decimal("0"), (-b - square_root) / a)
    upper = min(gross_scale, (-b + square_root) / a)
    if lower > upper:
        raise ValueError("portfolio volatility target is infeasible")
    scale = upper

    anchor_symbol = next(symbol for symbol in reversed(equity_values) if equity_values[symbol] != 0)
    anchor_value = equity_values[anchor_symbol]
    anchor_target = anchor_value * scale
    targets = {
        symbol: anchor_target * (value / anchor_value) for symbol, value in equity_values.items()
    }
    combined = dict(option_values)
    for symbol, value in targets.items():
        combined[symbol] = combined.get(symbol, Decimal("0")) + value
    forecast = forecast_volatility(combined, equity, returns)
    gross = (sum(abs(value) for value in targets.values()) + option_gross) / equity
    if forecast > maximum:
        raise ValueError("scaled forecast exceeds maximum volatility")
    baseline = forecast_volatility(
        {
            symbol: equity_values.get(symbol, Decimal("0"))
            + option_values.get(symbol, Decimal("0"))
            for symbol in set(equity_values) | set(option_values)
        },
        equity,
        returns,
    )
    return RiskScaleResult(targets, baseline, forecast, scale, gross)


def _portfolio_returns(exposure, equity, returns):
    _aligned_observation_count(returns)
    values = {symbol: _decimal(value, "exposure") for symbol, value in exposure.items()}
    missing_symbols = set(values) - set(returns)
    if missing_symbols:
        raise ValueError("missing return history for exposure")
    for _symbol, series in returns.items():
        for value in series:
            _decimal(value, "return")
    return tuple(
        sum(values.get(symbol, Decimal("0")) / equity * series[index] for symbol, series in returns.items())
        for index in range(len(next(iter(returns.values()))))
    )


def _annualized_variance(values):
    values = tuple(_decimal(value, "return") for value in values)
    if len(values) < 40:
        raise ValueError("40 to 60 aligned returns are required")
    mean = sum(values) / Decimal(len(values))
    variance = sum((value - mean) ** 2 for value in values) / Decimal(len(values) - 1)
    annualized = variance * Decimal("252")
    if not annualized.is_finite():
        raise ValueError("annualized variance must be finite")
    return annualized


def _annualized_covariance(left, right):
    left = tuple(_decimal(value, "return") for value in left)
    right = tuple(_decimal(value, "return") for value in right)
    if len(left) != len(right) or len(left) < 40:
        raise ValueError("40 to 60 aligned returns are required")
    left_mean = sum(left) / Decimal(len(left))
    right_mean = sum(right) / Decimal(len(right))
    annualized = (
        sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
        / Decimal(len(left) - 1)
        * Decimal("252")
    )
    if not annualized.is_finite():
        raise ValueError("annualized covariance must be finite")
    return annualized


def _aligned_observation_count(returns):
    lengths = {len(values) for values in returns.values()}
    if len(lengths) != 1:
        raise ValueError("return histories must be aligned")
    observation_count = lengths.pop() if lengths else 0
    if not 40 <= observation_count <= 60:
        raise ValueError("40 to 60 aligned returns are required")
    return observation_count


def _decimal(value, name):
    converted = Decimal(str(value))
    if not converted.is_finite():
        raise ValueError(f"{name} must be finite")
    return converted
