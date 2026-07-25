"""Fund-only LangChain tools backed by normalized deterministic data."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.fund_data import fetch_fund_snapshot
from tradingagents.instruments import resolve_instrument

_preloaded_snapshot: ContextVar[dict | None] = ContextVar(
    "tradingagents_preloaded_fund_snapshot",
    default=None,
)


@contextmanager
def use_preloaded_fund_snapshot(snapshot: dict | None) -> Iterator[None]:
    token = _preloaded_snapshot.set(deepcopy(snapshot) if snapshot else None)
    try:
        yield
    finally:
        _preloaded_snapshot.reset(token)


def _snapshot(ticker: str, curr_date: str, benchmark: str):
    preloaded = _preloaded_snapshot.get()
    instrument = (preloaded or {}).get("instrument") or {}
    if (
        preloaded
        and instrument.get("canonical_symbol") == ticker
        and preloaded.get("analysis_date") == curr_date
        and preloaded.get("benchmark_symbol") == benchmark
    ):
        return deepcopy(preloaded)
    descriptor = resolve_instrument(ticker, "fund")
    return fetch_fund_snapshot(descriptor, curr_date, benchmark).to_dict()


@tool
def get_fund_profile(
    ticker: Annotated[str, "fund ticker symbol"],
    curr_date: Annotated[str, "analysis date, yyyy-mm-dd"],
    benchmark: Annotated[str, "benchmark ticker"] = "SPY",
) -> dict:
    """Return normalized fund profile and provider/date warnings."""
    data = _snapshot(ticker, curr_date, benchmark)
    return {"profile": data["profile"], "warnings": data["warnings"], "source": data["source"]}


@tool
def get_fund_holdings(
    ticker: Annotated[str, "fund ticker symbol"],
    curr_date: Annotated[str, "analysis date, yyyy-mm-dd"],
    benchmark: Annotated[str, "benchmark ticker"] = "SPY",
) -> dict:
    """Return normalized top holdings and allocation weights."""
    data = _snapshot(ticker, curr_date, benchmark)
    return {"top": data["top_holdings"], "sectors": data["sectors"], "asset_classes": data["asset_classes"], "warnings": data["warnings"]}


@tool
def get_fund_performance(
    ticker: Annotated[str, "fund ticker symbol"],
    curr_date: Annotated[str, "analysis date, yyyy-mm-dd"],
    benchmark: Annotated[str, "benchmark ticker"] = "SPY",
) -> dict:
    """Return Python-computed fund return, risk, and benchmark metrics."""
    data = _snapshot(ticker, curr_date, benchmark)
    return {"metrics": data["metrics"], "warnings": data["warnings"]}
