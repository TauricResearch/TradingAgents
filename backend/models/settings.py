import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


def _json_default(value: Any) -> str:
    return json.dumps(value)


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # Trading mode
    trading_mode: Mapped[str] = mapped_column(String(20), default="simulation")
    active_broker: Mapped[str] = mapped_column(String(50), default="simulation")
    active_data_vendor: Mapped[str] = mapped_column(String(50), default="yfinance")

    # Cron
    cron_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    cron_schedule: Mapped[str] = mapped_column(String(100), default="0 9 * * 1-5")
    price_tolerance_pct: Mapped[float] = mapped_column(Float, default=0.5)

    # Watchlist and analysts stored as JSON strings
    _watchlist: Mapped[str] = mapped_column("watchlist", Text, default='[]')
    _selected_analysts: Mapped[str] = mapped_column(
        "selected_analysts",
        Text,
        default='["market", "news", "fundamentals", "social"]',
    )

    # LLM
    llm_provider: Mapped[str] = mapped_column(String(50), default="openai")
    deep_think_llm: Mapped[str] = mapped_column(String(100), default="gpt-4o")
    quick_think_llm: Mapped[str] = mapped_column(String(100), default="gpt-4o-mini")
    backend_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Provider-specific thinking/reasoning settings
    openai_reasoning_effort: Mapped[str | None] = mapped_column(String(20), nullable=True)
    anthropic_effort: Mapped[str | None] = mapped_column(String(20), nullable=True)
    google_thinking_level: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Output & graph behaviour
    output_language: Mapped[str] = mapped_column(String(50), default="English")
    analyst_concurrency_limit: Mapped[int] = mapped_column(Integer, default=1)
    checkpoint_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    max_recur_limit: Mapped[int] = mapped_column(Integer, default=1000)

    # News fetching limits
    news_article_limit: Mapped[int] = mapped_column(Integer, default=20)
    global_news_article_limit: Mapped[int] = mapped_column(Integer, default=10)
    global_news_lookback_days: Mapped[int] = mapped_column(Integer, default=7)

    # Benchmark override (None = auto-detect from ticker suffix)
    benchmark_ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Azure OpenAI deployment name (only needed when provider=azure)
    azure_deployment: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Per-category data vendor (overrides active_data_vendor for each category)
    data_vendor_core_stock: Mapped[str] = mapped_column(String(50), default="yfinance")
    data_vendor_technicals: Mapped[str] = mapped_column(String(50), default="yfinance")
    data_vendor_fundamentals: Mapped[str] = mapped_column(String(50), default="yfinance")
    data_vendor_news: Mapped[str] = mapped_column(String(50), default="yfinance")

    # Debate rounds
    max_debate_rounds: Mapped[int] = mapped_column(Integer, default=1)
    max_risk_rounds: Mapped[int] = mapped_column(Integer, default=1)

    # Risk limits
    max_position_size_pct: Mapped[float] = mapped_column(Float, default=10.0)
    max_risk_per_trade_pct: Mapped[float] = mapped_column(Float, default=2.0)

    # Eskiye dönük analizleri dahil et: önceki DB raporlarını past_context'e ekler
    include_historical_analyses: Mapped[bool] = mapped_column(Boolean, default=False)

    # Encrypted broker credentials (JSON string of {api_key, api_secret})
    broker_credentials_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def watchlist(self) -> list[str]:
        return json.loads(self._watchlist or "[]")

    @watchlist.setter
    def watchlist(self, value: list[str]):
        self._watchlist = json.dumps(value)

    @property
    def selected_analysts(self) -> list[str]:
        return json.loads(self._selected_analysts or '[]')

    @selected_analysts.setter
    def selected_analysts(self, value: list[str]):
        self._selected_analysts = json.dumps(value)
