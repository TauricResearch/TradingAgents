"""Portfolio analysis CLI interface."""
import typer
import datetime
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.prompt import Prompt, Confirm

from tradingagents.portfolio.models import Portfolio, Position
from tradingagents.portfolio.portfolio_graph import PortfolioAnalysisGraph
from tradingagents.default_config import DEFAULT_CONFIG
from cli.utils import select_analysts, select_research_depth, select_llm_provider
from cli.utils import select_shallow_thinking_agent, select_deep_thinking_agent

console = Console()


def get_portfolio_input() -> Portfolio:
    """
    Get portfolio holdings from user input.

    Returns:
        Portfolio object with user's positions
    """
    console.print(Panel(
        "[bold]Enter Your Portfolio Holdings[/bold]\n"
        "[dim]You will be prompted to enter each position.\n"
        "Enter ticker symbol, number of shares, and average cost per share.[/dim]",
        border_style="cyan"
    ))

    # Get portfolio name
    portfolio_name = Prompt.ask(
        "\nPortfolio name",
        default="My Portfolio"
    )

    # Get analysis date
    default_date = datetime.datetime.now().strftime("%Y-%m-%d")
    while True:
        analysis_date = Prompt.ask(
            "Analysis date (YYYY-MM-DD)",
            default=default_date
        )
        try:
            datetime.datetime.strptime(analysis_date, "%Y-%m-%d")
            break
        except ValueError:
            console.print("[red]Invalid date format. Please use YYYY-MM-DD[/red]")

    # Collect positions
    positions = {}
    position_num = 1

    console.print("\n[bold cyan]Enter positions (press Ctrl+C or enter empty ticker to finish):[/bold cyan]\n")

    while True:
        try:
            console.print(f"[yellow]Position #{position_num}[/yellow]")

            # Get ticker
            ticker = Prompt.ask("  Ticker symbol").strip().upper()
            if not ticker:
                if len(positions) == 0:
                    console.print("[red]Please enter at least one position[/red]")
                    continue
                break

            # Check if ticker already exists
            if ticker in positions:
                console.print(f"[yellow]  {ticker} already in portfolio. Skipping.[/yellow]")
                continue

            # Get shares
            while True:
                try:
                    shares_str = Prompt.ask("  Number of shares")
                    shares = float(shares_str)
                    if shares <= 0:
                        console.print("[red]  Shares must be positive[/red]")
                        continue
                    break
                except ValueError:
                    console.print("[red]  Invalid number[/red]")

            # Get average cost
            while True:
                try:
                    cost_str = Prompt.ask("  Average cost per share ($)")
                    avg_cost = float(cost_str)
                    if avg_cost <= 0:
                        console.print("[red]  Cost must be positive[/red]")
                        continue
                    break
                except ValueError:
                    console.print("[red]  Invalid number[/red]")

            # Add position
            positions[ticker] = Position(
                ticker=ticker,
                shares=shares,
                avg_cost=avg_cost
            )

            console.print(f"[green]  ✓ Added {ticker}: {shares} shares @ ${avg_cost:.2f}[/green]\n")
            position_num += 1

        except KeyboardInterrupt:
            if len(positions) == 0:
                console.print("\n[red]No positions entered. Exiting.[/red]")
                raise typer.Exit()
            break

    # Create portfolio
    portfolio = Portfolio(
        positions=positions,
        analysis_date=analysis_date,
        name=portfolio_name
    )

    # Display summary
    console.print("\n[bold green]Portfolio Summary:[/bold green]")

    table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
    table.add_column("Ticker", style="cyan", justify="center")
    table.add_column("Shares", justify="right")
    table.add_column("Avg Cost", justify="right")
    table.add_column("Cost Basis", justify="right")

    for ticker, position in portfolio.positions.items():
        table.add_row(
            ticker,
            f"{position.shares:.2f}",
            f"${position.avg_cost:.2f}",
            f"${position.cost_basis:,.2f}"
        )

    table.add_row(
        "[bold]TOTAL[/bold]",
        "",
        "",
        f"[bold]${portfolio.total_cost_basis:,.2f}[/bold]"
    )

    console.print(table)
    console.print()

    # Confirm
    if not Confirm.ask("Proceed with this portfolio?", default=True):
        raise typer.Exit()

    return portfolio


