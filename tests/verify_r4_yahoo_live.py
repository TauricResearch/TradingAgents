"""Run one R4 settlement with Yahoo prices and the course LLM.

Run manually from the repository root with a local .env or API key environment variable.
The memory log is written outside the Git repository for presentation evidence.
"""

import os
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import yfinance

from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.memory import TradingMemoryLog, settlement
from tradingagents.memory.reflection import Reflector


def main() -> None:
    if not os.environ.get("OPENAI_COMPATIBLE_API_KEY"):
        raise SystemExit("OPENAI_COMPATIBLE_API_KEY is required")

    yfinance.set_tz_cache_location(str(Path.cwd() / ".venv" / "r4-live-yf-cache"))
    evidence_dir = Path.cwd().parent / "pre_evidence"
    evidence_dir.mkdir(exist_ok=True)
    log_path = evidence_dir / f"r4-yahoo-live-{uuid4().hex[:8]}.md"
    log = TradingMemoryLog({"memory_log_path": str(log_path)})
    log.store_decision(
        "BABA",
        "2026-10-01",
        "**Rating**: Buy\n\nTest-only thesis: BABA may outperform SPY over five trading days.",
    )
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

    fetched = {}
    real_fetch_returns = settlement.fetch_returns

    def capture_returns(*args, **kwargs):
        result = real_fetch_returns(*args, **kwargs)
        fetched["result"] = result
        return result

    with patch.object(settlement, "fetch_returns", side_effect=capture_returns):
        result = settlement.settle_pending("BABA", log, Reflector(llm), config)

    if result.failed or result.settled != [("BABA", "2026-10-01")]:
        raise RuntimeError(f"R4 live settlement failed: {result}")
    gross_raw, gross_alpha, days, resolved = fetched["result"]
    net_raw, net_alpha = settlement.apply_trading_costs(gross_raw, gross_alpha, 10.0)
    entry = log.load_entries()[0]
    if entry["pending"] or not entry["reflection"].strip():
        raise RuntimeError("R4 live settlement did not store a reflection")
    if (entry["raw"], entry["alpha"]) != (f"{net_raw:+.1%}", f"{net_alpha:+.1%}"):
        raise RuntimeError("R4 live log does not match the calculated net returns")

    print("R4 LIVE SETTLEMENT: PASS")
    print("Prices: Yahoo Finance / yfinance (BABA and SPY)")
    print("Reflection: course model CS5351/DeepSeek-V4-Flash")
    print(f"Trade date: 2026-10-01; resolved: {resolved}; holding: {days} trading days")
    print(f"Gross return: {gross_raw:+.4%}; net return: {net_raw:+.4%}")
    print(f"Gross alpha: {gross_alpha:+.4%}; net alpha: {net_alpha:+.4%}")
    print(f"Memory log: {log_path}")


if __name__ == "__main__":
    main()
