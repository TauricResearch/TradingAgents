"""Cost of capital: CAPM cost of equity, after-tax cost of debt, market-value WACC.

Pure functions over numbers and price series. No vendor calls and no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


class ValuationError(ValueError):
    """A figure cannot be computed; the message says why and is shown in the report."""


@dataclass(frozen=True)
class BetaResult:
    beta: float
    weeks: int
    start: str
    end: str


def weekly_returns(closes: pd.Series) -> pd.Series:
    """Week-over-week returns from daily closes (the last close of each week, Friday-anchored)."""
    weekly = closes.sort_index().resample("W-FRI").last().dropna()
    return weekly.pct_change().dropna()


def beta_from_closes(stock: pd.Series, benchmark: pd.Series, min_weeks: int = 52) -> BetaResult:
    """Beta = cov(stock, benchmark) / var(benchmark) over weekly returns.

    Both series are daily closes with a date index. Returns are each in their own
    currency, as the repo's alpha is. Fewer than ``min_weeks`` aligned weeks is too
    little to estimate a slope, so it raises rather than return a noisy number.
    """
    paired = pd.concat({"s": weekly_returns(stock), "b": weekly_returns(benchmark)}, axis=1).dropna()
    if len(paired) < min_weeks:
        raise ValuationError(
            f"beta needs at least {min_weeks} weeks of returns shared with the benchmark; "
            f"only {len(paired)} are available"
        )
    variance = paired["b"].var()
    if not variance > 0:
        raise ValuationError("the benchmark's weekly returns do not vary, so beta is undefined")
    return BetaResult(
        beta=float(paired["s"].cov(paired["b"]) / variance),
        weeks=len(paired),
        start=paired.index[0].strftime("%Y-%m-%d"),
        end=paired.index[-1].strftime("%Y-%m-%d"),
    )


def cost_of_equity(risk_free: float, beta: float, equity_risk_premium: float) -> float:
    """CAPM: Ke = rf + beta * ERP."""
    return risk_free + beta * equity_risk_premium


def effective_tax_rate(income_tax: float | None, pretax_income: float | None, default: float,
                       floor: float = 0.0, cap: float = 0.35) -> tuple[float, str]:
    """(rate, note): tax / pretax income clamped to [floor, cap], else ``default``."""
    if income_tax is None or pretax_income is None or pretax_income <= 0:
        return default, f"effective tax rate unavailable (no positive pretax income); using the {default:.1%} default"
    raw = income_tax / pretax_income
    rate = min(max(raw, floor), cap)
    note = f"effective tax rate {raw:.1%}" + ("" if rate == raw else f", clamped to {rate:.1%}")
    return rate, note


def after_tax_cost_of_debt(interest_expense: float | None, total_debt: float | None,
                           tax_rate: float) -> float | None:
    """Kd(1 - t) with Kd = interest expense / total debt, or None when either is missing or debt is 0."""
    if interest_expense is None or not total_debt or total_debt <= 0:
        return None
    return abs(interest_expense) / total_debt * (1 - tax_rate)


@dataclass(frozen=True)
class WaccResult:
    wacc: float
    cost_of_equity: float
    after_tax_cost_of_debt: float | None
    equity_value: float
    debt_value: float
    equity_weight: float
    debt_weight: float


def wacc(equity_value: float, debt_value: float, ke: float, kd_after_tax: float | None) -> WaccResult:
    """WACC = E/(D+E) * Ke + D/(D+E) * Kd(1 - t), with market equity and book debt as the debt value.

    No debt (or no cost of debt to apply) means the firm is all equity: WACC = Ke.
    """
    if equity_value <= 0:
        raise ValuationError("market capitalisation is not positive, so the capital weights are undefined")
    debt = debt_value if kd_after_tax is not None and debt_value and debt_value > 0 else 0.0
    total = equity_value + debt
    we, wd = equity_value / total, debt / total
    return WaccResult(
        wacc=we * ke + (wd * kd_after_tax if wd else 0.0),
        cost_of_equity=ke,
        after_tax_cost_of_debt=kd_after_tax,
        equity_value=equity_value,
        debt_value=debt,
        equity_weight=we,
        debt_weight=wd,
    )
