from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tradingagents.database.base import Base


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    lookback_period: Mapped[str] = mapped_column(String(20), nullable=False)
    sector_filter: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_filter: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_results: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("created", "processing", "completed", "failed", name="discovery_status"),
        default="created",
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    trending_stocks: Mapped[list["TrendingStockResult"]] = relationship(
        "TrendingStockResult",
        back_populates="discovery_run",
        cascade="all, delete-orphan",
    )


class TrendingStockResult(Base):
    __tablename__ = "trending_stock_results"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    discovery_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("discovery_runs.id"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sentiment: Mapped[float] = mapped_column(Float, nullable=False)
    sector: Mapped[str] = mapped_column(
        Enum(
            "technology",
            "healthcare",
            "finance",
            "energy",
            "consumer_goods",
            "industrials",
            "other",
            name="stock_sector",
        ),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        Enum(
            "earnings",
            "merger_acquisition",
            "regulatory",
            "product_launch",
            "executive_change",
            "other",
            name="event_category",
        ),
        nullable=False,
    )
    news_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    discovery_run: Mapped["DiscoveryRun"] = relationship(
        "DiscoveryRun", back_populates="trending_stocks"
    )
    source_articles: Mapped[list["DiscoveryArticle"]] = relationship(
        "DiscoveryArticle",
        back_populates="trending_stock",
        cascade="all, delete-orphan",
    )


class DiscoveryArticle(Base):
    __tablename__ = "discovery_articles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    trending_stock_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trending_stock_results.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    content_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticker_mentions: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    trending_stock: Mapped["TrendingStockResult"] = relationship(
        "TrendingStockResult", back_populates="source_articles"
    )
