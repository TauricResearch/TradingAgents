import questionary
from typing import List, Optional, Tuple, Dict

from rich.console import Console

from cli.models import AnalystType

console = Console()

TICKER_INPUT_EXAMPLES = "Examples: SPY, CNC.TO, 7203.T, 0700.HK"

ANALYST_ORDER = [
    ("Market Analyst", AnalystType.MARKET),
    ("Social Media Analyst", AnalystType.SOCIAL),
    ("News Analyst", AnalystType.NEWS),
    ("Fundamentals Analyst", AnalystType.FUNDAMENTALS),
]


def get_ticker() -> str:
    """Prompt the user to enter a ticker symbol."""
    ticker = questionary.text(
        f"Enter the exact ticker symbol to analyze ({TICKER_INPUT_EXAMPLES}):",
        validate=lambda x: len(x.strip()) > 0 or "Please enter a valid ticker symbol.",
        style=questionary.Style(
            [
                ("text", "fg:green"),
                ("highlighted", "noinherit"),
            ]
        ),
    ).ask()

    if not ticker:
        console.print("\n[red]No ticker symbol provided. Exiting...[/red]")
        exit(1)

    return normalize_ticker_symbol(ticker)


def normalize_ticker_symbol(ticker: str) -> str:
    """Normalize ticker input while preserving exchange suffixes."""
    return ticker.strip().upper()


_CRYPTO_QUOTE_SUFFIXES = (
    "USDT", "USDC", "BUSD", "FDUSD", "TUSD",
    "BTC", "ETH", "BNB",
)


def is_crypto_ticker(ticker: str) -> bool:
    """Return True if the ticker looks like a Binance crypto trading pair.

    Binance pairs are all-uppercase with no dots or exchange suffixes,
    ending in a known quote currency (USDT, BTC, ETH, …).
    """
    t = ticker.upper()
    return "." not in t and any(t.endswith(suffix) for suffix in _CRYPTO_QUOTE_SUFFIXES)


def get_analysis_date() -> str:
    """Prompt the user to enter a date in YYYY-MM-DD format."""
    import re
    from datetime import datetime

    def validate_date(date_str: str) -> bool:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            return False
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    date = questionary.text(
        "Enter the analysis date (YYYY-MM-DD):",
        validate=lambda x: validate_date(x.strip())
        or "Please enter a valid date in YYYY-MM-DD format.",
        style=questionary.Style(
            [
                ("text", "fg:green"),
                ("highlighted", "noinherit"),
            ]
        ),
    ).ask()

    if not date:
        console.print("\n[red]No date provided. Exiting...[/red]")
        exit(1)

    return date.strip()


def select_analysts() -> List[AnalystType]:
    """Select analysts using an interactive checkbox."""
    choices = questionary.checkbox(
        "Select Your [Analysts Team]:",
        choices=[
            questionary.Choice(display, value=value) for display, value in ANALYST_ORDER
        ],
        instruction="\n- Press Space to select/unselect analysts\n- Press 'a' to select/unselect all\n- Press Enter when done",
        validate=lambda x: len(x) > 0 or "You must select at least one analyst.",
        style=questionary.Style(
            [
                ("checkbox-selected", "fg:green"),
                ("selected", "fg:green noinherit"),
                ("highlighted", "noinherit"),
                ("pointer", "noinherit"),
            ]
        ),
    ).ask()

    if not choices:
        console.print("\n[red]No analysts selected. Exiting...[/red]")
        exit(1)

    return choices


def select_research_depth() -> int:
    """Select research depth using an interactive selection."""

    # Define research depth options with their corresponding values
    DEPTH_OPTIONS = [
        ("Shallow - Quick research, few debate and strategy discussion rounds", 1),
        ("Medium - Middle ground, moderate debate rounds and strategy discussion", 3),
        ("Deep - Comprehensive research, in depth debate and strategy discussion", 5),
    ]

    choice = questionary.select(
        "Select Your [Research Depth]:",
        choices=[
            questionary.Choice(display, value=value) for display, value in DEPTH_OPTIONS
        ],
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:yellow noinherit"),
                ("highlighted", "fg:yellow noinherit"),
                ("pointer", "fg:yellow noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print("\n[red]No research depth selected. Exiting...[/red]")
        exit(1)

    return choice


def select_shallow_thinking_agent() -> str:
    """Select shallow thinking llm engine using an interactive selection."""
    SHALLOW_AGENT_OPTIONS = [
        ("Claude Sonnet 4.6 - Best speed and intelligence balance", "claude-sonnet-4-6"),
        ("Claude Haiku 4.5 - Fast, near-instant responses", "claude-haiku-4-5"),
        ("Claude Sonnet 4.5 - Agents and coding", "claude-sonnet-4-5"),
    ]

    choice = questionary.select(
        "Select Your [Quick-Thinking LLM Engine]:",
        choices=[
            questionary.Choice(display, value=value)
            for display, value in SHALLOW_AGENT_OPTIONS
        ],
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:magenta noinherit"),
                ("highlighted", "fg:magenta noinherit"),
                ("pointer", "fg:magenta noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print(
            "\n[red]No shallow thinking llm engine selected. Exiting...[/red]"
        )
        exit(1)

    return choice


def select_deep_thinking_agent() -> str:
    """Select deep thinking llm engine using an interactive selection."""
    DEEP_AGENT_OPTIONS = [
        ("Claude Opus 4.6 - Most intelligent, agents and coding", "claude-opus-4-6"),
        ("Claude Opus 4.5 - Premium, max intelligence", "claude-opus-4-5"),
        ("Claude Sonnet 4.6 - Best speed and intelligence balance", "claude-sonnet-4-6"),
        ("Claude Sonnet 4.5 - Agents and coding", "claude-sonnet-4-5"),
    ]

    choice = questionary.select(
        "Select Your [Deep-Thinking LLM Engine]:",
        choices=[
            questionary.Choice(display, value=value)
            for display, value in DEEP_AGENT_OPTIONS
        ],
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:magenta noinherit"),
                ("highlighted", "fg:magenta noinherit"),
                ("pointer", "fg:magenta noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print("\n[red]No deep thinking llm engine selected. Exiting...[/red]")
        exit(1)

    return choice


def ask_anthropic_effort() -> str | None:
    """Ask for Anthropic effort level.

    Controls token usage and response thoroughness on Claude 4.5+ and 4.6 models.
    """
    return questionary.select(
        "Select Effort Level:",
        choices=[
            questionary.Choice("High (recommended)", "high"),
            questionary.Choice("Medium (balanced)", "medium"),
            questionary.Choice("Low (faster, cheaper)", "low"),
        ],
        style=questionary.Style([
            ("selected", "fg:cyan noinherit"),
            ("highlighted", "fg:cyan noinherit"),
            ("pointer", "fg:cyan noinherit"),
        ]),
    ).ask()


