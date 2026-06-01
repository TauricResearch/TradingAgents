import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class MultiTickerAnalysis(Base):
    __tablename__ = "multi_ticker_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[str] = mapped_column(String(20), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), default="stock")

    # JSON list of ticker symbols
    _tickers: Mapped[str] = mapped_column("tickers", Text, default="[]")

    # JSON list of AnalysisResult IDs for individual ticker runs
    _analysis_ids: Mapped[str] = mapped_column("analysis_ids", Text, default="[]")

    # SuperPortfolioManager output
    super_portfolio_report: Mapped[str] = mapped_column(Text, default="")

    triggered_by: Mapped[str] = mapped_column(String(20), default="manual")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    @property
    def tickers(self) -> list[str]:
        return json.loads(self._tickers or "[]")

    @tickers.setter
    def tickers(self, value: list[str]):
        self._tickers = json.dumps(value)

    @property
    def analysis_ids(self) -> list[int]:
        return json.loads(self._analysis_ids or "[]")

    @analysis_ids.setter
    def analysis_ids(self, value: list[int]):
        self._analysis_ids = json.dumps(value)
