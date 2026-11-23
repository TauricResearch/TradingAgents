"""Discounted cash flow: a fading-growth FCF forecast and a Gordon-growth terminal value.

Pure functions; every figure the valuation report shows comes from here.
"""

from __future__ import annotations

from dataclasses import dataclass

from tradingagents.valuation.wacc import ValuationError

# Terminal growth must sit this far below WACC, or the Gordon denominator is near zero
# and the value explodes.
MIN_SPREAD = 0.005


def free_cash_flow(cfo: float, capex: float) -> float:
    """FCF = operating cash flow - capital expenditure (capex as a positive outflow)."""
    return cfo - abs(capex)


def historical_growth(fcfs: list[float], floor: float, cap: float) -> tuple[float | None, str]:
    """(growth, note): the compound annual growth of positive FCF history, clamped to [floor, cap].

    Needs at least two fiscal years whose first and last FCF are both positive; None
    otherwise, for the caller to apply its stated default.
    """
    if len(fcfs) < 2 or fcfs[0] <= 0 or fcfs[-1] <= 0:
        return None, "free cash flow history is too short or not positive at both ends for a growth rate"
    years = len(fcfs) - 1
    cagr = (fcfs[-1] / fcfs[0]) ** (1 / years) - 1
    growth = min(max(cagr, floor), cap)
    note = f"{years}-year FCF CAGR {cagr:.1%}" + ("" if growth == cagr else f", clamped to {growth:.1%}")
    return growth, note


def fade_growth(initial: float, terminal: float, years: int) -> list[float]:
    """Linear fade: year 1 grows at ``initial``, year ``years`` at ``terminal``.

    g_t = initial + (terminal - initial) * (t - 1) / (years - 1)
    """
    if years < 2:
        raise ValuationError("the forecast needs at least 2 years")
    return [initial + (terminal - initial) * (t - 1) / (years - 1) for t in range(1, years + 1)]


def project_fcf(base_fcf: float, growth: list[float]) -> list[float]:
    """FCF_t = FCF_{t-1} * (1 + g_t), starting from the last reported FCF."""
    out, current = [], base_fcf
    for g in growth:
        current *= 1 + g
        out.append(current)
    return out


def present_value(cash_flows: list[float], rate: float) -> list[float]:
    """PV_t = CF_t / (1 + rate)^t for t = 1..n (year-end discounting)."""
    return [cf / (1 + rate) ** t for t, cf in enumerate(cash_flows, start=1)]


def gordon_terminal_value(last_fcf: float, rate: float, terminal_growth: float) -> float:
    """TV = FCF_N * (1 + g) / (WACC - g), valued at the end of year N."""
    if rate - terminal_growth < MIN_SPREAD:
        raise ValuationError(
            f"WACC ({rate:.2%}) must exceed terminal growth ({terminal_growth:.2%}) by at least "
            f"{MIN_SPREAD:.1%} for a terminal value"
        )
    return last_fcf * (1 + terminal_growth) / (rate - terminal_growth)


@dataclass(frozen=True)
class DcfResult:
    growth: list[float]
    fcf: list[float]
    pv_fcf: list[float]
    terminal_value: float
    pv_terminal: float
    enterprise_value: float
    equity_value: float
    value_per_share: float
    wacc: float
    terminal_growth: float

    @property
    def terminal_share(self) -> float:
        """Share of enterprise value that comes from the terminal value."""
        return self.pv_terminal / self.enterprise_value


def run_dcf(base_fcf: float, growth: list[float], rate: float, terminal_growth: float,
            total_debt: float, cash: float, shares: float) -> DcfResult:
    """Enterprise value, equity value and value per share.

    EV = sum PV(FCF_t) + PV(TV); equity = EV - debt + cash; per share = equity / shares.
    """
    if base_fcf <= 0:
        raise ValuationError(f"base free cash flow is not positive ({base_fcf:,.0f}); a growth DCF does not apply")
    if shares <= 0:
        raise ValuationError("share count is not positive")
    fcf = project_fcf(base_fcf, growth)
    pv = present_value(fcf, rate)
    tv = gordon_terminal_value(fcf[-1], rate, terminal_growth)
    pv_tv = tv / (1 + rate) ** len(fcf)
    ev = sum(pv) + pv_tv
    equity = ev - total_debt + cash
    return DcfResult(growth, fcf, pv, tv, pv_tv, ev, equity, equity / shares, rate, terminal_growth)


WACC_STEPS = (-0.02, -0.01, 0.0, 0.01, 0.02)
GROWTH_STEPS = (-0.01, -0.005, 0.0, 0.005, 0.01)


def sensitivity(base_fcf: float, growth: list[float], rate: float, terminal_growth: float,
                total_debt: float, cash: float, shares: float,
                wacc_steps=WACC_STEPS, growth_steps=GROWTH_STEPS):
    """Value per share on a WACC x terminal-growth grid around the base case.

    Returns (wacc values, growth values, rows) with one row per WACC; a cell is None
    where WACC does not exceed terminal growth by ``MIN_SPREAD``. The explicit-period
    growth path is held fixed, so only the discount rate and terminal growth move.
    """
    rates = [rate + d for d in wacc_steps]
    growths = [terminal_growth + d for d in growth_steps]
    rows = []
    for r in rates:
        row = []
        for g in growths:
            try:
                row.append(run_dcf(base_fcf, growth, r, g, total_debt, cash, shares).value_per_share)
            except ValuationError:
                row.append(None)
        rows.append(row)
    return rates, growths, rows
