import questionary
from typing import List, Optional, Tuple, Dict

from rich.console import Console

from cli.models import AnalystType

console = Console()

_MARKET_TICKER_EXAMPLES: dict[str, str] = {
    "stock": "e.g. SPY, AAPL, CNC.TO, 7203.T, 0700.HK",
    "crypto": "e.g. BTCUSDT, ETHUSDT, BNBUSDT",
    "forex": "e.g. EURUSD=X, GBPUSD=X, USDJPY=X",
}

ANALYST_ORDER = [
    ("Market Analyst", AnalystType.MARKET),
    ("Social Media Analyst", AnalystType.SOCIAL),
    ("News Analyst", AnalystType.NEWS),
    ("Fundamentals Analyst", AnalystType.FUNDAMENTALS),
]


def select_market_type() -> str:
    """Prompt the user to select a market type (stock, crypto, forex)."""
    MARKET_OPTIONS = [
        ("Stock — Equities & ETFs (e.g. SPY, AAPL, CNC.TO)", "stock"),
        ("Crypto — Binance pairs (e.g. BTCUSDT, ETHUSDT)", "crypto"),
        ("Forex — Currency pairs (e.g. EURUSD=X, GBPUSD=X)", "forex"),
    ]

    choice = questionary.select(
        "Select Market Type:",
        choices=[
            questionary.Choice(display, value=value) for display, value in MARKET_OPTIONS
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
        console.print("\n[red]No market type selected. Exiting...[/red]")
        exit(1)

    return choice


def get_ticker(market_type: str = "stock") -> str:
    """Prompt the user to enter a ticker symbol."""
    examples = _MARKET_TICKER_EXAMPLES.get(market_type, _MARKET_TICKER_EXAMPLES["stock"])
    ticker = questionary.text(
        f"Enter the exact identifier to analyze ({examples}):",
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


def ask_kline_config() -> dict:
    """Ask the user for Binance kline interval, start date, and end date.

    Defaults:
      - interval: 1d (daily)
      - start_date: 2 months before today  (DD/MM/YYYY)
      - end_date:   today                  (DD/MM/YYYY)
    """
    import re
    from datetime import datetime, timedelta

    DATE_FMT = "%d/%m/%Y"

    today = datetime.now()
    default_end = today.strftime(DATE_FMT)
    default_start = (today - timedelta(days=60)).strftime(DATE_FMT)

    # ── Interval ────────────────────────────────────────────────────────────
    INTERVAL_OPTIONS = [
        ("1 Day  (1d) — default, suitable for swing trading", "1d"),
        ("1 Hour (1h) — intraday view", "1h"),
        ("4 Hour (4h) — mid-session view", "4h"),
        ("15 Min (15m)", "15m"),
        ("5 Min  (5m)", "5m"),
        ("1 Min  (1m) — high-frequency", "1m"),
        ("1 Week (1w) — long-term trend", "1w"),
        ("1 Month(1M) — macro trend", "1M"),
    ]

    interval = questionary.select(
        "Select Kline Interval:",
        choices=[
            questionary.Choice(display, value=value)
            for display, value in INTERVAL_OPTIONS
        ],
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style([
            ("selected", "fg:yellow noinherit"),
            ("highlighted", "fg:yellow noinherit"),
            ("pointer", "fg:yellow noinherit"),
        ]),
    ).ask()

    if interval is None:
        console.print("\n[red]No kline interval selected. Exiting...[/red]")
        exit(1)

    # ── Date validation helper ───────────────────────────────────────────────
    def _valid_date(s: str) -> bool:
        try:
            datetime.strptime(s, DATE_FMT)
            return True
        except ValueError:
            return False

    # ── Start date ──────────────────────────────────────────────────────────
    start_date = questionary.text(
        f"Kline start date (DD/MM/YYYY) [default: {default_start}]:",
        default=default_start,
        validate=lambda s: _valid_date(s) or "Please enter a valid date in DD/MM/YYYY format.",
        style=questionary.Style([("text", "fg:green")]),
    ).ask()

    if start_date is None:
        console.print("\n[red]No start date provided. Exiting...[/red]")
        exit(1)

    # ── End date ────────────────────────────────────────────────────────────
    end_date = questionary.text(
        f"Kline end date   (DD/MM/YYYY) [default: {default_end}]:",
        default=default_end,
        validate=lambda s: _valid_date(s) or "Please enter a valid date in DD/MM/YYYY format.",
        style=questionary.Style([("text", "fg:green")]),
    ).ask()

    if end_date is None:
        console.print("\n[red]No end date provided. Exiting...[/red]")
        exit(1)

    # ── Convert DD/MM/YYYY → YYYY-MM-DD for internal use ────────────────────
    start_iso = datetime.strptime(start_date, DATE_FMT).strftime("%Y-%m-%d")
    end_iso = datetime.strptime(end_date, DATE_FMT).strftime("%Y-%m-%d")

    return {
        "kline_interval": interval,
        "kline_start_date": start_iso,
        "kline_end_date": end_iso,
    }


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


