import typer
from dotenv import load_dotenv

load_dotenv()

import questionary
from rich.align import Align
from rich.console import Console
from rich.panel import Panel

from cli.analysis import run_analysis, run_analysis_for_ticker
from cli.backtest_cmd import run_backtest
from cli.discovery import discover_trending_flow

console = Console()

app = typer.Typer(
    name="TradingAgents",
    help="TradingAgents CLI: Multi-Agents LLM Financial Trading Framework",
    add_completion=True,
)


def show_main_menu():
    with open("./cli/static/welcome.txt") as f:
        welcome_ascii = f.read()

    welcome_content = f"{welcome_ascii}\n"
    welcome_content += "[bold green]TradingAgents: Multi-Agents LLM Financial Trading Framework - CLI[/bold green]\n\n"
    welcome_content += "[bold]Available Options:[/bold]\n"
    welcome_content += "1. Analyze a specific stock\n"
    welcome_content += "2. Discover trending stocks\n\n"
    welcome_content += (
        "[dim]Built by Tauric Research (https://github.com/TauricResearch)[/dim]"
    )

    welcome_box = Panel(
        welcome_content,
        border_style="green",
        padding=(1, 2),
        title="Welcome to TradingAgents",
        subtitle="Multi-Agents LLM Financial Trading Framework",
    )
    console.print(Align.center(welcome_box))
    console.print()

    MENU_OPTIONS = [
        ("1. Analyze a specific stock", "analyze"),
        ("2. Discover trending stocks", "discover"),
    ]

    choice = questionary.select(
        "Select an option:",
        choices=[
            questionary.Choice(display, value=value) for display, value in MENU_OPTIONS
        ],
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:green noinherit"),
                ("highlighted", "fg:green noinherit"),
                ("pointer", "fg:green noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print("\n[red]No option selected. Exiting...[/red]")
        exit(0)

    return choice


@app.command()
def analyze():
    run_analysis()


@app.command()
def discover():
    discover_trending_flow(run_analysis_callback=run_analysis_for_ticker)


@app.command()
def menu():
    choice = show_main_menu()
    if choice == "analyze":
        run_analysis()
    elif choice == "discover":
        discover_trending_flow(run_analysis_callback=run_analysis_for_ticker)


@app.command()
def backtest(
    ticker: str = typer.Option(
        None, "--ticker", "-t", help="Ticker symbol to backtest"
    ),
    start_date: str = typer.Option(
        None, "--start", "-s", help="Start date (YYYY-MM-DD)"
    ),
    end_date: str = typer.Option(None, "--end", "-e", help="End date (YYYY-MM-DD)"),
    initial_cash: float = typer.Option(
        100000.0, "--cash", "-c", help="Initial portfolio cash"
    ),
    strategy: str = typer.Option(
        "sma", "--strategy", help="Strategy: sma, rsi, or hold"
    ),
):
    run_backtest(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
        strategy=strategy,
    )


if __name__ == "__main__":
    app()
