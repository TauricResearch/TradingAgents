"""Test portfolio analysis functionality."""
from pathlib import Path
from tradingagents.portfolio.models import Portfolio, Position
from tradingagents.portfolio.portfolio_graph import PortfolioAnalysisGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Create a sample portfolio
positions = {
    "AAPL": Position(ticker="AAPL", shares=100, avg_cost=150.00),
    "MSFT": Position(ticker="MSFT", shares=50, avg_cost=300.00),
    "GOOGL": Position(ticker="GOOGL", shares=25, avg_cost=120.00),
}

portfolio = Portfolio(
    positions=positions,
    analysis_date="2024-12-01",
    name="Test Portfolio"
)

# Create config
config = DEFAULT_CONFIG.copy()
config["max_debate_rounds"] = 1  # Use minimal rounds for testing
config["max_risk_discuss_rounds"] = 1
config["quick_think_llm"] = "gpt-4o-mini"
config["deep_think_llm"] = "gpt-4o-mini"

# Initialize portfolio graph
print("Initializing portfolio analysis...")
portfolio_graph = PortfolioAnalysisGraph(
    selected_analysts=["market", "fundamentals"],  # Use fewer analysts for faster testing
    debug=True,
    config=config
)

# Run analysis
try:
    print("\nStarting portfolio analysis...")
    result = portfolio_graph.analyze_portfolio(portfolio, max_workers=2)

    print("\n" + "="*60)
    print("PORTFOLIO ANALYSIS COMPLETE")
    print("="*60)

    # Print summary
    print(f"\nPortfolio: {result.portfolio.name}")
    print(f"Total Value: ${result.portfolio.total_market_value:,.2f}")
    print(f"Total P/L: ${result.portfolio.total_unrealized_gain_loss:,.2f} "
          f"({result.portfolio.total_unrealized_gain_loss_pct:+.2f}%)")

    print("\n" + result.portfolio_recommendation)
    print("\n" + result.risk_assessment)

    if result.rebalancing_suggestions:
        print("\nRebalancing Suggestions:")
        for suggestion in result.rebalancing_suggestions:
            print(f"  • [{suggestion['type']}] {suggestion['ticker']}: {suggestion['reason']}")

    # Test PDF generation
    try:
        from cli.portfolio_pdf_generator import generate_portfolio_pdf_report

        output_path = Path("./test_output")
        output_path.mkdir(exist_ok=True)

        print("\nGenerating PDF report...")
        pdf_path = generate_portfolio_pdf_report(result, output_path)
        print(f"PDF generated: {pdf_path}")
        print(f"File size: {pdf_path.stat().st_size} bytes")

    except Exception as e:
        print(f"\nPDF generation error: {e}")

    print("\n✓ Test completed successfully!")

except Exception as e:
    print(f"\nError: {e}")
    import traceback
    traceback.print_exc()
