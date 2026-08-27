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


def run_offline_simulation(ticker: str = "NVDA", trade_date: str = "2024-05-10") -> Dict[str, Any]:
    """Simulate the multi-agent trading decision pipeline."""
    print("=" * 70)
    print("TradingAgents Offline Demonstration")
    print(f"Ticker: {ticker} | Date: {trade_date} | Mode: OFFLINE (Mocked)")
    print("=" * 70)

    # 1. Market Analyst Phase
    print("\n[Phase 1] Multi-Source Intelligence & Analysis")
    print("  -> Market Analyst: Processing OHLCV & technical indicators (SMA, RSI, MACD)...")
    market_report = (
        f"Technical Summary for {ticker}: 20-day SMA above 50-day SMA (bullish trend). "
        f"RSI at 58.4 indicates healthy upward momentum without being overbought."
    )
    print(f"     [Result]: {market_report}")

    print("  -> Sentiment Analyst: Aggregating social & community sentiment...")
    sentiment_report = (
        f"Social sentiment for {ticker} shows 78% positive mentions across monitored channels. "
        f"Strong discussion volume surrounding latest product lineup announcements."
    )
    print(f"     [Result]: {sentiment_report}")

    print("  -> Fundamentals Analyst: Analyzing financial metrics & valuation...")
    fundamentals_report = (
        f"Gross margins sustained at 74%. P/E ratio is premium relative to historical average, "
        f"supported by robust forward revenue guidance and datacenter growth."
    )
    print(f"     [Result]: {fundamentals_report}")

    # 2. Bull vs Bear Researcher Debate
    print("\n[Phase 2] Researcher Debate")
    print("  -> Bull Researcher:")
    bull_case = (
        f"Strong competitive moat in accelerated compute, high demand visibility into upcoming quarters, "
        f"and robust pricing power outweigh short-term cyclical concerns."
    )
    print(f"     [Argument]: {bull_case}")

    print("  -> Bear Researcher:")
    bear_case = (
        f"Elevated multiple leaves limited safety margin for supply chain disruptions or "
        f"macro headwinds; potential margin compression if customer capex moderates."
    )
    print(f"     [Rebuttal]: {bear_case}")

    # 3. Risk Management & Portfolio Manager Assessment
    print("\n[Phase 3] Risk Management Assessment & Position Sizing")
    risk_assessment = (
        "Volatility parameters within target bounds. Max draw-down constraint: 5.0%. "
        "Recommended position size capped at 3.5% portfolio weight with trailing stop."
    )
    print(f"     [Risk Summary]: {risk_assessment}")

    # 4. Final Executive Decision
    print("\n[Phase 4] Executive Portfolio Decision")
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
    }

    print(f"  -> Decision: {final_decision['action']}")
    print(f"  -> Target Allocation: {final_decision['target_weight'] * 100:.1f}%")
    print(f"  -> Confidence Score: {final_decision['confidence'] * 100:.0f}%")
    print(f"  -> Executive Rationale: {final_decision['rationale']}")
    print("\n" + "=" * 70)
    print("Offline demonstration completed successfully.")
    print("=" * 70)

    return final_decision


def main():
    parser = argparse.ArgumentParser(description="Run TradingAgents offline demo.")
    parser.add_argument("--ticker", default="NVDA", help="Asset ticker symbol (default: NVDA)")
    parser.add_argument("--date", default="2024-05-10", help="Trading date (YYYY-MM-DD, default: 2024-05-10)")
    args = parser.parse_args()

    run_offline_simulation(ticker=args.ticker, trade_date=args.date)


if __name__ == "__main__":
    main()
