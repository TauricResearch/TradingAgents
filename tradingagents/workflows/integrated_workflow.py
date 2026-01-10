"""
Integrated Trading Workflow - Phase 4

Connects all components:
- Ticker Anonymizer
- Regime Detector
- Semantic Fact Checker
- Deterministic Risk Gate
- JSON Schema Enforcement

HARD GATING: Fact check failure = immediate trade rejection
"""

import time
from typing import Dict, Any, Optional
from dataclasses import dataclass

# Import all components
from tradingagents.utils.anonymizer import TickerAnonymizer
from tradingagents.engines.regime_detector import RegimeDetector, MarketRegime
from tradingagents.engines.regime_aware_signals import RegimeAwareSignalEngine
from tradingagents.validation.semantic_fact_checker import SemanticFactChecker, FactCheckResult
from tradingagents.risk.deterministic_risk_gate import DeterministicRiskGate, TradeProposal
from tradingagents.schemas.agent_schemas import (
    AnalystOutput, ResearcherOutput, TradeDecision, FactCheckReport, WorkflowState, SignalType
)
from tradingagents.utils.json_retry import JSONRetryLoop


@dataclass
class WorkflowMetrics:
    """Workflow performance metrics."""
    total_latency: float
    anonymization_time: float
    regime_detection_time: float
    analyst_time: float
    researcher_time: float
    fact_check_time: float
    risk_gate_time: float
    json_retry_count: int


