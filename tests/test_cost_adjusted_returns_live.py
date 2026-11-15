"""Live LLM check for R4 settlement with deterministic local prices."""

import os

import pandas as pd
import pytest

from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.memory import TradingMemoryLog, settlement
from tradingagents.memory.reflection import Reflector


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENAI_COMPATIBLE_API_KEY"),
    reason="OPENAI_COMPATIBLE_API_KEY is not set",
)
def test_course_model_reflects_on_cost_adjusted_settlement(tmp_path, monkeypatch):
    dates = pd.bdate_range("2026-01-05", periods=7)
    prices = {
        "BABA": pd.Series([99, 100, 101, 102, 103, 104, 105], index=dates),
        "SPY": pd.Series([400, 401, 402, 403, 404, 405, 406], index=dates),
    }

    def local_closes(symbol, start_date, end_date):
        series = prices[symbol]
        return series[(series.index >= start_date) & (series.index < end_date)]

    monkeypatch.setattr(settlement, "get_closes", local_closes)
    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "r4-live-memory.md")})
    log.store_decision("BABA", "2026-01-05", "**Rating**: Buy\n\nThesis: improving earnings.")
    llm = create_llm_client(
        "openai_compatible",
        "CS5351/DeepSeek-V4-Flash",
        base_url="https://llm.cs.cityu.edu.hk/v1",
        timeout=60,
        max_retries=0,
    ).get_llm()
    config = {
        "holding_period_days": 5,
        "use_cost_adjusted_returns": True,
        "trading_cost_bps": 10.0,
        "min_commission": 0.0,
        "assumed_trade_notional": 10_000.0,
    }

    result = settlement.settle_pending("BABA", log, Reflector(llm), config)

    assert result.failed == []
    assert result.settled == [("BABA", "2026-01-05")]
    entry = log.load_entries()[0]
    assert (entry["raw"], entry["alpha"], entry["holding"]) == ("+4.8%", "+3.5%", "5d")
    assert entry["pending"] is False
    assert entry["reflection"].strip()
