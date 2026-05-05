from __future__ import annotations

from typing import Any


def build_macro_regime(final_state: dict[str, Any]) -> dict[str, Any]:
    market_report = final_state.get("market_report") or ""
    news_report = final_state.get("news_report") or ""
    macro_report = final_state.get("macro_report") or ""
    text = " ".join(part for part in (market_report, news_report, macro_report) if isinstance(part, str)).strip()
    return {
        "available": bool(text),
        "summary": text[:240],
        "note": "Use rates, volatility, breadth, and event lag to contextualize issuer claims.",
    }
