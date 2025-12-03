import time
from typing import Optional, List

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich import box

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.dataflows.config import get_config
from tradingagents.agents.discovery.models import (
    DiscoveryRequest,
    DiscoveryStatus,
    TrendingStock,
    Sector,
    EventCategory,
)
from tradingagents.agents.discovery.persistence import save_discovery_result

from cli.display import create_question_box
from cli.utils import (
    select_llm_provider,
    select_shallow_thinking_agent,
    loading,
    MultiStageLoader,
)

console = Console()

LOOKBACK_OPTIONS = [
    ("Last hour (1h)", "1h"),
    ("Last 6 hours (6h)", "6h"),
    ("Last 24 hours (24h)", "24h"),
    ("Last 7 days (7d)", "7d"),
]

SECTOR_OPTIONS = [
    ("Technology", Sector.TECHNOLOGY),
    ("Healthcare", Sector.HEALTHCARE),
    ("Finance", Sector.FINANCE),
    ("Energy", Sector.ENERGY),
    ("Consumer Goods", Sector.CONSUMER_GOODS),
    ("Industrials", Sector.INDUSTRIALS),
    ("Other", Sector.OTHER),
]

EVENT_OPTIONS = [
    ("Earnings", EventCategory.EARNINGS),
    ("Merger/Acquisition", EventCategory.MERGER_ACQUISITION),
    ("Regulatory", EventCategory.REGULATORY),
    ("Product Launch", EventCategory.PRODUCT_LAUNCH),
    ("Executive Change", EventCategory.EXECUTIVE_CHANGE),
    ("Other", EventCategory.OTHER),
]


