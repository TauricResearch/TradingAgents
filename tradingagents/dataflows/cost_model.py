"""Cost model: FX spreads, ETF slippage, fees."""

from __future__ import annotations
from dataclasses import dataclass

FX_SPREAD_BPS: dict[str, float] = {"BRL": 8, "TRY": 25, "MXN": 6, "INR": 4, "ZAR": 10, "ARS": 20, "CLP": 7, "PLN": 5, "COP": 9, "IDR": 6, "THB": 5, "PHP": 5, "USD": 0, "MULTI": 7}
ETF_SLIPPAGE_BPS: dict[str, float] = {"EWZ": 10, "EWW": 8, "INDA": 6, "EZA": 8, "TUR": 15, "ILF": 7, "EPOL": 6, "VWO": 5, "THD": 5, "COPX": 7}
ETF_FX_BETA: dict[str, float] = {"BRL": 0.90, "MXN": 0.85, "INR": 0.70, "ZAR": 0.80, "TRY": 1.00, "CLP": 0.75, "PLN": 0.60, "COP": 0.80, "IDR": 0.60, "THB": 0.60, "PHP": 0.65, "MULTI": 0.80, "EWZ": 0.90, "EWW": 0.85, "INDA": 0.70, "EZA": 0.80, "TUR": 1.00, "ILF": 0.75, "EPOL": 0.60, "VWO": 0.80, "THD": 0.60}


@dataclass
class CostModel:
    """All-in cost: fee + slippage + FX spread (bps, one-way)."""

    fee_bps: float = 10.0
    slippage_bps: float = 5.0
    fx_spread_bps: float = 7.0

    def total_bps(self) -> float:
        return self.fee_bps + self.slippage_bps + self.fx_spread_bps

    def total_rate(self) -> float:
        return self.total_bps() / 10000.0

    def net_return(self, gross: float) -> float:
        return gross - 2 * self.total_rate() * 100

    def for_currency(self, currency: str) -> "CostModel":
        fx = FX_SPREAD_BPS.get(currency, self.fx_spread_bps)
        return CostModel(fee_bps=self.fee_bps, slippage_bps=self.slippage_bps, fx_spread_bps=fx)

    def cost_breakdown(self) -> dict:
        return {"fee_bps": self.fee_bps, "slippage_bps": self.slippage_bps, "fx_spread_bps": self.fx_spread_bps, "total_bps": self.total_bps()}


def net_expected_return(spread: float, currency: str, cost_model: CostModel | None = None, beta: float | None = None) -> tuple[float, dict]:
    cm = cost_model or CostModel()
    if currency:
        cm = cm.for_currency(currency)
        slip = ETF_SLIPPAGE_BPS.get(currency, cm.slippage_bps)
        cm = CostModel(fee_bps=cm.fee_bps, slippage_bps=slip, fx_spread_bps=cm.fx_spread_bps)
    b = beta if beta is not None else ETF_FX_BETA.get(currency, 0.8)
    gross = spread * b
    net = cm.net_return(gross)
    return net, {**cm.cost_breakdown(), "beta": b, "gross": gross, "net": net}
