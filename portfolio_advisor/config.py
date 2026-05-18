from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum


class Aggressiveness(str, Enum):
    CONSERVATIVE = "conservative"
    AGGRESSIVE = "aggressive"


@dataclass
class Config:
    aggressiveness: Aggressiveness = Aggressiveness.CONSERVATIVE

    # Cash threshold: minimum balance to be considered "has cash" (strategy Condition detection)
    cash_threshold: float = 100.0

    # Screener thresholds
    min_avg_volume: int = 500_000
    price_range_pct: float = 0.20
    momentum_days: int = 5
    max_candidates: int = 50

    # Aggressive mode technical filters (strategy doc: Condition 1 Aggressive, Step 2)
    min_market_cap_b: float = 2.0   # minimum market cap in billions
    min_rsi: float = 55.0           # RSI lower bound (trending bullish)
    max_rsi: float = 75.0           # RSI upper bound (not yet overbought)

    # Scheduled job times (all ET, 24h format)
    intraday_check_times: list = field(
        default_factory=lambda: ["09:32", "11:30", "13:30", "15:30"]
    )
    eod_scan_time: str = "16:15"
    premarket_scan_time: str = "09:00"

    # TradingAgents config overrides
    llm_provider: str = os.getenv("TRADINGAGENTS_LLM_PROVIDER", "openai")
    deep_think_llm: str = os.getenv("TRADINGAGENTS_DEEP_MODEL", "gpt-4o")
    quick_think_llm: str = os.getenv("TRADINGAGENTS_QUICK_MODEL", "gpt-4o-mini")
    max_debate_rounds: int = 1
    max_risk_discuss_rounds: int = 1
    results_dir: str = os.getenv(
        "TRADINGAGENTS_RESULTS_DIR",
        os.path.join(os.path.expanduser("~"), ".tradingagents", "logs"),
    )
    data_cache_dir: str = os.getenv(
        "TRADINGAGENTS_CACHE_DIR",
        os.path.join(os.path.expanduser("~"), ".tradingagents", "cache"),
    )

    # Web UI
    web_host: str = "0.0.0.0"
    web_port: int = 5001

    # Internal paths (resolved relative to this file)
    data_dir: str = os.path.join(os.path.dirname(__file__), "data")
    state_file: str = os.path.join(os.path.dirname(__file__), "data", "state.json")


config = Config()
