import logging
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.models.backtest import BacktestConfig, BacktestResult
from tradingagents.models.decisions import (
    SignalType,
    TradingDecision,
    AnalystReport,
    AnalystType,
)
from tradingagents.models.portfolio import PortfolioSnapshot

from .engine import BacktestEngine
from .data_loader import DataLoader

logger = logging.getLogger(__name__)


class AgentBacktestEngine(BacktestEngine):
    def __init__(
        self,
        config: BacktestConfig,
        agent_config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(config)
        self.agent_config = agent_config or config.agent_config
        self.trading_graph: Optional[TradingAgentsGraph] = None
        self._decision_cache: Dict[str, TradingDecision] = {}

    def _initialize(self):
        super()._initialize()

        graph_config = {
            **self.agent_config,
        }

        self.trading_graph = TradingAgentsGraph(
            selected_analysts=self.agent_config.get(
                "selected_analysts",
                ["market", "social", "news", "fundamentals"],
            ),
            debug=self.agent_config.get("debug", False),
            config=graph_config if graph_config else None,
        )

    def _get_decision(
        self,
        ticker: str,
        trading_date: date,
        day_index: int,
    ) -> Optional[TradingDecision]:
        cache_key = f"{ticker}_{trading_date}"
        if cache_key in self._decision_cache:
            return self._decision_cache[cache_key]

        try:
            final_state, signal_info = self.trading_graph.propagate(
                ticker, trading_date
            )

            decision = self._parse_agent_decision(
                ticker, trading_date, final_state, signal_info
            )

            self._decision_cache[cache_key] = decision
            return decision

        except (ValueError, KeyError, RuntimeError, ConnectionError, TimeoutError) as e:
            logger.error(
                "Agent decision failed for %s on %s: %s",
                ticker, trading_date, e
            )
            return None

    def _parse_agent_decision(
        self,
        ticker: str,
        trading_date: date,
        final_state: Dict[str, Any],
        signal_info: Dict[str, Any],
    ) -> TradingDecision:
        signal = self._extract_signal(signal_info)
        confidence = self._extract_confidence(signal_info)

        analyst_reports = []

        if final_state.get("market_report"):
            analyst_reports.append(
                AnalystReport(
                    analyst_type=AnalystType.MARKET,
                    ticker=ticker,
                    report_date=datetime.combine(trading_date, datetime.min.time()),
                    summary=final_state["market_report"][:500],
                    raw_content=final_state["market_report"],
                )
            )

        if final_state.get("sentiment_report"):
            analyst_reports.append(
                AnalystReport(
                    analyst_type=AnalystType.SENTIMENT,
                    ticker=ticker,
                    report_date=datetime.combine(trading_date, datetime.min.time()),
                    summary=final_state["sentiment_report"][:500],
                    raw_content=final_state["sentiment_report"],
                )
            )

        if final_state.get("news_report"):
            analyst_reports.append(
                AnalystReport(
                    analyst_type=AnalystType.NEWS,
                    ticker=ticker,
                    report_date=datetime.combine(trading_date, datetime.min.time()),
                    summary=final_state["news_report"][:500],
                    raw_content=final_state["news_report"],
                )
            )

        if final_state.get("fundamentals_report"):
            analyst_reports.append(
                AnalystReport(
                    analyst_type=AnalystType.FUNDAMENTALS,
                    ticker=ticker,
                    report_date=datetime.combine(trading_date, datetime.min.time()),
                    summary=final_state["fundamentals_report"][:500],
                    raw_content=final_state["fundamentals_report"],
                )
            )

        debate_state = final_state.get("investment_debate_state", {})
        bull_argument = None
        bear_argument = None

        if debate_state.get("bull_history"):
            bull_argument = debate_state["bull_history"][-1] if debate_state["bull_history"] else None
        if debate_state.get("bear_history"):
            bear_argument = debate_state["bear_history"][-1] if debate_state["bear_history"] else None

        risk_state = final_state.get("risk_debate_state", {})
        risk_approved = self._extract_risk_approval(risk_state)

        final_decision_text = final_state.get("final_trade_decision", "")
        recommended_action = self._extract_action(signal_info, final_decision_text)

        return TradingDecision(
            ticker=ticker,
            timestamp=datetime.now(),
            decision_date=datetime.combine(trading_date, datetime.min.time()),
            signal=signal,
            confidence=confidence,
            recommended_action=recommended_action,
            analyst_reports=analyst_reports,
            bull_argument=bull_argument,
            bear_argument=bear_argument,
            debate_rounds=debate_state.get("count", 0),
            risk_manager_approved=risk_approved,
            final_decision=recommended_action,
            rationale=final_decision_text[:1000] if final_decision_text else "",
        )

    def _extract_signal(self, signal_info: Dict[str, Any]) -> SignalType:
        action = signal_info.get("action", "").upper()
        direction = signal_info.get("direction", "").upper()

        if action == "BUY" or direction == "BULLISH":
            confidence = signal_info.get("confidence", 0.5)
            if confidence > 0.8:
                return SignalType.STRONG_BUY
            return SignalType.BUY

        elif action == "SELL" or direction == "BEARISH":
            confidence = signal_info.get("confidence", 0.5)
            if confidence > 0.8:
                return SignalType.STRONG_SELL
            return SignalType.SELL

        return SignalType.HOLD

    def _extract_confidence(self, signal_info: Dict[str, Any]) -> Decimal:
        confidence = signal_info.get("confidence", 0.5)
        if isinstance(confidence, str):
            try:
                confidence = float(confidence.replace("%", "")) / 100
            except ValueError:
                confidence = 0.5

        return Decimal(str(min(max(float(confidence), 0.0), 1.0)))

    def _extract_action(
        self,
        signal_info: Dict[str, Any],
        final_decision_text: str,
    ) -> str:
        action = signal_info.get("action", "")
        if action:
            return action.upper()

        text_upper = final_decision_text.upper()
        if "BUY" in text_upper and "DON'T BUY" not in text_upper:
            return "BUY"
        elif "SELL" in text_upper:
            return "SELL"

        return "HOLD"

    def _extract_risk_approval(self, risk_state: Dict[str, Any]) -> Optional[bool]:
        judge_decision = risk_state.get("judge_decision", "")
        if not judge_decision:
            return None

        text_upper = judge_decision.upper()
        if "APPROVE" in text_upper or "ACCEPT" in text_upper:
            return True
        elif "REJECT" in text_upper or "DENY" in text_upper:
            return False

        return None


def run_agent_backtest(
    tickers: list[str],
    start_date: date,
    end_date: date,
    initial_cash: Decimal = Decimal("100000"),
    agent_config: Optional[Dict[str, Any]] = None,
) -> BacktestResult:
    from tradingagents.models.portfolio import PortfolioConfig

    config = BacktestConfig(
        name=f"Agent Backtest - {', '.join(tickers)}",
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
        portfolio_config=PortfolioConfig(
            initial_cash=initial_cash,
            commission_per_trade=Decimal("1"),
            slippage_percent=Decimal("0.05"),
        ),
        warmup_period=5,
        agent_config=agent_config or {},
    )

    engine = AgentBacktestEngine(config, agent_config)
    return engine.run()
