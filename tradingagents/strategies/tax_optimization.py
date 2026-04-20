"""Tax-Loss Harvesting with CGT Discount Optimization (§13.1-13.2).

Enhances tax-loss harvesting by considering the Australian 12-month CGT
discount rule. Lots held >12 months get a 50% CGT discount on gains,
so selling short-term loss lots first maximizes tax benefit (full offset)
while preserving long-term lots that benefit from the discount.

Signal output:
- Tickers with harvestable short-term losses → SUPPORTS (sell for full offset)
- Tickers with only long-term losses → NEUTRAL (50% discount reduces benefit)
- Tickers with no losses → CONTRADICTS (no tax benefit from selling)

Reference: Kakushadze & Serur §13.1-13.2 — "Tax-Loss Harvesting"
"""

from __future__ import annotations

import datetime

from tradingagents.strategies.base import BaseStrategy, StrategySignal


class TaxOptimizationStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: Identifies tax-loss harvesting opportunities. Tips: Only relevant for taxable accounts. Consider wash-sale rules (30-day window). Strongest near fiscal year-end. Combine with fundamental view — don't harvest losses on stocks you want to keep."

    name = "tax_optimization"
    description = "CGT discount-aware lot selection for tax-loss harvesting"
    target_analysts = ["portfolio"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        lots: list[dict] = kwargs.get("lots", [])
        current_price: float = kwargs.get("current_price", 0)

        if not lots or current_price <= 0:
            return self._neutral(ticker, date, "requires portfolio lot data — pass lots=[] and current_price via kwargs")

        today = datetime.datetime.strptime(date, "%Y-%m-%d")
        short_term_loss = 0.0
        long_term_loss = 0.0
        short_term_gain = 0.0
        long_term_gain = 0.0
        harvest_lots: list[dict] = []

        for lot in lots:
            try:
                lot_date = datetime.datetime.strptime(lot["date"], "%Y-%m-%d")
                qty = lot.get("qty", 0)
                cost = lot.get("price", 0)
            except (KeyError, ValueError):
                continue

            if qty <= 0 or cost <= 0:
                continue

            pnl = (current_price - cost) * qty
            held_days = (today - lot_date).days
            is_long_term = held_days >= 365

            if pnl < 0:
                if is_long_term:
                    long_term_loss += pnl
                else:
                    short_term_loss += pnl
                harvest_lots.append({
                    "date": lot["date"],
                    "qty": qty,
                    "cost": cost,
                    "pnl": round(pnl, 2),
                    "held_days": held_days,
                    "cgt_type": "long-term" if is_long_term else "short-term",
                    "tax_benefit": round(abs(pnl) if not is_long_term else abs(pnl) * 0.5, 2),
                })
            else:
                if is_long_term:
                    long_term_gain += pnl
                else:
                    short_term_gain += pnl

        total_loss = short_term_loss + long_term_loss
        # Tax benefit: short-term losses offset at 100%, long-term at 50% (CGT discount)
        tax_benefit = abs(short_term_loss) + abs(long_term_loss) * 0.5

        if total_loss == 0:
            return self._neutral(ticker, date, "no unrealised losses")

        # Sort harvest candidates: short-term first (higher tax benefit), then by loss size
        harvest_lots.sort(key=lambda l: (0 if l["cgt_type"] == "short-term" else 1, l["pnl"]))

        if short_term_loss < 0:
            signal = "STRONG"
            direction = "SUPPORTS"
            label = f"${short_term_loss:+,.0f} short-term loss (100% offset)"
            if long_term_loss < 0:
                label += f" + ${long_term_loss:+,.0f} long-term (50% offset)"
        elif long_term_loss < 0:
            signal = "MODERATE"
            direction = "NEUTRAL"
            label = f"${long_term_loss:+,.0f} long-term loss only (50% CGT discount reduces benefit)"
        else:
            signal = "WEAK"
            direction = "NEUTRAL"
            label = "minimal harvestable losses"

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal=signal,
            value=round(tax_benefit, 2),
            value_label=f"${tax_benefit:,.0f} tax benefit — {label}",
            direction=direction,
            detail={
                "short_term_loss": round(short_term_loss, 2),
                "long_term_loss": round(long_term_loss, 2),
                "short_term_gain": round(short_term_gain, 2),
                "long_term_gain": round(long_term_gain, 2),
                "tax_benefit": round(tax_benefit, 2),
                "harvest_lots": harvest_lots,
                "n_harvest_lots": len(harvest_lots),
            },
        )

    def _neutral(self, ticker: str, date: str, reason: str) -> StrategySignal:
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0,
            value_label=f"N/A ({reason})",
            direction="NEUTRAL", detail={},
        )
