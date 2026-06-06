"""Options chain tool (leverage on Strong signals).

Fetches the option chain and selects a contract near a target strike. The fetch
is injectable (offline-testable); ``YFinanceOptionsFetcher`` is the real adapter.
The deterministic Trade function decides Call vs Put on Strong signals; this tool
turns that into a concrete contract.
"""

from __future__ import annotations

from typing import Any, Callable, Optional


def get_options_chain(
    symbol: str,
    *,
    option_type: str,
    expiry: Optional[str] = None,
    live_fn: Optional[Callable[[str, str, Optional[str]], list[dict[str, Any]]]] = None,
) -> list[dict[str, Any]]:
    """Return option contracts (dicts with at least ``strike``). Empty if no source."""
    if live_fn is None:
        return []
    return live_fn(symbol, option_type, expiry)


def select_contract(
    chain: list[dict[str, Any]], *, target_strike: float
) -> Optional[dict[str, Any]]:
    """Pick the contract whose strike is closest to ``target_strike`` (ATM-ish)."""
    candidates = [c for c in chain if c.get("strike") is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda c: abs(float(c["strike"]) - target_strike))


class YFinanceOptionsFetcher:
    """Real adapter over yfinance option_chain. Network-bound (integration)."""

    def __call__(self, symbol: str, option_type: str, expiry: Optional[str]) -> list[dict[str, Any]]:
        import yfinance as yf

        ticker = yf.Ticker(symbol.upper())
        expiries = getattr(ticker, "options", []) or []
        if not expiries:
            return []
        chosen = expiry if expiry in expiries else expiries[0]
        chain = ticker.option_chain(chosen)
        frame = chain.calls if option_type == "call" else chain.puts
        out: list[dict[str, Any]] = []
        for _, row in frame.iterrows():
            out.append({
                "symbol": row.get("contractSymbol"),
                "strike": float(row["strike"]),
                "last_price": float(row.get("lastPrice", 0) or 0),
                "bid": float(row.get("bid", 0) or 0),
                "ask": float(row.get("ask", 0) or 0),
                "expiry": chosen,
                "option_type": option_type,
            })
        return out
