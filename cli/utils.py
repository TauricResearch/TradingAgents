import questionary
from typing import List, Optional, Callable, Any
from contextlib import contextmanager
from functools import wraps
import threading
import time

from rich.console import Console
from rich.spinner import Spinner
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.align import Align

from cli.models import AnalystType

console = Console()

SPINNER_STYLES = {
    "default": "dots",
    "fast": "dots2",
    "bounce": "bouncingBall",
    "pulse": "point",
    "arrow": "arrow3",
    "loading": "dots12",
}


class LoadingIndicator:
    def __init__(
        self,
        message: str = "Working...",
        spinner_style: str = "default",
        show_elapsed: bool = False,
        border_style: str = "cyan",
    ):
        self.message = message
        self.spinner_name = SPINNER_STYLES.get(spinner_style, spinner_style)
        self.show_elapsed = show_elapsed
        self.border_style = border_style
        self._live = None
        self._start_time = None
        self._stop_event = threading.Event()
        self._update_thread = None

    def _create_display(self) -> Panel:
        elapsed_text = ""
        if self.show_elapsed and self._start_time:
            elapsed = time.time() - self._start_time
            elapsed_text = f" [{elapsed:.1f}s]"

        spinner = Spinner(self.spinner_name, text=f" {self.message}{elapsed_text}")
        return Panel(
            Align.center(spinner),
            border_style=self.border_style,
            padding=(0, 2),
        )

    def _update_loop(self):
        while not self._stop_event.is_set():
            if self._live and self.show_elapsed:
                self._live.update(self._create_display())
            time.sleep(0.1)

    def start(self):
        self._start_time = time.time()
        self._stop_event.clear()
        self._live = Live(
            self._create_display(),
            console=console,
            refresh_per_second=10,
            transient=True,
        )
        self._live.start()
        if self.show_elapsed:
            self._update_thread = threading.Thread(target=self._update_loop, daemon=True)
            self._update_thread.start()

    def stop(self):
        self._stop_event.set()
        if self._update_thread:
            self._update_thread.join(timeout=0.5)
        if self._live:
            self._live.stop()

    def update_message(self, message: str):
        self.message = message
        if self._live:
            self._live.update(self._create_display())


@contextmanager
def loading(
    message: str = "Working...",
    spinner_style: str = "default",
    show_elapsed: bool = False,
    success_message: Optional[str] = None,
    error_message: Optional[str] = None,
):
    indicator = LoadingIndicator(
        message=message,
        spinner_style=spinner_style,
        show_elapsed=show_elapsed,
    )
    try:
        indicator.start()
        yield indicator
        if success_message:
            console.print(f"[green]{success_message}[/green]")
    except Exception as e:
        if error_message:
            console.print(f"[red]{error_message}: {e}[/red]")
        raise
    finally:
        indicator.stop()


def with_loading(
    message: str = "Working...",
    spinner_style: str = "default",
    show_elapsed: bool = False,
    success_message: Optional[str] = None,
):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            with loading(
                message=message,
                spinner_style=spinner_style,
                show_elapsed=show_elapsed,
                success_message=success_message,
            ):
                return func(*args, **kwargs)
        return wrapper
    return decorator


class MultiStageLoader:
    def __init__(self, stages: List[str], title: str = "Progress"):
        self.stages = stages
        self.title = title
        self.current_stage = 0
        self._live = None
        self._start_time = None

    def _create_display(self) -> Panel:
        lines = []
        for i, stage in enumerate(self.stages):
            if i < self.current_stage:
                lines.append(Text(f"  [done] {stage}", style="green"))
            elif i == self.current_stage:
                spinner = Spinner("dots", text=f" {stage}")
                lines.append(spinner)
            else:
                lines.append(Text(f"  [ -- ] {stage}", style="dim"))

        from rich.console import Group
        content = Group(*lines)

        elapsed = ""
        if self._start_time:
            elapsed = f" [{time.time() - self._start_time:.1f}s]"

        return Panel(
            content,
            title=f"{self.title}{elapsed}",
            border_style="cyan",
            padding=(1, 2),
        )

    def start(self):
        self._start_time = time.time()
        self._live = Live(
            self._create_display(),
            console=console,
            refresh_per_second=10,
        )
        self._live.start()

    def next_stage(self):
        self.current_stage += 1
        if self._live:
            self._live.update(self._create_display())

    def stop(self):
        if self._live:
            self._live.stop()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False

ANALYST_ORDER = [
    ("Market Analyst", AnalystType.MARKET),
    ("Social Media Analyst", AnalystType.SOCIAL),
    ("News Analyst", AnalystType.NEWS),
    ("Fundamentals Analyst", AnalystType.FUNDAMENTALS),
]