def run_portfolio_analysis():
    """Run the complete portfolio analysis workflow."""

    # Display welcome
    console.print(Panel(
        "[bold green]TradingAgents Portfolio Analyzer[/bold green]\n"
        "[dim]Analyze your entire portfolio with AI-powered multi-agent framework[/dim]",
        border_style="green"
    ))
    console.print()

    # Step 1: Get portfolio holdings
    portfolio = get_portfolio_input()

    # Step 2: Select analysts
    console.print(Panel(
        "[bold]Select Analysts[/bold]\n"
        "[dim]Choose which analyst agents to include in the analysis[/dim]",
        border_style="blue"
    ))
    selected_analysts = select_analysts()

    # Step 3: Select research depth
    console.print(Panel(
        "[bold]Research Depth[/bold]\n"
        "[dim]Higher depth = more thorough analysis but slower[/dim]",
        border_style="blue"
    ))
    research_depth = select_research_depth()

    # Step 4: Select LLM provider
    console.print(Panel(
        "[bold]LLM Provider[/bold]\n"
        "[dim]Select which LLM service to use[/dim]",
        border_style="blue"
    ))
    llm_provider, backend_url = select_llm_provider()

    # Step 5: Select thinking agents
    console.print(Panel(
        "[bold]Thinking Agents[/bold]\n"
        "[dim]Select reasoning models[/dim]",
        border_style="blue"
    ))
    shallow_thinker = select_shallow_thinking_agent(llm_provider)
    deep_thinker = select_deep_thinking_agent(llm_provider)

    # Create config
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = research_depth
    config["max_risk_discuss_rounds"] = research_depth
    config["quick_think_llm"] = shallow_thinker
    config["deep_think_llm"] = deep_thinker
    config["backend_url"] = backend_url
    config["llm_provider"] = llm_provider.lower()

    # Create results directory
    results_dir = Path(config["results_dir"]) / "portfolio" / portfolio.analysis_date
    results_dir.mkdir(parents=True, exist_ok=True)

    # Initialize portfolio graph
    console.print("\n[bold cyan]Initializing portfolio analysis...[/bold cyan]\n")

    portfolio_graph = PortfolioAnalysisGraph(
        selected_analysts=[analyst.value for analyst in selected_analysts],
        debug=True,
        config=config
    )

    # Run analysis
    try:
        result = portfolio_graph.analyze_portfolio(portfolio)

        # Display results
        console.print("\n[bold green]Analysis Complete![/bold green]\n")

        # Save result
        import json
        result_file = results_dir / "portfolio_analysis.json"
        with open(result_file, 'w') as f:
            json.dump(result.to_dict(), f, indent=2, default=str)

        console.print(f"[green]Results saved to: {result_file}[/green]\n")

        # Display portfolio recommendation
        if result.portfolio_recommendation:
            console.print(Panel(
                result.portfolio_recommendation,
                title="Portfolio Overview",
                border_style="green"
            ))

        # Display risk assessment
        if result.risk_assessment:
            console.print(Panel(
                result.risk_assessment,
                title="Risk Assessment",
                border_style="yellow"
            ))

        # Display rebalancing suggestions
        if result.rebalancing_suggestions:
            console.print("\n[bold]Rebalancing Suggestions:[/bold]")
            for suggestion in result.rebalancing_suggestions:
                console.print(f"  • [{suggestion['type']}] {suggestion['ticker']}: {suggestion['reason']}")

        console.print(f"\n[bold cyan]Full analysis results saved to:[/bold cyan] {results_dir}")

        # Generate PDF report
        try:
            from cli.portfolio_pdf_generator import generate_portfolio_pdf_report

            console.print("\n[bold cyan]Generating portfolio PDF report...[/bold cyan]")
            pdf_path = generate_portfolio_pdf_report(result, results_dir)
            console.print(f"[bold green]Portfolio PDF saved to:[/bold green] {pdf_path}")
        except ImportError as e:
            console.print(f"[yellow]Warning: {e}[/yellow]")
            console.print("[yellow]PDF generation skipped. Install required packages:[/yellow]")
            console.print("[dim]pip install reportlab matplotlib seaborn[/dim]")
        except Exception as e:
            console.print(f"[red]Error generating portfolio PDF: {e}[/red]")

        return result

    except Exception as e:
        console.print(f"\n[red]Error during analysis: {e}[/red]")
        import traceback
        traceback.print_exc()
        raise typer.Exit(1)
