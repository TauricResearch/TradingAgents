from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

from .broker import Position
from .config import Aggressiveness, Config

# Map TradingAgents 5-tier rating to a numeric score for ranking within buckets.
_SIGNAL_SCORE: dict[str, int] = {
    "Buy": 5,
    "Overweight": 4,
    "Hold": 3,
    "Underweight": 2,
    "Sell": 1,
}


@dataclass
class Action:
    ticker: str
    action: str       # "BUY", "SELL", or "HOLD"
    signal: str       # raw TradingAgents 5-tier rating
    score: int        # higher = more conviction in the direction
    rationale: str    # first substantive line from the PM decision
    owned: bool
    price: float      # current share price (0 if unknown)
    affordable: bool  # True if price <= available cash, or already owned


def _is_buy(signal: str, aggressiveness: Aggressiveness) -> bool:
    if aggressiveness == Aggressiveness.AGGRESSIVE:
        return signal in ("Buy", "Overweight")
    return signal == "Buy"


def _is_sell(signal: str, aggressiveness: Aggressiveness) -> bool:
    if aggressiveness == Aggressiveness.AGGRESSIVE:
        return signal in ("Sell", "Underweight")
    return signal == "Sell"


def _extract_rationale(final_state: dict) -> str:
    text = final_state.get("final_trade_decision", "")
    for line in text.splitlines():
        stripped = line.strip("*# \t")
        if len(stripped) > 30:
            return stripped[:200]
    return text[:200]


def detect_condition(cash: float, positions: list, cash_threshold: float) -> int:
    """Return strategy condition 1–4.

    1 — cash available, no positions held
    2 — cash available, at least one position held
    3 — no cash, no positions held
    4 — no cash, at least one position held
    """
    has_cash = cash >= cash_threshold
    has_positions = bool(positions)
    if has_cash and not has_positions:
        return 1
    if has_cash and has_positions:
        return 2
    if not has_cash and not has_positions:
        return 3
    return 4


def audit_positions(positions: List[Position]) -> List[dict]:
    """Serialize positions and annotate with strategy-doc risk flags.

    Flags:
        concentration_risk   — single position > 10% of portfolio value
        drawdown_15pct       — position down > 15% from cost basis
        sector_concentration — sector > 25% of portfolio value
    """
    if not positions:
        return []

    total_value = sum(p.market_value for p in positions)
    sector_values: dict[str, float] = {}
    for p in positions:
        sector_values[p.sector] = sector_values.get(p.sector, 0.0) + p.market_value

    result = []
    for p in positions:
        flags = []
        if total_value > 0 and p.market_value / total_value > 0.10:
            flags.append("concentration_risk")
        if p.cost_basis > 0 and p.current_price < p.cost_basis * 0.85:
            flags.append("drawdown_15pct")
        if (
            p.sector not in ("Unknown", None, "")
            and total_value > 0
            and sector_values.get(p.sector, 0.0) / total_value > 0.25
        ):
            flags.append("sector_concentration")
        result.append({
            "ticker": p.ticker,
            "shares": p.shares,
            "cost_basis": p.cost_basis,
            "current_price": p.current_price,
            "sector": p.sector,
            "market_value": p.market_value,
            "flags": flags,
        })
    return result


def aggregate(
    results: List[Tuple[str, dict, str]],
    owned_tickers: set,
    cfg: Config,
    run_date: date,
    cash: float = 0.0,
    price_map: Optional[Dict[str, float]] = None,
) -> List[Action]:
    pm = price_map or {}
    actions: List[Action] = []

    for ticker, final_state, signal in results:
        owned = ticker in owned_tickers
        score = _SIGNAL_SCORE.get(signal, 3)
        rationale = _extract_rationale(final_state)
        price = pm.get(ticker, 0.0)

        # Affordable: already owned, OR we have meaningful cash and the stock is within reach
        affordable = owned or (
            cash >= cfg.cash_threshold and (price == 0.0 or price <= cash)
        )

        if _is_sell(signal, cfg.aggressiveness):
            action = "SELL"
        elif _is_buy(signal, cfg.aggressiveness):
            action = "BUY"
        else:
            action = "HOLD"

        actions.append(Action(
            ticker=ticker,
            action=action,
            signal=signal,
            score=score,
            rationale=rationale,
            owned=owned,
            price=price,
            affordable=affordable,
        ))

    # SELL first (most bearish first), then BUY (most bullish first), then HOLD.
    _order = {"SELL": 0, "BUY": 1, "HOLD": 2}

    def _sort_key(a: Action) -> tuple:
        if a.action == "SELL":
            return (_order[a.action], a.score)
        return (_order[a.action], -a.score)

    actions.sort(key=_sort_key)
    return actions
