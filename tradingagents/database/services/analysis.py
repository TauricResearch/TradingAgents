import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from tradingagents.database.models import (
    AnalysisSession,
    AnalystReport,
    InvestmentDebate,
    RiskDebate,
)
from tradingagents.database.repositories import (
    AnalysisSessionRepository,
    AnalystReportRepository,
    InvestmentDebateRepository,
    RiskDebateRepository,
)


class AnalysisService:
    def __init__(self, session: Session):
        self.session = session
        self.sessions = AnalysisSessionRepository(session)
        self.reports = AnalystReportRepository(session)
        self.investment_debates = InvestmentDebateRepository(session)
        self.risk_debates = RiskDebateRepository(session)

    def create_session(self, ticker: str, trade_date: str) -> AnalysisSession:
        return self.sessions.create(
            {
                "ticker": ticker,
                "trade_date": trade_date,
                "status": "running",
            }
        )

    def save_analyst_report(
        self, session_id: str, analyst_type: str, report_content: str
    ) -> AnalystReport:
        return self.reports.create(
            {
                "session_id": session_id,
                "analyst_type": analyst_type,
                "report_content": report_content,
            }
        )

    def save_investment_debate(
        self, session_id: str, debate_state: dict[str, Any]
    ) -> InvestmentDebate:
        return self.investment_debates.create(
            {
                "session_id": session_id,
                "bull_history": json.dumps(debate_state.get("bull_history", [])),
                "bear_history": json.dumps(debate_state.get("bear_history", [])),
                "debate_history": json.dumps(debate_state.get("history", [])),
                "judge_decision": debate_state.get("judge_decision", ""),
                "investment_plan": debate_state.get("current_response", ""),
                "debate_rounds": len(debate_state.get("history", [])),
            }
        )

    def save_risk_debate(
        self, session_id: str, debate_state: dict[str, Any]
    ) -> RiskDebate:
        return self.risk_debates.create(
            {
                "session_id": session_id,
                "risky_history": json.dumps(debate_state.get("risky_history", [])),
                "safe_history": json.dumps(debate_state.get("safe_history", [])),
                "neutral_history": json.dumps(debate_state.get("neutral_history", [])),
                "debate_history": json.dumps(debate_state.get("history", [])),
                "judge_decision": debate_state.get("judge_decision", ""),
                "debate_rounds": len(debate_state.get("history", [])),
            }
        )

    def save_full_state(
        self, ticker: str, trade_date: str, final_state: dict[str, Any]
    ) -> AnalysisSession:
        analysis_session = self.create_session(ticker, trade_date)

        analyst_mappings = [
            ("market", "market_report"),
            ("sentiment", "sentiment_report"),
            ("news", "news_report"),
            ("fundamentals", "fundamentals_report"),
        ]

        for analyst_type, state_key in analyst_mappings:
            report_content = final_state.get(state_key, "")
            if report_content:
                self.save_analyst_report(
                    analysis_session.id, analyst_type, report_content
                )

        investment_debate_state = final_state.get("investment_debate_state", {})
        if investment_debate_state:
            self.save_investment_debate(analysis_session.id, investment_debate_state)

        risk_debate_state = final_state.get("risk_debate_state", {})
        if risk_debate_state:
            self.save_risk_debate(analysis_session.id, risk_debate_state)

        self.sessions.mark_completed(analysis_session.id)

        return analysis_session

    def get_session_by_ticker_date(
        self, ticker: str, trade_date: str
    ) -> AnalysisSession | None:
        return self.sessions.get_by_ticker_and_date(ticker, trade_date)

    def get_latest_session(self, ticker: str) -> AnalysisSession | None:
        return self.sessions.get_latest_by_ticker(ticker)
