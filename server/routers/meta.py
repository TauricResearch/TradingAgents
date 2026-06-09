"""Provider metadata, ticker resolution, range stats, defaults."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ticker_resolver import resolve_ticker
from tradingagents.default_config import DEFAULT_CONFIG
from ..deps import require_auth
from ..providers import provider_table
from ..schemas import Defaults, ResolveResult

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/providers")
def providers(_: str = Depends(require_auth)):
    return provider_table()


@router.get("/resolve-ticker", response_model=ResolveResult)
def resolve(q: str, _: str = Depends(require_auth)):
    ticker, message = resolve_ticker(q)
    return ResolveResult(ticker=ticker, message=message)


@router.get("/defaults", response_model=Defaults)
def defaults(_: str = Depends(require_auth)):
    c = DEFAULT_CONFIG
    return Defaults(
        provider=c.get("llm_provider", "doubao"),
        deep_model=c.get("deep_think_llm", ""),
        quick_model=c.get("quick_think_llm", ""),
        selected_analysts=["market"],
        max_debate_rounds=int(c.get("max_debate_rounds", 1)),
        max_risk_discuss_rounds=int(c.get("max_risk_discuss_rounds", 1)),
        output_language=c.get("output_language", "English"),
    )


@router.get("/range-stats")
def range_stats(ticker: str, date: str, _: str = Depends(require_auth)):
    from tradingagents.dataflows.range_stats import (
        RangeStatsUnavailable,
        compute_range_stats,
        format_range_stats_for_webui,
    )
    try:
        return format_range_stats_for_webui(compute_range_stats(ticker, date))
    except RangeStatsUnavailable:
        return None
    except Exception:  # noqa: BLE001 — degrade gracefully like the Streamlit card
        return None
