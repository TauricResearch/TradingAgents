import questionary
from typing import List, Optional, Tuple, Dict

from rich.console import Console

from cli.models import AnalystType
from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.llm_clients.model_catalog import get_model_options

console = Console()

TICKER_INPUT_EXAMPLES = "Examples: SPY, CNC.TO, 7203.T, 0700.HK"

ANALYST_ORDER = [
    ("Market Analyst", AnalystType.MARKET),
    ("Social Media Analyst", AnalystType.SOCIAL),
    ("News Analyst", AnalystType.NEWS),
    ("Fundamentals Analyst", AnalystType.FUNDAMENTALS),
]


def _validate_ticker_input(value: str):
    """questionary validator: non-empty AND passes safe_ticker_component."""
    stripped = (value or "").strip()
    if not stripped:
        return "Please enter a valid ticker symbol."
    try:
        safe_ticker_component(stripped.upper())
    except ValueError as e:
        return f"Invalid ticker: {e}"
    return True


def get_ticker() -> str:
    """Prompt the user to enter a ticker symbol.

    Validation runs both the non-empty check and safe_ticker_component so a
    ticker that would later fail deep inside the graph (e.g. one with
    path-traversal characters) is rejected immediately at the input prompt.
    """
    ticker = questionary.text(
        f"Enter the exact ticker symbol to analyze ({TICKER_INPUT_EXAMPLES}):",
        validate=_validate_ticker_input,
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


def _fetch_openrouter_models() -> List[Tuple[str, str]]:
    """Fetch available models from the OpenRouter API."""
    import requests
    try:
        resp = requests.get("https://openrouter.ai/api/v1/models", timeout=10)
        resp.raise_for_status()
        models = resp.json().get("data", [])
        return [(m.get("name") or m["id"], m["id"]) for m in models]
    except Exception as e:
        console.print(f"\n[yellow]Could not fetch OpenRouter models: {e}[/yellow]")
        return []


# Stable, widely-used providers shown first in the curated picker.
# Order matters: this is the rank at which each provider's models appear.
# Anything not in this tuple still shows up, just at the bottom.
_OPENROUTER_PRIORITY_PROVIDERS: Tuple[str, ...] = (
    "deepseek",
    "anthropic",
    "openai",
    "google",
    "x-ai",
    "mistralai",
    "meta-llama",
    "qwen",
)


def _curate_openrouter_models(
    models: List[Tuple[str, str]],
    *,
    per_provider_limit: int = 2,
) -> List[Tuple[str, str]]:
    """Filter and sort OpenRouter models for the interactive picker.

    Drops the :free variants — they share an upstream rate-limit pool and
    routinely 429 mid-analysis (this is what crashed our first run). The
    Custom-ID prompt remains available for users who explicitly want a
    free model and accept the failure mode.

    Sorts so the providers in _OPENROUTER_PRIORITY_PROVIDERS surface first
    in their listed order, capped at ``per_provider_limit`` entries each so
    a single chatty provider (deepseek has 11+ variants) doesn't crowd out
    everyone else.  Models from non-priority providers land at the bottom
    in alphabetical order with no per-provider cap.
    """
    filtered = [(name, mid) for name, mid in models if not mid.endswith(":free")]

    # Group by provider while preserving the API's insertion order, which
    # OpenRouter sorts newest-first. We rely on that order so users see
    # "deepseek-v3.2" before "deepseek-v2", not "v2" first via alphabetic.
    by_provider: dict[str, List[Tuple[str, str]]] = {}
    for entry in filtered:
        prov = entry[1].split("/", 1)[0]
        by_provider.setdefault(prov, []).append(entry)

    out: List[Tuple[str, str]] = []
    seen_ids: set[str] = set()

    # Priority providers, capped per-provider, in declared order.
    # Within each provider, take the first N as returned by the API
    # (newest-first), not alphabetical.
    for prov in _OPENROUTER_PRIORITY_PROVIDERS:
        for entry in by_provider.get(prov, [])[:per_provider_limit]:
            out.append(entry)
            seen_ids.add(entry[1])

    # Non-priority providers only: priority providers' overflow stays
    # hidden so a chatty provider can't crowd the long tail. Users who
    # want a specific older variant can still type it via Custom ID.
    priority_set = set(_OPENROUTER_PRIORITY_PROVIDERS)
    leftovers = [
        e for e in filtered
        if e[1] not in seen_ids and e[1].split("/", 1)[0] not in priority_set
    ]
    out.extend(sorted(leftovers, key=lambda e: e[1]))
    return out


def select_openrouter_model() -> str:
    """Select a curated OpenRouter model, or enter a custom ID.

    Free-tier models (:free suffix) are excluded from the picker because
    they're commonly rate-limited upstream and produce mid-analysis 429s.
    Users who want a specific model — free or otherwise — can still type
    the ID via the "Custom model ID" option.
    """
    models = _fetch_openrouter_models()
    curated = _curate_openrouter_models(models)

    # Show up to 8 from the priority list. Custom-ID always available.
    choices = [questionary.Choice(name, value=mid) for name, mid in curated[:8]]
    choices.append(questionary.Choice("Custom model ID", value="custom"))

    choice = questionary.select(
        "Select OpenRouter Model (stable providers — :free variants excluded):",
        choices=choices,
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style([
            ("selected", "fg:magenta noinherit"),
            ("highlighted", "fg:magenta noinherit"),
            ("pointer", "fg:magenta noinherit"),
        ]),
    ).ask()

    if choice is None or choice == "custom":
        return questionary.text(
            "Enter OpenRouter model ID (e.g. deepseek/deepseek-chat):",
            validate=lambda x: len(x.strip()) > 0 or "Please enter a model ID.",
        ).ask().strip()

    return choice


def _prompt_custom_model_id() -> str:
    """Prompt user to type a custom model ID."""
    return questionary.text(
        "Enter model ID:",
        validate=lambda x: len(x.strip()) > 0 or "Please enter a model ID.",
    ).ask().strip()


def _select_model(provider: str, mode: str) -> str:
    """Select a model for the given provider and mode (quick/deep)."""
    if provider.lower() == "openrouter":
        return select_openrouter_model()

    if provider.lower() == "azure":
        return questionary.text(
            f"Enter Azure deployment name ({mode}-thinking):",
            validate=lambda x: len(x.strip()) > 0 or "Please enter a deployment name.",
        ).ask().strip()

    choice = questionary.select(
        f"Select Your [{mode.title()}-Thinking LLM Engine]:",
        choices=[
            questionary.Choice(display, value=value)
            for display, value in get_model_options(provider, mode)
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
        console.print(f"\n[red]No {mode} thinking llm engine selected. Exiting...[/red]")
        exit(1)

    if choice == "custom":
        return _prompt_custom_model_id()

    return choice


def select_shallow_thinking_agent(provider) -> str:
    """Select shallow thinking llm engine using an interactive selection."""
    return _select_model(provider, "quick")


def select_deep_thinking_agent(provider) -> str:
    """Select deep thinking llm engine using an interactive selection."""
    return _select_model(provider, "deep")

def select_llm_provider() -> tuple[str, str | None]:
    """Select the LLM provider and its API endpoint."""
    # (display_name, provider_key, base_url)
    PROVIDERS = [
        ("OpenAI", "openai", "https://api.openai.com/v1"),
        ("Google", "google", None),
        ("Anthropic", "anthropic", "https://api.anthropic.com/"),
        ("xAI", "xai", "https://api.x.ai/v1"),
        ("DeepSeek", "deepseek", "https://api.deepseek.com"),
        ("Qwen", "qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        ("GLM", "glm", "https://open.bigmodel.cn/api/paas/v4/"),
        ("OpenRouter", "openrouter", "https://openrouter.ai/api/v1"),
        ("Azure OpenAI", "azure", None),
        ("Ollama", "ollama", "http://localhost:11434/v1"),
    ]

    choice = questionary.select(
        "Select your LLM Provider:",
        choices=[
            questionary.Choice(display, value=(provider_key, url))
            for display, provider_key, url in PROVIDERS
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
        console.print("\n[red]No LLM provider selected. Exiting...[/red]")
        exit(1)

    provider, url = choice
    return provider, url


def ask_openai_reasoning_effort() -> str:
    """Ask for OpenAI reasoning effort level."""
    choices = [
        questionary.Choice("Medium (Default)", "medium"),
        questionary.Choice("High (More thorough)", "high"),
        questionary.Choice("Low (Faster)", "low"),
    ]
    return questionary.select(
        "Select Reasoning Effort:",
        choices=choices,
        style=questionary.Style([
            ("selected", "fg:cyan noinherit"),
            ("highlighted", "fg:cyan noinherit"),
            ("pointer", "fg:cyan noinherit"),
        ]),
    ).ask()


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


def ask_gemini_thinking_config() -> str | None:
    """Ask for Gemini thinking configuration.

    Returns thinking_level: "high" or "minimal".
    Client maps to appropriate API param based on model series.
    """
    return questionary.select(
        "Select Thinking Mode:",
        choices=[
            questionary.Choice("Enable Thinking (recommended)", "high"),
            questionary.Choice("Minimal/Disable Thinking", "minimal"),
        ],
        style=questionary.Style([
            ("selected", "fg:green noinherit"),
            ("highlighted", "fg:green noinherit"),
            ("pointer", "fg:green noinherit"),
        ]),
    ).ask()


def ask_output_language() -> str:
    """Ask for report output language.

    The two Chinese variants are listed separately because Chinese-trained
    LLMs (DeepSeek, Qwen, GLM) default to Simplified when given just
    "Chinese", so users wanting Traditional must select it explicitly.
    """
    choice = questionary.select(
        "Select Output Language:",
        choices=[
            questionary.Choice("English (default)", "English"),
            questionary.Choice("Traditional Chinese (繁體中文)", "Traditional Chinese"),
            questionary.Choice("Simplified Chinese (简体中文)", "Simplified Chinese"),
            questionary.Choice("Japanese (日本語)", "Japanese"),
            questionary.Choice("Korean (한국어)", "Korean"),
            questionary.Choice("Hindi (हिन्दी)", "Hindi"),
            questionary.Choice("Spanish (Español)", "Spanish"),
            questionary.Choice("Portuguese (Português)", "Portuguese"),
            questionary.Choice("French (Français)", "French"),
            questionary.Choice("German (Deutsch)", "German"),
            questionary.Choice("Arabic (العربية)", "Arabic"),
            questionary.Choice("Russian (Русский)", "Russian"),
            questionary.Choice("Custom language", "custom"),
        ],
        style=questionary.Style([
            ("selected", "fg:yellow noinherit"),
            ("highlighted", "fg:yellow noinherit"),
            ("pointer", "fg:yellow noinherit"),
        ]),
    ).ask()

    if choice == "custom":
        return questionary.text(
            "Enter language name (e.g. Turkish, Vietnamese, Thai, Indonesian):",
            validate=lambda x: len(x.strip()) > 0 or "Please enter a language name.",
        ).ask().strip()

    return choice


def ask_fundamentals_style() -> str:
    """Ask which analytical lens the Fundamentals analyst should apply.

    Returns a style key (e.g. ``"buffett_value"``) suitable for writing
    into ``config["fundamentals_style"]``. Callers should only invoke
    this when the Fundamentals analyst is actually in the selected set —
    otherwise we add a useless step to the wizard.
    """
    # Imported lazily so importing cli.utils doesn't drag in the full
    # agents package (which depends on langchain).
    from tradingagents.agents.analysts.fundamentals_styles import STYLES

    choices = [
        questionary.Choice(
            title=f"{style.label}\n    {style.description}",
            value=style.key,
        )
        for style in STYLES.values()
    ]

    choice = questionary.select(
        "Select Fundamentals Analysis Style:",
        choices=choices,
        instruction="\n- Each style applies a different investment lens",
        style=questionary.Style([
            ("selected", "fg:cyan noinherit"),
            ("highlighted", "fg:cyan noinherit"),
            ("pointer", "fg:cyan noinherit"),
        ]),
    ).ask()

    if choice is None:
        console.print("\n[red]No style selected. Exiting...[/red]")
        exit(1)

    return choice
