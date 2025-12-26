"""
Example: Using Output Validators for Agent Quality Checks

This example demonstrates how to use the output validation utilities
to check agent output quality and extract trading signals.
"""

from spektiv.utils.output_validator import (
    validate_report_completeness,
    validate_decision_quality,
    validate_debate_state,
    validate_agent_state,
)


def example_validate_report():
    """Example: Validate a market report."""
    print("=" * 60)
    print("Example 1: Validate Report Completeness")
    print("=" * 60)

    report = """
    # Market Analysis for AAPL

    ## Technical Indicators
    Strong bullish momentum with RSI at 55 and MACD showing positive divergence.

    ## Volume Analysis
    Above-average volume on recent upward moves indicates strong buyer interest.
    """ + "Additional detailed analysis. " * 40

    result = validate_report_completeness(
        report,
        min_length=500,
        require_markdown_tables=False,
        require_sections=True
    )

    print(f"Valid: {result.is_valid}")
    print(f"Length: {result.metrics['length']} chars")
    print(f"Section Headers: {result.metrics['section_headers']}")
    print(f"Errors: {result.errors}")
    print(f"Warnings: {result.warnings}")
    print()


def example_extract_signal():
    """Example: Extract trading signal from decision."""
    print("=" * 60)
    print("Example 2: Extract Trading Signal")
    print("=" * 60)

    decisions = [
        "BUY: Strong fundamentals and positive momentum",
        "SELL: Overvalued with deteriorating metrics",
        "HOLD: Mixed signals, awaiting clarity",
        "buy the stock now",  # Case-insensitive
    ]

    for decision in decisions:
        result = validate_decision_quality(decision)
        signal = result.metrics.get("signal", "UNKNOWN")
        has_reasoning = result.metrics.get("has_reasoning", False)

        print(f"Decision: {decision[:40]:<40} -> Signal: {signal:4} | Reasoning: {has_reasoning}")
    print()


def example_validate_debate():
    """Example: Validate debate state."""
    print("=" * 60)
    print("Example 3: Validate Debate State")
    print("=" * 60)

    debate_state = {
        "history": "Round 1: Bull presents case...\nRound 2: Bear counters...\nRound 3: Judge decides...",
        "count": 3,
        "judge_decision": "BUY: Bulls made compelling case",
        "bull_history": "Strong fundamentals",
        "bear_history": "Some valuation concerns",
    }

    result = validate_debate_state(debate_state, debate_type="invest")

    print(f"Valid: {result.is_valid}")
    print(f"Debate Rounds: {result.metrics.get('count', 0)}")
    print(f"Judge Signal: {result.metrics.get('judge_signal', 'N/A')}")
    print(f"History Length: {result.metrics.get('history_length', 0)} chars")
    print(f"Errors: {result.errors}")
    print(f"Warnings: {result.warnings}")
    print()


def example_validate_complete_state():
    """Example: Validate complete agent state."""
    print("=" * 60)
    print("Example 4: Validate Complete Agent State")
    print("=" * 60)

    # Minimal state (will have warnings)
    state = {
        "company_of_interest": "AAPL",
        "trade_date": "2024-01-15",
        "market_report": "Market analysis. " * 100,
        "final_trade_decision": "BUY: Strong fundamentals and positive momentum",
    }

    result = validate_agent_state(state)

    print(f"Valid: {result.is_valid}")
    print(f"Company: {result.metrics.get('company_of_interest', 'N/A')}")
    print(f"Reports Present: {result.metrics.get('reports_present', 0)}/4")
    print(f"Final Signal: {result.metrics.get('final_signal', 'N/A')}")
    print(f"Errors: {result.errors}")
    print(f"Warnings: {result.warnings}")
    print()


def example_quality_check_workflow():
    """Example: Complete quality check workflow."""
    print("=" * 60)
    print("Example 5: Complete Quality Check Workflow")
    print("=" * 60)

    # Simulate agent output
    state = {
        "company_of_interest": "TSLA",
        "trade_date": "2024-01-20",
        "market_report": "# Market Report\n\n" + "Detailed analysis. " * 100,
        "sentiment_report": "# Sentiment\n\n" + "Social sentiment. " * 100,
        "news_report": "# News\n\n" + "Latest news. " * 100,
        "fundamentals_report": "# Fundamentals\n\n" + "Financial data. " * 100,
        "investment_debate_state": {
            "history": "Debate history...",
            "count": 2,
            "judge_decision": "SELL: Bears made stronger case",
        },
        "risk_debate_state": {
            "history": "Risk assessment...",
            "count": 1,
            "judge_decision": "SELL: Exit to preserve capital",
        },
        "final_trade_decision": "SELL: Consensus to exit position",
    }

    # Validate complete state
    result = validate_agent_state(state)

    print(f"Overall Quality Check: {'PASS' if result.is_valid else 'FAIL'}")
    print()

    # Extract key metrics
    print("Key Metrics:")
    print(f"  Company: {result.metrics.get('company_of_interest')}")
    print(f"  Trade Date: {result.metrics.get('trade_date')}")
    print(f"  Reports: {result.metrics.get('reports_present')}/4 present")
    print(f"  Investment Debate: {'Valid' if result.metrics.get('investment_debate_valid') else 'Invalid'}")
    print(f"  Risk Debate: {'Valid' if result.metrics.get('risk_debate_valid') else 'Invalid'}")
    print(f"  Final Signal: {result.metrics.get('final_signal')}")
    print()

    # Show issues
    if result.errors:
        print("Errors (must fix):")
        for error in result.errors:
            print(f"  - {error}")
        print()

    if result.warnings:
        print("Warnings (should review):")
        for warning in result.warnings:
            print(f"  - {warning}")
        print()

    # Decision logic
    if result.is_valid:
        signal = result.metrics.get('final_signal')
        if signal:
            print(f"Recommendation: Proceed with {signal} decision")
        else:
            print("Recommendation: Review - no clear signal extracted")
    else:
        print("Recommendation: Fix errors before proceeding")
    print()


if __name__ == "__main__":
    # Run all examples
    example_validate_report()
    example_extract_signal()
    example_validate_debate()
    example_validate_complete_state()
    example_quality_check_workflow()

    print("=" * 60)
    print("All examples completed!")
    print("=" * 60)
