from datetime import datetime, timezone
from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    trade_date: Mapped[str] = mapped_column(String(20), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), default="stock")
    signal: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Buy/Overweight/Hold/Underweight/Sell

    # Analyst reports
    market_report: Mapped[str] = mapped_column(Text, default="")
    sentiment_report: Mapped[str] = mapped_column(Text, default="")
    news_report: Mapped[str] = mapped_column(Text, default="")
    fundamentals_report: Mapped[str] = mapped_column(Text, default="")
    macro_report: Mapped[str] = mapped_column(Text, default="")
    options_report: Mapped[str] = mapped_column(Text, default="")
    quant_report: Mapped[str] = mapped_column(Text, default="")
    earnings_report: Mapped[str] = mapped_column(Text, default="")
    review_report: Mapped[str] = mapped_column(Text, default="")

    # Decision chain
    investment_plan: Mapped[str] = mapped_column(Text, default="")
    trader_plan: Mapped[str] = mapped_column(Text, default="")
    final_decision: Mapped[str] = mapped_column(Text, default="")

    # Metrics
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    triggered_by: Mapped[str] = mapped_column(String(20), default="manual")  # manual | cron
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
