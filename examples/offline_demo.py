"""TradingAgents Offline Demo.

Demonstrates the multi-agent decision architecture (Analysts -> Debate ->
Risk Management -> Portfolio Decision) offline with zero API keys,
mocked data, and simulated agent reasoning.

Usage:
    python examples/offline_demo.py
    python examples/offline_demo.py --ticker AAPL --date 2024-05-10
"""

import argparse
from typing import Dict, Any

# Agent specifications detailing roles, responsibilities, and operational scope
AGENT_REGISTRY: Dict[str, Dict[str, str]] = {
    "Market Analyst": {
        "role": "Technical & Quantitative Analysis",
        "focus": "Evaluates price action, volume trends, moving averages (SMA), and momentum oscillators (RSI, MACD).",
        "cadence": "Continuous market signal generation",
    },
    "Sentiment Analyst": {
        "role": "Alternative Data & News Extraction",
        "focus": "Extracts sentiment polarity from news feeds, social media disclosures, and market discourse.",
        "cadence": "Real-time & event-driven processing",
    },
    "Fundamentals Analyst": {
        "role": "Financial Statement & Valuation Audit",
        "focus": "Evaluates balance sheets, operating margins, P/E multiples, and forward revenue guidance.",
        "cadence": "Filing & earnings-driven analysis",
    },
    "Bull Researcher": {
        "role": "Constructive Growth Advocate",
        "focus": "Synthesizes positive catalysts, market share gains, competitive moats, and upside potential.",
        "cadence": "Interactive debate synthesis",
    },
    "Bear Researcher": {
        "role": "Downside & Vulnerability Skeptic",
        "focus": "Challenges valuation multiples, capital expenditure expansion, and macroeconomic vulnerabilities.",
        "cadence": "Interactive debate rebuttal",
    },
    "Risk Manager": {
        "role": "Capital Preservation & Constraint Enforcement",
        "focus": "Enforces volatility caps, maximum allowable drawdown limits, and portfolio allocation guards.",
        "cadence": "Pre-trade risk audit & sizing",
    },
    "Portfolio Manager": {
        "role": "Executive Capital Allocator",
        "focus": "Synthesizes intelligence from analysts and researchers to formulate binding asset allocations.",
        "cadence": "Final execution approval",
    },
}


def run_offline_simulation(ticker: str = "NVDA", trade_date: str = "2024-05-10") -> Dict[str, Any]:
    """Simulate the multi-agent trading decision pipeline with agent profile context."""
    print("=" * 75)
    print("TradingAgents Offline Demonstration (Multi-Agent System)")
    print(f"Target Ticker: {ticker} | Evaluation Date: {trade_date} | Mode: OFFLINE")
    print("=" * 75)

    # 1. Multi-Source Intelligence & Analysis
    print("\n[Phase 1] Multi-Source Intelligence & Analyst Team")
    
    ma = AGENT_REGISTRY["Market Analyst"]
    print(f"  • {ma['role']} [Market Analyst]:")
    print(f"    Responsibility: {ma['focus']}")
    market_report = (
        f"Technical Summary for {ticker}: 20-day SMA above 50-day SMA (bullish trend). "
        f"RSI at 58.4 indicates healthy upward momentum without overbought conditions."
    )
    print(f"    Signal Output: {market_report}\n")

    sa = AGENT_REGISTRY["Sentiment Analyst"]
    print(f"  • {sa['role']} [Sentiment Analyst]:")
    print(f"    Responsibility: {sa['focus']}")
    sentiment_report = (
        f"Sentiment Index for {ticker}: 78% positive polarity across financial news channels. "
        f"Strong discussion volume surrounding latest hardware and datacenter announcements."
    )
    print(f"    Signal Output: {sentiment_report}\n")

    fa = AGENT_REGISTRY["Fundamentals Analyst"]
    print(f"  • {fa['role']} [Fundamentals Analyst]:")
    print(f"    Responsibility: {fa['focus']}")
    fundamentals_report = (
        f"Fundamental Valuation for {ticker}: Gross margins sustained at 74%. Premium P/E ratio "
        f"is defended by robust forward revenue guidance and enterprise datacenter acceleration."
    )
    print(f"    Signal Output: {fundamentals_report}")

    # 2. Bull vs Bear Researcher Debate
    print("\n[Phase 2] Researcher Debate (Adversarial Thesis Evaluation)")
    
    bull = AGENT_REGISTRY["Bull Researcher"]
    print(f"  • {bull['role']} [Bull Researcher]:")
    print(f"    Responsibility: {bull['focus']}")
    bull_case = (
        f"Uncontested competitive moat in accelerated compute, deep customer lock-in, and multi-quarter "
        f"order backlogs provide strong revenue visibility that justifies premium valuation."
    )
    print(f"    Argument: {bull_case}\n")

    bear = AGENT_REGISTRY["Bear Researcher"]
    print(f"  • {bear['role']} [Bear Researcher]:")
    print(f"    Responsibility: {bear['focus']}")
    bear_case = (
        f"Cyclical customer capex digestion risks and potential supply-chain constraints leave "
        f"scant margin for error at current multiples; risk of sharp re-rating on any miss."
    )
    print(f"    Rebuttal: {bear_case}")

    # 3. Risk Management & Portfolio Manager Assessment
    print("\n[Phase 3] Risk Management Assessment & Position Sizing")
    rm = AGENT_REGISTRY["Risk Manager"]
    print(f"  • {rm['role']} [Risk Manager]:")
    print(f"    Responsibility: {rm['focus']}")
    risk_assessment = (
        "Volatility parameters within target bounds. Max draw-down constraint: 5.0%. "
        "Recommended position size capped at 3.5% portfolio weight with trailing stop."
    )
    print(f"    Constraint Decision: {risk_assessment}")

    # 4. Final Executive Decision
    print("\n[Phase 4] Executive Portfolio Decision")
    pm = AGENT_REGISTRY["Portfolio Manager"]
    print(f"  • {pm['role']} [Portfolio Manager]:")
    print(f"    Responsibility: {pm['focus']}")
    final_decision = {
        "ticker": ticker,
        "date": trade_date,
        "action": "BUY",
        "target_weight": 0.035,
        "confidence": 0.82,
        "rationale": (
            f"Bull thesis confirmed by technical breakout and positive sentiment, with risk-adjusted "
            f"position sizing mitigating bear valuation concerns."
        ),
        "agent_profiles": AGENT_REGISTRY,
    }

    print(f"    Decision Action   : {final_decision['action']}")
    print(f"    Target Allocation : {final_decision['target_weight'] * 100:.1f}%")
    print(f"    Confidence Score  : {final_decision['confidence'] * 100:.0f}%")
    print(f"    Executive Thesis  : {final_decision['rationale']}")
    print("\n" + "=" * 75)
    print("Offline demonstration completed successfully.")
    print("=" * 75)

    return final_decision


def main():
    parser = argparse.ArgumentParser(description="Run TradingAgents offline demo.")
    parser.add_argument("--ticker", default="NVDA", help="Asset ticker symbol (default: NVDA)")
    parser.add_argument("--date", default="2024-05-10", help="Trading date (YYYY-MM-DD, default: 2024-05-10)")
    args = parser.parse_args()

    run_offline_simulation(ticker=args.ticker, trade_date=args.date)


if __name__ == "__main__":
    main()
