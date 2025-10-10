"""Simple test for PDF generation functionality."""
from pathlib import Path
from cli.pdf_generator import generate_pdf_report

# Mock final state for testing
mock_final_state = {
    "market_report": """
    # Market Analysis Report

    The stock showed strong momentum with positive technical indicators.
    RSI is at 65, indicating neither overbought nor oversold conditions.
    MACD shows bullish crossover suggesting upward momentum.
    """,
    "sentiment_report": """
    # Social Sentiment Analysis

    Overall sentiment is positive with 65% bullish mentions on social media.
    Key influencers are discussing positive growth prospects.
    Reddit sentiment shows increased interest in the stock.
    """,
    "news_report": """
    # News Analysis

    Recent earnings beat expectations by 12%.
    New product launch announced, expected to drive revenue growth.
    Analyst upgrades from major firms indicate positive outlook.
    """,
    "fundamentals_report": """
    # Fundamentals Analysis

    P/E ratio of 18 is reasonable for the sector.
    Revenue growth of 25% YoY shows strong business momentum.
    Debt-to-equity ratio is healthy at 0.4.
    """,
    "investment_debate_state": {
        "bull_history": "Strong fundamentals and positive sentiment support upward price action.",
        "bear_history": "Valuation concerns and macro headwinds could limit upside.",
        "judge_decision": "Moderate buy recommendation with position size of 5%."
    },
    "trader_investment_plan": """
    # Trading Plan

    Recommend entering position at current levels.
    Target entry: $150
    Stop loss: $140
    Take profit: $170
    Position size: 5% of portfolio
    """,
    "risk_debate_state": {
        "risky_history": "Market conditions favor aggressive positioning.",
        "safe_history": "Consider reducing exposure given elevated volatility.",
        "neutral_history": "Current position sizing appears appropriate.",
        "judge_decision": "Approve trade with recommended position size."
    },
    "final_trade_decision": "BUY 5% position"
}

# Test PDF generation
try:
    output_path = Path("./test_output")
    output_path.mkdir(exist_ok=True)

    # Use a real ticker and recent date for chart generation
    pdf_path = generate_pdf_report(
        mock_final_state,
        "AAPL",  # Use Apple stock for testing
        "2024-12-01",  # Recent date with available data
        output_path
    )

    print(f"PDF generated successfully: {pdf_path}")
    print(f"File size: {pdf_path.stat().st_size} bytes")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
