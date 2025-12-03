from datetime import datetime

from sqlalchemy import and_
from sqlalchemy.orm import Session

from tradingagents.database.models.analysis import (
    AnalysisSession,
    AnalystReport,
    InvestmentDebate,
    RiskDebate,
)
from tradingagents.database.repositories.base import BaseRepository


class AnalysisSessionRepository(BaseRepository[AnalysisSession]):
    def __init__(self, session: Session):
        super().__init__(session, AnalysisSession)

    def get_by_ticker_and_date(
        self, ticker: str, trade_date: str
    ) -> AnalysisSession | None:
        return (
            self.session.query(AnalysisSession)
            .filter(
                and_(
                    AnalysisSession.ticker == ticker,
                    AnalysisSession.trade_date == trade_date,
                )
            )
            .first()
        )

    def get_latest_by_ticker(self, ticker: str) -> AnalysisSession | None:
        return (
            self.session.query(AnalysisSession)
            .filter(AnalysisSession.ticker == ticker)
            .order_by(AnalysisSession.created_at.desc())
            .first()
        )

    def get_completed_sessions(self, limit: int = 100) -> list[AnalysisSession]:
        return (
            self.session.query(AnalysisSession)
            .filter(AnalysisSession.status == "completed")
            .order_by(AnalysisSession.completed_at.desc())
            .limit(limit)
            .all()
        )

    def mark_completed(self, session_id: str) -> AnalysisSession | None:
        obj = self.get(session_id)
        if obj:
            obj.status = "completed"
            obj.completed_at = datetime.utcnow()
            self.session.flush()
        return obj

    def mark_failed(self, session_id: str) -> AnalysisSession | None:
        obj = self.get(session_id)
        if obj:
            obj.status = "failed"
            obj.completed_at = datetime.utcnow()
            self.session.flush()
        return obj


class AnalystReportRepository(BaseRepository[AnalystReport]):
    def __init__(self, session: Session):
        super().__init__(session, AnalystReport)

    def get_by_session_and_type(
        self, session_id: str, analyst_type: str
    ) -> AnalystReport | None:
        return (
            self.session.query(AnalystReport)
            .filter(
                and_(
                    AnalystReport.session_id == session_id,
                    AnalystReport.analyst_type == analyst_type,
                )
            )
            .first()
        )

    def get_all_by_session(self, session_id: str) -> list[AnalystReport]:
        return (
            self.session.query(AnalystReport)
            .filter(AnalystReport.session_id == session_id)
            .all()
        )


class InvestmentDebateRepository(BaseRepository[InvestmentDebate]):
    def __init__(self, session: Session):
        super().__init__(session, InvestmentDebate)

    def get_by_session(self, session_id: str) -> InvestmentDebate | None:
        return (
            self.session.query(InvestmentDebate)
            .filter(InvestmentDebate.session_id == session_id)
            .first()
        )


class RiskDebateRepository(BaseRepository[RiskDebate]):
    def __init__(self, session: Session):
        super().__init__(session, RiskDebate)

    def get_by_session(self, session_id: str) -> RiskDebate | None:
        return (
            self.session.query(RiskDebate)
            .filter(RiskDebate.session_id == session_id)
            .first()
        )