def select_lookback_period() -> str:
    choice = questionary.select(
        "Select lookback period:",
        choices=[
            questionary.Choice(display, value=value) for display, value in LOOKBACK_OPTIONS
        ],
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:cyan noinherit"),
                ("highlighted", "fg:cyan noinherit"),
                ("pointer", "fg:cyan noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print("\n[red]No lookback period selected. Exiting...[/red]")
        exit(1)

    return choice


def select_sector_filter() -> Optional[List[Sector]]:
    use_filter = questionary.confirm(
        "Filter by sector?",
        default=False,
        style=questionary.Style(
            [
                ("selected", "fg:cyan noinherit"),
                ("highlighted", "fg:cyan noinherit"),
            ]
        ),
    ).ask()

    if not use_filter:
        return None

    choices = questionary.checkbox(
        "Select sectors to include:",
        choices=[
            questionary.Choice(display, value=value) for display, value in SECTOR_OPTIONS
        ],
        instruction="\n- Press Space to select/unselect\n- Press 'a' to select all\n- Press Enter when done",
        style=questionary.Style(
            [
                ("checkbox-selected", "fg:cyan"),
                ("selected", "fg:cyan noinherit"),
                ("highlighted", "noinherit"),
                ("pointer", "noinherit"),
            ]
        ),
    ).ask()

    if not choices:
        return None

    return choices


def select_event_filter() -> Optional[List[EventCategory]]:
    use_filter = questionary.confirm(
        "Filter by event type?",
        default=False,
        style=questionary.Style(
            [
                ("selected", "fg:cyan noinherit"),
                ("highlighted", "fg:cyan noinherit"),
            ]
        ),
    ).ask()

    if not use_filter:
        return None

    choices = questionary.checkbox(
        "Select event types to include:",
        choices=[
            questionary.Choice(display, value=value) for display, value in EVENT_OPTIONS
        ],
        instruction="\n- Press Space to select/unselect\n- Press 'a' to select all\n- Press Enter when done",
        style=questionary.Style(
            [
                ("checkbox-selected", "fg:cyan"),
                ("selected", "fg:cyan noinherit"),
                ("highlighted", "noinherit"),
                ("pointer", "noinherit"),
            ]
        ),
    ).ask()

    if not choices:
        return None

    return choices


def create_discovery_results_table(trending_stocks: List[TrendingStock]) -> Table:
    table = Table(
        show_header=True,
        header_style="bold magenta",
        box=box.ROUNDED,
        title="Trending Stocks",
        title_style="bold green",
        expand=True,
    )

    table.add_column("Rank", style="cyan", justify="center", width=6)
    table.add_column("Ticker", style="bold yellow", justify="center", width=10)
    table.add_column("Company", style="white", justify="left", width=25)
    table.add_column("Score", style="green", justify="right", width=10)
    table.add_column("Mentions", style="blue", justify="center", width=10)
    table.add_column("Event Type", style="magenta", justify="center", width=18)

    for rank, stock in enumerate(trending_stocks, 1):
        if rank <= 3:
            rank_display = f"[bold green]{rank}[/bold green]"
            ticker_display = f"[bold yellow]{stock.ticker}[/bold yellow]"
        else:
            rank_display = str(rank)
            ticker_display = stock.ticker

        table.add_row(
            rank_display,
            ticker_display,
            stock.company_name[:25] if len(stock.company_name) > 25 else stock.company_name,
            f"{stock.score:.2f}",
            str(stock.mention_count),
            stock.event_type.value.replace("_", " ").title(),
        )

    return table


def create_stock_detail_panel(stock: TrendingStock, rank: int) -> Panel:
    sentiment_label = "positive" if stock.sentiment > 0.3 else "negative" if stock.sentiment < -0.3 else "neutral"
    sentiment_color = "green" if stock.sentiment > 0.3 else "red" if stock.sentiment < -0.3 else "yellow"

    content = f"""[bold]Rank #{rank}: {stock.ticker} - {stock.company_name}[/bold]

[cyan]Score:[/cyan] {stock.score:.2f}
[cyan]Sentiment:[/cyan] [{sentiment_color}]{stock.sentiment:.2f} ({sentiment_label})[/{sentiment_color}]
[cyan]Sector:[/cyan] {stock.sector.value.replace("_", " ").title()}
[cyan]Event Type:[/cyan] {stock.event_type.value.replace("_", " ").title()}
[cyan]Mentions:[/cyan] {stock.mention_count}

[bold]News Summary:[/bold]
{stock.news_summary}

[bold]Top Source Articles:[/bold]"""

    for i, article in enumerate(stock.source_articles[:3], 1):
        content += f"\n  {i}. [{article.title[:50]}...] - {article.source}"

    return Panel(
        content,
        title=f"Stock Details: {stock.ticker}",
        border_style="cyan",
        padding=(1, 2),
    )


def select_stock_for_detail(trending_stocks: List[TrendingStock]) -> Optional[TrendingStock]:
    if not trending_stocks:
        return None

    choices = [
        questionary.Choice(
            f"{i+1}. {stock.ticker} - {stock.company_name} (Score: {stock.score:.2f})",
            value=stock
        )
        for i, stock in enumerate(trending_stocks)
    ]
    choices.append(questionary.Choice("Back to menu", value=None))

    selected = questionary.select(
        "Select a stock to view details:",
        choices=choices,
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:cyan noinherit"),
                ("highlighted", "fg:cyan noinherit"),
                ("pointer", "fg:cyan noinherit"),
            ]
        ),
    ).ask()

    return selected