class IntegratedTradingWorkflow:
    """
    Main trading workflow integrating all components.
    
    CRITICAL GATES:
    1. JSON Schema Enforcement (retry loop)
    2. Fact Checker (hard gate - reject on hallucination)
    3. Risk Gate (hard gate - reject on risk violation)
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize workflow with all components.
        
        Args:
            config: Configuration dict
        """
        self.config = config
        
        # Initialize components
        self.anonymizer = TickerAnonymizer(seed=config.get("anonymizer_seed", "blindfire_v1"))
        self.regime_detector = RegimeDetector()
        self.signal_engine = RegimeAwareSignalEngine()
        self.fact_checker = SemanticFactChecker(
            use_local_model=config.get("use_nli_model", True),
            cache_size=config.get("fact_check_cache_size", 10000)
        )
        self.risk_gate = DeterministicRiskGate(config.get("risk_config", {}))
        self.json_retry = JSONRetryLoop(max_retries=config.get("max_json_retries", 2))
        
        # Latency budget (seconds)
        self.fact_check_latency_budget = config.get("fact_check_latency_budget", 2.0)
        
        # Performance tracking
        self.metrics_history = []
    
    def execute_trade_decision(
        self,
        ticker: str,
        trading_date: str,
        market_data: Dict[str, Any],
        ground_truth: Dict[str, Any],
        llm_agents: Dict[str, Any]
    ) -> tuple[TradeDecision, WorkflowMetrics]:
        """
        Execute complete trading workflow.
        
        CRITICAL: Never returns None - always returns a TradeDecision (even if rejected).
        This prevents state machine crashes in LangGraph.
        
        Args:
            ticker: Original ticker (e.g., "AAPL")
            trading_date: Trading date YYYY-MM-DD
            market_data: Market data (prices, indicators)
            ground_truth: Ground truth for fact checking
            llm_agents: Dict of LLM agent callables
        
        Returns:
            (trade_decision, metrics) - decision.action may be "NO_TRADE" if rejected
        """
        workflow_start = time.time()
        metrics = {}
        
        # STEP 1: Anonymize ticker and normalize prices
        anon_start = time.time()
        anon_ticker = self.anonymizer.anonymize_ticker(ticker)
        
        # Normalize prices to base-100
        if "price_data" in market_data:
            market_data["price_data"] = self.anonymizer.normalize_price_series(
                market_data["price_data"],
                base_value=100.0,
                use_adjusted=True  # Use Adj Close for dividends/splits
            )
        
        metrics["anonymization_time"] = time.time() - anon_start
        
        # STEP 2: Detect market regime
        regime_start = time.time()
        prices = market_data.get("price_series")
        regime, regime_metrics = self.regime_detector.detect_regime(prices)
        metrics["regime_detection_time"] = time.time() - regime_start
        
        print(f"📊 Detected Regime: {regime.value}")
        print(f"   Volatility: {regime_metrics['volatility']:.1%}")
        print(f"   Trend Strength (ADX): {regime_metrics['trend_strength']:.1f}")
        
        # STEP 3: Run analysts with JSON enforcement
        analyst_start = time.time()
        
        # Market Analyst
        market_output, market_meta = self.json_retry.invoke_with_retry(
            llm_agents["market_analyst"],
            AnalystOutput,
            "Analyze market data and output JSON",
            {"ticker": anon_ticker, "data": market_data}
        )
        
        if market_output is None:
            print(f"❌ Market analyst failed JSON compliance after {market_meta['attempts']} attempts")
            # DEAD STATE: Return NO_TRADE instead of None
            return self._create_dead_state(
                "JSON_COMPLIANCE_FAILURE",
                f"Market analyst failed after {market_meta['attempts']} attempts",
                workflow_start,
                metrics
            )
        
        metrics["analyst_time"] = time.time() - analyst_start
        
        # STEP 4: Run researchers (Bull/Bear)
        researcher_start = time.time()
        
        bull_output, bull_meta = self.json_retry.invoke_with_retry(
            llm_agents["bull_researcher"],
            ResearcherOutput,
            "Provide bull case arguments in JSON",
            {"ticker": anon_ticker, "analyst_findings": market_output.key_findings}
        )
        
        bear_output, bear_meta = self.json_retry.invoke_with_retry(
            llm_agents["bear_researcher"],
            ResearcherOutput,
            "Provide bear case arguments in JSON",
            {"ticker": anon_ticker, "analyst_findings": market_output.key_findings}
        )
        
        if bull_output is None or bear_output is None:
            print("❌ Researcher failed JSON compliance")
            # DEAD STATE: Return NO_TRADE instead of None
            return self._create_dead_state(
                "JSON_COMPLIANCE_FAILURE",
                "Researcher failed JSON compliance",
                workflow_start,
                metrics
            )
        
        metrics["researcher_time"] = time.time() - researcher_start
        
        # STEP 5: FACT CHECK (HARD GATE)
        fact_check_start = time.time()
        
        # Combine all arguments from researchers
        all_arguments = bull_output.key_arguments + bear_output.key_arguments
        
        # Validate arguments
        fact_results = self.fact_checker.validate_arguments(
            all_arguments,
            ground_truth,
            trading_date
        )
        
        metrics["fact_check_time"] = time.time() - fact_check_start
        
        # Check latency budget
        if metrics["fact_check_time"] > self.fact_check_latency_budget:
            print(f"⚠️  Fact check exceeded latency budget: {metrics['fact_check_time']:.2f}s > {self.fact_check_latency_budget}s")
        
        # Count contradictions
        contradictions = [
            arg for arg, result in fact_results.items()
            if not result.valid
        ]
        
        fact_check_report = FactCheckReport(
            total_arguments=len(all_arguments),
            valid_arguments=len(all_arguments) - len(contradictions),
            invalid_arguments=len(contradictions),
            contradictions=contradictions,
            overall_valid=len(contradictions) == 0
        )
        
        # HARD GATE: Reject if any contradictions
        if not fact_check_report.overall_valid:
            print(f"🚫 FACT CHECK FAILED - TRADE REJECTED")
            print(f"   Contradictions found: {len(contradictions)}")
            for contradiction in contradictions:
                print(f"   - {contradiction}")
                print(f"     Evidence: {fact_results[contradiction].evidence}")
            
            # DEAD STATE: Return NO_TRADE instead of None
            return self._create_dead_state(
                "FACT_CHECK_FAILURE",
                f"Contradictions: {', '.join(contradictions[:3])}",
                workflow_start,
                metrics
            )
        
        print(f"✅ Fact check passed ({len(all_arguments)} arguments validated)")
        
        # STEP 6: RISK GATE (HARD GATE)
        risk_gate_start = time.time()
        
        # Determine trade action (simplified - would use judge logic in production)
        # Determine trade action using TRADER AGENT (Regime Veto)
        # Construct state for Trader
        trader_state = {
            "company_of_interest": ticker,
            "investment_plan": f"Bull Case ({bull_output.confidence:.2f}): {bull_output.key_arguments}\n\nBear Case ({bear_output.confidence:.2f}): {bear_output.key_arguments}",
            "market_report": str(market_output.key_findings),
            "sentiment_report": "N/A",
            "news_report": "N/A",
            "fundamentals_report": "N/A",
            "market_regime": regime.value,
            "volatility_score": regime_metrics['volatility']
        }
        
        # Invoke Trader
        trader_output = llm_agents["trader"](trader_state)
        trader_response = trader_output["trader_investment_plan"]
        
        # Parse Trader Decision
        action = SignalType.HOLD
        confidence = 0.5
        
        if "BUY" in trader_response.upper() and "FINAL TRANSACTION PROPOSAL: **BUY**" in trader_response:
             action = SignalType.BUY
             # Use Bull confidence if BUY, moderated by Trader logic
             confidence = bull_output.confidence 
        elif "SELL" in trader_response.upper() and "FINAL TRANSACTION PROPOSAL: **SELL**" in trader_response:
             action = SignalType.SELL
             confidence = bear_output.confidence
        
        print(f"🧠 Trader Decision: {action.value}")
        print(f"   Reasoning: {trader_response[:100]}...")
        
        # Create trade proposal
        proposal = TradeProposal(
            ticker=anon_ticker,
            action=action.value,
            quantity=None,  # Will be calculated by risk gate
            confidence=confidence,
            reasoning=f"Bull: {bull_output.confidence:.2f}, Bear: {bear_output.confidence:.2f}"
        )
        
        # Validate through risk gate
        portfolio_state = {
            "equity": self.config.get("portfolio_value", 100000),
            "current_drawdown": self.config.get("current_drawdown", 0.0),
            "positions": self.config.get("positions", {}),
            "win_rate": self.config.get("win_rate", 0.55),
            "avg_win": self.config.get("avg_win", 0.03),
            "avg_loss": self.config.get("avg_loss", 0.02)
        }
        
        risk_result = self.risk_gate.validate_and_adjust_trade(
            proposal,
            portfolio_state,
            market_data
        )
        
        metrics["risk_gate_time"] = time.time() - risk_gate_start
        
        # HARD GATE: Reject if risk gate rejects
        if not risk_result["approved"]:
            print(f"🚫 RISK GATE REJECTED TRADE")
            print(f"   Reason: {risk_result['rejection_reason']}")
            
            # DEAD STATE: Return NO_TRADE instead of None
            return self._create_dead_state(
                "RISK_GATE_FAILURE",
                risk_result['rejection_reason'],
                workflow_start,
                metrics
            )
        
        print(f"✅ Risk gate approved")
        if risk_result.get("override_message"):
            print(f"   {risk_result['override_message']}")
        
        # STEP 7: Create final trade decision
        final_decision = TradeDecision(
            action=action,
            quantity=risk_result["adjusted_proposal"].quantity,
            confidence=confidence,
            reasoning=proposal.reasoning,
            fact_check_passed=True,
            risk_gate_passed=True,
            position_size=risk_result["risk_metrics"].get("position_size"),
            stop_loss=risk_result["risk_metrics"].get("stop_loss"),
            risk_pct=risk_result["risk_metrics"].get("trade_risk_pct")
        )
        
        workflow_metrics = self._build_metrics(workflow_start, metrics)
        
        print(f"\n✅ TRADE APPROVED")
        print(f"   Action: {final_decision.action.value}")
        print(f"   Quantity: {final_decision.quantity} shares")
        print(f"   Stop Loss: ${final_decision.stop_loss:.2f}")
        print(f"   Risk: {final_decision.risk_pct:.2%} of portfolio")
        print(f"   Total Latency: {workflow_metrics.total_latency:.2f}s")
        
        return final_decision, workflow_metrics
    
    def _create_dead_state(
        self,
        failure_type: str,
        reason: str,
        workflow_start: float,
        metrics: Dict[str, float]
    ) -> tuple[TradeDecision, WorkflowMetrics]:
        """
        Create a "dead state" trade decision for rejections.
        
        CRITICAL: Never return None - return a valid TradeDecision with action="HOLD"
        and metadata explaining the rejection. This prevents state machine crashes.
        
        Args:
            failure_type: Type of failure (JSON_COMPLIANCE_FAILURE, FACT_CHECK_FAILURE, etc.)
            reason: Human-readable reason
            workflow_start: Workflow start time
            metrics: Current metrics dict
        
        Returns:
            (dead_state_decision, metrics)
        """
        dead_state = TradeDecision(
            action=SignalType.HOLD,  # NO_TRADE represented as HOLD
            quantity=0,
            confidence=0.0,
            reasoning=f"REJECTED: {failure_type} - {reason}",
            fact_check_passed=failure_type != "FACT_CHECK_FAILURE",
            risk_gate_passed=failure_type != "RISK_GATE_FAILURE",
            position_size=0,
            stop_loss=None,
            risk_pct=0.0
        )
        
        workflow_metrics = self._build_metrics(
            workflow_start,
            metrics,
            json_failures=1 if "JSON" in failure_type else 0,
            fact_check_failures=1 if "FACT_CHECK" in failure_type else 0,
            risk_gate_failures=1 if "RISK_GATE" in failure_type else 0
        )
        
        return dead_state, workflow_metrics
    
    def _build_metrics(
        self,
        workflow_start: float,
        metrics: Dict[str, float],
        json_failures: int = 0,
        fact_check_failures: int = 0,
        risk_gate_failures: int = 0
    ) -> WorkflowMetrics:
        """Build workflow metrics object."""
        return WorkflowMetrics(
            total_latency=time.time() - workflow_start,
            anonymization_time=metrics.get("anonymization_time", 0.0),
            regime_detection_time=metrics.get("regime_detection_time", 0.0),
            analyst_time=metrics.get("analyst_time", 0.0),
            researcher_time=metrics.get("researcher_time", 0.0),
            fact_check_time=metrics.get("fact_check_time", 0.0),
            risk_gate_time=metrics.get("risk_gate_time", 0.0),
            json_retry_count=json_failures + fact_check_failures + risk_gate_failures
        )


# Example usage
if __name__ == "__main__":
    import pandas as pd
    import numpy as np
    
    # Configuration
    config = {
        "anonymizer_seed": "blindfire_v1",
        "use_nli_model": False,  # Use fallback for demo
        "max_json_retries": 2,
        "fact_check_latency_budget": 2.0,
        "portfolio_value": 100000,
        "risk_config": {
            "max_position_risk": 0.02,
            "max_portfolio_heat": 0.10,
            "circuit_breaker": 0.15
        }
    }
    
    workflow = IntegratedTradingWorkflow(config)
    
    # Mock data
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    prices = pd.Series(100 + np.cumsum(np.random.randn(100) * 0.5 + 0.3), index=dates)
    
    market_data = {
        "price_series": prices,
        "close": 105.0,
        "atr": 2.5,
        "volume": 50000000,
        "indicators": {"RSI": 55, "MACD": 0.5}
    }
    
    ground_truth = {
        "revenue_growth_yoy": 0.05,
        "price_change_pct": 0.03
    }
    
    print("Workflow initialized. Ready for integration testing.")
