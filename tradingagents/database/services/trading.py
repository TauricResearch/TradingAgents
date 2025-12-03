from typing import Any

from sqlalchemy.orm import Session

from tradingagents.database.models import (
    TradeExecution,
    TradeReflection,
    TradingDecision,
)
from tradingagents.database.repositories import (
    TradeExecutionRepository,
    TradeReflectionRepository,
    TradingDecisionRepository,
)


class TradingService:
    def __init__(self, session: Session):
        self.session = session
        self.decisions = TradingDecisionRepository(session)
        self.executions = TradeExecutionRepository(session)
        self.reflections = TradeReflectionRepository(session)

    def save_trading_decision(
        self,
        session_id: str,
        ticker: str,
        final_state: dict[str, Any],
        signal: str,
    ) -> TradingDecision:
        decision_map = {"BUY": "buy", "SELL": "sell", "HOLD": "hold"}
        decision = decision_map.get(signal.upper(), "hold")

        return self.decisions.create(
            {
                "session_id": session_id,
                "ticker": ticker,
                "decision": decision,
                "trader_plan": final_state.get("trader_investment_plan", ""),
                "investment_plan": final_state.get("investment_plan", ""),
                "final_decision_text": final_state.get("final_trade_decision", ""),
            }
        )

    def record_execution(
        self,
        decision_id: str,
        ticker: str,
        action: str,
        quantity: int,
        price: float,
    ) -> TradeExecution:
        return self.executions.create(
            {
                "decision_id": decision_id,
                "ticker": ticker,
                "action": action,
                "quantity": quantity,
                "price": price,
                "status": "executed",
            }
        )

    def save_reflection(
        self,
        ticker: str,
        trade_date: str,
        decision_id: str | None,
        returns_losses: float,
        reflection_content: str,
    ) -> TradeReflection:
        return self.reflections.create(
            {
                "ticker": ticker,
                "trade_date": trade_date,
                "decision_id": decision_id,
                "actual_return": returns_losses,
                "reflection_content": reflection_content,
            }
        )

    def get_decision_by_session(self, session_id: str) -> TradingDecision | None:
        return self.decisions.get_by_session(session_id)

    def get_decisions_by_ticker(
        self, ticker: str, limit: int = 100
    ) -> list[TradingDecision]:
        return self.decisions.get_by_ticker(ticker, limit)

    def get_pending_executions(self) -> list[TradeExecution]:
        return self.executions.get_pending()