def get_ticker() -> str:
    """Prompt the user to enter a ticker symbol."""
    ticker = questionary.text(
        "Enter the ticker symbol to analyze:",
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

    return ticker.strip().upper()


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


def select_shallow_thinking_agent(provider) -> str:
    """Select shallow thinking llm engine using an interactive selection."""

    # Define shallow thinking llm engine options with their corresponding model names
    SHALLOW_AGENT_OPTIONS = {
        "openai": [
            ("GPT-4o-mini - Fast and efficient for quick tasks", "gpt-4o-mini"),
            ("GPT-4.1-nano - Ultra-lightweight model for basic operations", "gpt-4.1-nano"),
            ("GPT-4.1-mini - Compact model with good performance", "gpt-4.1-mini"),
            ("GPT-4o - Standard model with solid capabilities", "gpt-4o"),
        ],
        "anthropic": [
            ("Claude Haiku 3.5 - Fast inference and standard capabilities", "claude-3-5-haiku-latest"),
            ("Claude Sonnet 3.5 - Highly capable standard model", "claude-3-5-sonnet-latest"),
            ("Claude Sonnet 3.7 - Exceptional hybrid reasoning and agentic capabilities", "claude-3-7-sonnet-latest"),
            ("Claude Sonnet 4 - High performance and excellent reasoning", "claude-sonnet-4-0"),
        ],
        "google": [
            ("Gemini 2.0 Flash-Lite - Cost efficiency and low latency", "gemini-2.0-flash-lite"),
            ("Gemini 2.0 Flash - Next generation features, speed, and thinking", "gemini-2.0-flash"),
            ("Gemini 2.5 Flash - Adaptive thinking, cost efficiency", "gemini-2.5-flash-preview-05-20"),
        ],
        "openrouter": [
            ("Meta: Llama 4 Scout", "meta-llama/llama-4-scout:free"),
            ("Meta: Llama 3.3 8B Instruct - A lightweight and ultra-fast variant of Llama 3.3 70B", "meta-llama/llama-3.3-8b-instruct:free"),
            ("google/gemini-2.0-flash-exp:free - Gemini Flash 2.0 offers a significantly faster time to first token", "google/gemini-2.0-flash-exp:free"),
        ],
        "ollama": [
            ("llama3.1 local", "llama3.1"),
            ("llama3.2 local", "llama3.2"),
        ]
    }

    choice = questionary.select(
        "Select Your [Quick-Thinking LLM Engine]:",
        choices=[
            questionary.Choice(display, value=value)
            for display, value in SHALLOW_AGENT_OPTIONS[provider.lower()]
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


def select_deep_thinking_agent(provider) -> str:
    """Select deep thinking llm engine using an interactive selection."""

    # Define deep thinking llm engine options with their corresponding model names
    DEEP_AGENT_OPTIONS = {
        "openai": [
            ("GPT-4.1-nano - Ultra-lightweight model for basic operations", "gpt-4.1-nano"),
            ("GPT-4.1-mini - Compact model with good performance", "gpt-4.1-mini"),
            ("GPT-4o - Standard model with solid capabilities", "gpt-4o"),
            ("o4-mini - Specialized reasoning model (compact)", "o4-mini"),
            ("o3-mini - Advanced reasoning model (lightweight)", "o3-mini"),
            ("o3 - Full advanced reasoning model", "o3"),
            ("o1 - Premier reasoning and problem-solving model", "o1"),
        ],
        "anthropic": [
            ("Claude Haiku 3.5 - Fast inference and standard capabilities", "claude-3-5-haiku-latest"),
            ("Claude Sonnet 3.5 - Highly capable standard model", "claude-3-5-sonnet-latest"),
            ("Claude Sonnet 3.7 - Exceptional hybrid reasoning and agentic capabilities", "claude-3-7-sonnet-latest"),
            ("Claude Sonnet 4 - High performance and excellent reasoning", "claude-sonnet-4-0"),
            ("Claude Opus 4 - Most powerful Anthropic model", "	claude-opus-4-0"),
        ],
        "google": [
            ("Gemini 2.0 Flash-Lite - Cost efficiency and low latency", "gemini-2.0-flash-lite"),
            ("Gemini 2.0 Flash - Next generation features, speed, and thinking", "gemini-2.0-flash"),
            ("Gemini 2.5 Flash - Adaptive thinking, cost efficiency", "gemini-2.5-flash-preview-05-20"),
            ("Gemini 2.5 Pro", "gemini-2.5-pro-preview-06-05"),
        ],
        "openrouter": [
            ("DeepSeek V3 - a 685B-parameter, mixture-of-experts model", "deepseek/deepseek-chat-v3-0324:free"),
            ("Deepseek - latest iteration of the flagship chat model family from the DeepSeek team.", "deepseek/deepseek-chat-v3-0324:free"),
        ],
        "ollama": [
            ("llama3.1 local", "llama3.1"),
            ("qwen3", "qwen3"),
        ]
    }
    
    choice = questionary.select(
        "Select Your [Deep-Thinking LLM Engine]:",
        choices=[
            questionary.Choice(display, value=value)
            for display, value in DEEP_AGENT_OPTIONS[provider.lower()]
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

def select_llm_provider() -> tuple[str, str]:
    """Select the OpenAI api url using interactive selection."""
    # Define OpenAI api options with their corresponding endpoints
    BASE_URLS = [
        ("OpenAI", "https://api.openai.com/v1"),
        ("Anthropic", "https://api.anthropic.com/"),
        ("Google", "https://generativelanguage.googleapis.com/v1"),
        ("Openrouter", "https://openrouter.ai/api/v1"),
        ("Ollama", "http://localhost:11434/v1"),        
    ]
    
    choice = questionary.select(
        "Select your LLM Provider:",
        choices=[
            questionary.Choice(display, value=(display, value))
            for display, value in BASE_URLS
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
        console.print("\n[red]no OpenAI backend selected. Exiting...[/red]")
        exit(1)
    
    display_name, url = choice
    print(f"You selected: {display_name}\tURL: {url}")
    
    return display_name, url
