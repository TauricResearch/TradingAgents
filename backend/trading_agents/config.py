"""Typed configuration for TradingAgents.

`TradingAgentsConfig` is a Pydantic `BaseSettings` model that:
- validates every field at construction time
- reads TRADINGAGENTS_* environment variables automatically
- keeps full backward-compat with the legacy dict-based DEFAULT_CONFIG

Usage (new code):
    from tradingagents.config import TradingAgentsConfig
    cfg = TradingAgentsConfig(llm_provider="anthropic", max_debate_rounds=3)
    ta = TradingAgentsGraph(config=cfg)

Usage (legacy dict still works):
    from tradingagents.default_config import DEFAULT_CONFIG
    ta = TradingAgentsGraph(config=DEFAULT_CONFIG)
"""
import os
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_HOME = Path.home() / ".tradingagents"


class TradingAgentsConfig(BaseSettings):
    """Typed, validated configuration for TradingAgentsGraph.

    All fields can be overridden via TRADINGAGENTS_* environment variables.
    Complex types (lists, dicts) accept JSON strings in env vars.
    """

    model_config = SettingsConfigDict(
        env_prefix="TRADINGAGENTS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",             # unknown env vars are silently ignored
        populate_by_name=True,      # allow both field name and alias
        env_ignore_empty=True,      # treat empty-string env vars as not set
    )

    # ── File paths ─────────────────────────────────────────────────────────────
    project_dir: str = Field(
        default_factory=lambda: str(Path(__file__).parent.resolve()),
    )
    results_dir: str = Field(
        default_factory=lambda: str(_HOME / "logs"),
        # backward-compat: TRADINGAGENTS_RESULTS_DIR (pydantic auto-maps this)
    )
    data_cache_dir: str = Field(
        default_factory=lambda: str(_HOME / "cache"),
        # legacy env var was TRADINGAGENTS_CACHE_DIR
        validation_alias=AliasChoices(
            "TRADINGAGENTS_CACHE_DIR",
            "TRADINGAGENTS_DATA_CACHE_DIR",
        ),
    )
    memory_log_path: str = Field(
        default_factory=lambda: str(_HOME / "memory" / "trading_memory.md"),
    )
    memory_log_max_entries: Optional[int] = Field(default=None, ge=1)

    # ── LLM settings ───────────────────────────────────────────────────────────
    llm_provider: str = "openai"
    deep_think_llm: str = "gpt-5.4"
    quick_think_llm: str = "gpt-5.4-mini"
    backend_url: Optional[str] = Field(
        default=None,
        # legacy: TRADINGAGENTS_LLM_BACKEND_URL
        validation_alias=AliasChoices(
            "TRADINGAGENTS_LLM_BACKEND_URL",
            "TRADINGAGENTS_BACKEND_URL",
        ),
    )

    # Provider-specific thinking configuration
    google_thinking_level: Optional[str] = None    # "high", "minimal", …
    openai_reasoning_effort: Optional[str] = None  # "high", "medium", "low"
    anthropic_effort: Optional[str] = None         # "high", "medium", "low"

    # ── Graph behaviour ────────────────────────────────────────────────────────
    checkpoint_enabled: bool = False
    output_language: str = "English"
    max_debate_rounds: int = Field(default=1, ge=1, le=10)
    max_risk_discuss_rounds: int = Field(
        default=1,
        ge=1,
        le=10,
        # legacy: TRADINGAGENTS_MAX_RISK_ROUNDS
        validation_alias=AliasChoices(
            "TRADINGAGENTS_MAX_RISK_ROUNDS",
            "TRADINGAGENTS_MAX_RISK_DISCUSS_ROUNDS",
        ),
    )
    max_recur_limit: int = Field(default=1000, ge=1)
    analyst_concurrency_limit: int = Field(default=1, ge=1)

    # ── Prompt configuration ───────────────────────────────────────────────────
    super_portfolio_manager_prompt: str = (
        "You are a Super Portfolio Manager advising a new investor with a $100,000 portfolio. "
        "Your team of analysts and traders has analyzed multiple assets, and your job is to build a "
        "clear, beginner-friendly allocation across those assets. "
        "Prioritize capital preservation, diversification, position sizing discipline, and "
        "risk-adjusted returns over aggressive speculation. "
        "Provide percentage allocations for each ticker (e.g., AAPL: 40%, MSFT: 35%) and include a "
        "cash allocation when the risk/reward profile is not attractive. "
        "Avoid concentrating too much capital in a single high-risk asset unless the reports provide "
        "unusually strong evidence. "
        "Write a detailed but easy-to-understand summary explaining the allocation strategy, the key "
        "risks, and what a new investor should monitor after entering the positions."
    )

    # ── Data fetching ──────────────────────────────────────────────────────────
    news_article_limit: int = Field(default=20, ge=1)
    global_news_article_limit: int = Field(default=10, ge=1)
    global_news_lookback_days: int = Field(default=7, ge=1)
    global_news_queries: list[str] = Field(
        default_factory=lambda: [
            "Federal Reserve interest rates inflation",
            "S&P 500 earnings GDP economic outlook",
            "geopolitical risk trade war sanctions",
            "ECB Bank of England BOJ central bank policy",
            "oil commodities supply chain energy",
        ]
    )

    # ── Data vendors ───────────────────────────────────────────────────────────
    data_vendors: dict[str, str] = Field(
        default_factory=lambda: {
            "core_stock_apis": "yfinance",
            "technical_indicators": "yfinance",
            "fundamental_data": "yfinance",
            "news_data": "yfinance",
        }
    )
    # Tool-level overrides (take precedence over category-level data_vendors)
    tool_vendors: dict[str, str] = Field(default_factory=dict)

    # ── Benchmarks ─────────────────────────────────────────────────────────────
    benchmark_ticker: Optional[str] = None
    benchmark_map: dict[str, str] = Field(
        default_factory=lambda: {
            ".NS":  "^NSEI",    # NSE India (Nifty 50)
            ".BO":  "^BSESN",   # BSE India (Sensex)
            ".T":   "^N225",    # Tokyo (Nikkei 225)
            ".HK":  "^HSI",     # Hong Kong (Hang Seng)
            ".L":   "^FTSE",    # London (FTSE 100)
            ".TO":  "^GSPTSE",  # Toronto (TSX Composite)
            ".AX":  "^AXJO",    # Australia (ASX 200)
            "":     "SPY",      # default for US-listed tickers
        }
    )

    # ── Validators ─────────────────────────────────────────────────────────────
    @field_validator("llm_provider", mode="before")
    @classmethod
    def normalise_provider(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("anthropic_effort", "openai_reasoning_effort", mode="before")
    @classmethod
    def normalise_effort(cls, v):
        if v is None:
            return v
        return v.strip().lower()

    # ── Compatibility ──────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        """Return a plain dict identical in shape to the legacy DEFAULT_CONFIG.

        Existing code that passes a dict to TradingAgentsGraph continues to
        work without modification.
        """
        return self.model_dump()