def discover_trending_flow(run_analysis_callback=None) -> None:
    console.print(Rule("[bold green]Discover Trending Stocks[/bold green]"))
    console.print()

    console.print(
        create_question_box(
            "Step 1: Lookback Period",
            "Select how far back to search for trending stocks"
        )
    )
    lookback_period = select_lookback_period()
    console.print(f"[green]Selected lookback period:[/green] {lookback_period}")
    console.print()

    console.print(
        create_question_box(
            "Step 2: Sector Filter (Optional)",
            "Optionally filter results by sector"
        )
    )
    sector_filter = select_sector_filter()
    if sector_filter:
        console.print(f"[green]Selected sectors:[/green] {', '.join(s.value for s in sector_filter)}")
    else:
        console.print("[dim]No sector filter applied[/dim]")
    console.print()

    console.print(
        create_question_box(
            "Step 3: Event Filter (Optional)",
            "Optionally filter results by event type"
        )
    )
    event_filter = select_event_filter()
    if event_filter:
        console.print(f"[green]Selected events:[/green] {', '.join(e.value for e in event_filter)}")
    else:
        console.print("[dim]No event filter applied[/dim]")
    console.print()

    console.print(
        create_question_box(
            "Step 4: LLM Provider",
            "Select your LLM provider for entity extraction"
        )
    )
    selected_llm_provider, backend_url = select_llm_provider()
    console.print()

    console.print(
        create_question_box(
            "Step 5: Quick-Thinking Model",
            "Select the model for entity extraction"
        )
    )
    selected_model = select_shallow_thinking_agent(selected_llm_provider)
    console.print()

    config = get_config()
    config["llm_provider"] = selected_llm_provider.lower()
    config["backend_url"] = backend_url
    config["quick_think_llm"] = selected_model
    config["deep_think_llm"] = selected_model

    request = DiscoveryRequest(
        lookback_period=lookback_period,
        sector_filter=sector_filter,
        event_filter=event_filter,
        max_results=config.get("discovery_max_results", 20),
    )

    discovery_stages = [
        "Initializing analysis engine",
        "Fetching news sources",
        "Extracting stock entities",
        "Resolving ticker symbols",
        "Calculating trending scores",
    ]

    result = None

    with MultiStageLoader(discovery_stages, title="Discovery Progress") as loader:
        try:
            loader.next_stage()
            graph = TradingAgentsGraph(config=config, debug=False)

            loader.next_stage()
            result = graph.discover_trending(request)

            loader.next_stage()
            time.sleep(0.3)

            loader.next_stage()
            time.sleep(0.3)

        except (ValueError, KeyError, RuntimeError, ConnectionError, TimeoutError) as e:
            console.print(f"\n[red]Error during discovery: {e}[/red]")
            return

    if result is None:
        console.print("\n[red]Discovery failed. Please try again.[/red]")
        return

    if result.status == DiscoveryStatus.FAILED:
        console.print(f"\n[red]Discovery failed: {result.error_message}[/red]")
        return

    if result.status == DiscoveryStatus.COMPLETED:
        try:
            with loading("Saving discovery results..."):
                save_path = save_discovery_result(result)
            console.print(f"\n[dim]Results saved to: {save_path}[/dim]")
        except (IOError, OSError, ValueError) as e:
            console.print(f"\n[yellow]Warning: Could not save results: {e}[/yellow]")

    console.print()

    if not result.trending_stocks:
        console.print("[yellow]No trending stocks found matching your criteria.[/yellow]")
        return

    console.print(f"[green]Found {len(result.trending_stocks)} trending stocks[/green]")
    console.print()

    results_table = create_discovery_results_table(result.trending_stocks)
    console.print(results_table)
    console.print()

    while True:
        selected_stock = select_stock_for_detail(result.trending_stocks)

        if selected_stock is None:
            break

        rank = result.trending_stocks.index(selected_stock) + 1
        detail_panel = create_stock_detail_panel(selected_stock, rank)
        console.print()
        console.print(detail_panel)
        console.print()

        analyze_choice = questionary.confirm(
            f"Analyze {selected_stock.ticker}?",
            default=False,
            style=questionary.Style(
                [
                    ("selected", "fg:green noinherit"),
                    ("highlighted", "fg:green noinherit"),
                ]
            ),
        ).ask()

        if analyze_choice and run_analysis_callback:
            console.print()
            with loading(f"Preparing analysis for {selected_stock.ticker}...", spinner_style="loading"):
                time.sleep(0.5)
            run_analysis_callback(selected_stock.ticker, config)
            break
