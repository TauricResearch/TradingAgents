from sqlalchemy import and_
from sqlalchemy.orm import Session

from tradingagents.database.models.trading import (
    TradeExecution,
    TradeReflection,
    TradingDecision,
)
from tradingagents.database.repositories.base import BaseRepository


class TradingDecisionRepository(BaseRepository[TradingDecision]):
    def __init__(self, session: Session):
        super().__init__(session, TradingDecision)

    def get_by_session(self, session_id: str) -> TradingDecision | None:
        return (
            self.session.query(TradingDecision)
            .filter(TradingDecision.session_id == session_id)
            .first()
        )

    def get_by_ticker(self, ticker: str, limit: int = 100) -> list[TradingDecision]:
        return (
            self.session.query(TradingDecision)
            .filter(TradingDecision.ticker == ticker)
            .order_by(TradingDecision.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_by_decision_type(
        self, decision: str, limit: int = 100
    ) -> list[TradingDecision]:
        return (
            self.session.query(TradingDecision)
            .filter(TradingDecision.decision == decision)
            .order_by(TradingDecision.created_at.desc())
            .limit(limit)
            .all()
        )


class TradeExecutionRepository(BaseRepository[TradeExecution]):
    def __init__(self, session: Session):
        super().__init__(session, TradeExecution)

    def get_by_decision(self, decision_id: str) -> TradeExecution | None:
        return (
            self.session.query(TradeExecution)
            .filter(TradeExecution.decision_id == decision_id)
            .first()
        )

    def get_pending(self) -> list[TradeExecution]:
        return (
            self.session.query(TradeExecution)
            .filter(TradeExecution.status == "pending")
            .all()
        )

    def get_by_ticker(self, ticker: str, limit: int = 100) -> list[TradeExecution]:
        return (
            self.session.query(TradeExecution)
            .filter(TradeExecution.ticker == ticker)
            .order_by(TradeExecution.created_at.desc())
            .limit(limit)
            .all()
        )


class TradeReflectionRepository(BaseRepository[TradeReflection]):
    def __init__(self, session: Session):
        super().__init__(session, TradeReflection)

    def get_by_ticker(self, ticker: str, limit: int = 100) -> list[TradeReflection]:
        return (
            self.session.query(TradeReflection)
            .filter(TradeReflection.ticker == ticker)
            .order_by(TradeReflection.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_by_ticker_and_date(
        self, ticker: str, trade_date: str
    ) -> TradeReflection | None:
        return (
            self.session.query(TradeReflection)
            .filter(
                and_(
                    TradeReflection.ticker == ticker,
                    TradeReflection.trade_date == trade_date,
                )
            )
            .first()
        )
