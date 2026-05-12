import os
from pathlib import Path
from typing import List, Optional, Tuple, Dict

import questionary
from dotenv import find_dotenv, set_key
from rich.console import Console

from cli.models import AnalystType
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.model_catalog import get_model_options

console = Console()

TICKER_INPUT_EXAMPLES = "Examples: SPY, CNC.TO, 7203.T, 0700.HK"

ANALYST_ORDER = [
    ("Market Analyst", AnalystType.MARKET),
    ("Sentiment Analyst", AnalystType.SOCIAL),
    ("News Analyst", AnalystType.NEWS),
    ("Fundamentals Analyst", AnalystType.FUNDAMENTALS),
    ("Macro Analyst", AnalystType.MACRO),
    ("Options Analyst", AnalystType.OPTIONS),
    ("Quantitative Analyst", AnalystType.QUANT),
    ("Earnings Analyst", AnalystType.EARNINGS),
    ("Review Analyst", AnalystType.REVIEW),
]


def get_ticker() -> List[str]:
    """Prompt the user to enter ticker symbol(s)."""
    prefs = load_prefs()
    default_ticker = prefs.get("last_ticker", "SPY")

    ticker_input = questionary.text(
        f"Enter the exact ticker symbol(s) to analyze, separated by commas ({TICKER_INPUT_EXAMPLES}) [Default: {default_ticker}]:",
        default=default_ticker,
        validate=lambda x: len(x.strip()) > 0 or "Please enter a valid ticker symbol.",
        style=questionary.Style(
            [
                ("text", "fg:green"),
                ("highlighted", "noinherit"),
            ]
        ),
    ).ask()

    if not ticker_input:
        console.print("\n[red]No ticker symbol provided. Exiting...[/red]")
        exit(1)

    # Save to prefs
    prefs["last_ticker"] = ticker_input.strip()
    save_prefs(prefs)

    # Split by comma and normalize
    tickers = [normalize_ticker_symbol(t) for t in ticker_input.split(",") if t.strip()]
    return tickers

def normalize_ticker_symbol(ticker: str) -> str:
    """Normalize ticker input while preserving exchange suffixes."""
    return ticker.strip().upper()


def get_analysis_date() -> str:
    """Prompt the user to enter a date in YYYY-MM-DD format. Defaults to today."""
    import re
    from datetime import datetime

    today_str = datetime.now().strftime("%Y-%m-%d")

    def validate_date(date_str: str) -> bool:
        if not date_str.strip():
            return True # Allow empty, will default to today
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            return False
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    date = questionary.text(
        "Enter the analysis date (YYYY-MM-DD) [Press Enter for today]:",
        default=today_str,
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

    date = date.strip()
    return date if date else today_str


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


def select_openrouter_model(default_choice: str = None) -> str:
    """Select an OpenRouter model from the newest available, or enter a custom ID."""
    models = _fetch_openrouter_models()

    choices = [questionary.Choice(name, value=mid) for name, mid in models[:5]]
    choices.append(questionary.Choice("Custom model ID", value="custom"))

    default_index = 0
    if default_choice:
        for idx, choice_obj in enumerate(choices[:-1]):
            if choice_obj.value == default_choice:
                default_index = idx
                break
        else:
            if default_choice != "custom":
                default_index = len(choices) - 1

    choice = questionary.select(
        "Select OpenRouter Model (latest available):",
        choices=choices,
        default=choices[default_index] if choices else None,
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style([
            ("selected", "fg:magenta noinherit"),
            ("highlighted", "fg:magenta noinherit"),
            ("pointer", "fg:magenta noinherit"),
        ]),
    ).ask()

    if choice is None or choice == "custom":
        custom_default = default_choice if default_choice and default_choice != "custom" else ""
        return questionary.text(
            "Enter OpenRouter model ID (e.g. google/gemma-4-26b-a4b-it):",
            default=custom_default,
            validate=lambda x: len(x.strip()) > 0 or "Please enter a model ID.",
        ).ask().strip()

    return choice


def _prompt_custom_model_id(default_id: str = "") -> str:
    """Prompt user to type a custom model ID."""
    return questionary.text(
        "Enter model ID:",
        default=default_id,
        validate=lambda x: len(x.strip()) > 0 or "Please enter a model ID.",
    ).ask().strip()


from cli.user_prefs import load_prefs, save_prefs

def _select_model(provider: str, mode: str) -> str:
    """Select a model for the given provider and mode (quick/deep)."""
    prefs = load_prefs()
    pref_key = f"{provider}_{mode}_model"
    default_choice = prefs.get(pref_key)

    if provider.lower() == "openrouter":
        return select_openrouter_model(default_choice)

    if provider.lower() == "azure":
        return questionary.text(
            f"Enter Azure deployment name ({mode}-thinking):",
            validate=lambda x: len(x.strip()) > 0 or "Please enter a deployment name.",
        ).ask().strip()

    # Find the default index if we have a saved preference
    default_index = 0
    model_options = get_model_options(provider, mode)
    if default_choice:
        for idx, (_, val) in enumerate(model_options):
            if val == default_choice:
                default_index = idx
                break
        else:
            # If default_choice is custom but not in standard options, we should select 'Custom model ID'
            if default_choice != "custom": # To avoid selecting custom if the saved was actually 'custom' literally (rare but possible)
                for idx, (_, val) in enumerate(model_options):
                    if val == "custom":
                        default_index = idx
                        break

    choices = [
        questionary.Choice(display, value=value)
        for display, value in model_options
    ]

    choice = questionary.select(
        f"Select Your [{mode.title()}-Thinking LLM Engine]:",
        choices=choices,
        default=choices[default_index] if choices else None,
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
        custom_default = default_choice if default_choice and default_choice != "custom" else ""
        final_choice = _prompt_custom_model_id(custom_default)
    else:
        final_choice = choice
        
    prefs[pref_key] = final_choice
    save_prefs(prefs)
    return final_choice


def select_shallow_thinking_agent(provider) -> str:
    """Select shallow thinking llm engine using an interactive selection."""
    return _select_model(provider, "quick")


def select_deep_thinking_agent(provider) -> str:
    """Select deep thinking llm engine using an interactive selection."""
    return _select_model(provider, "deep")

def select_llm_provider() -> tuple[str, str | None]:
    """Select the LLM provider and its API endpoint."""
    # Ollama users can point at a remote ollama-serve via OLLAMA_BASE_URL
    # (convention from the broader Ollama ecosystem); falls back to the
    # localhost default when unset.
    ollama_url = os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434/v1"
    # (display_name, provider_key, base_url)
    PROVIDERS = [
        ("OpenAI", "openai", "https://api.openai.com/v1"),
        ("Google", "google", None),
        ("Anthropic", "anthropic", "https://api.anthropic.com/"),
        ("xAI", "xai", "https://api.x.ai/v1"),
        ("DeepSeek", "deepseek", "https://api.deepseek.com"),
        ("Qwen", "qwen", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
        ("GLM", "glm", "https://open.bigmodel.cn/api/paas/v4/"),
        ("MiniMax", "minimax", "https://api.minimax.io/v1"),
        ("OpenRouter", "openrouter", "https://openrouter.ai/api/v1"),
        ("Azure OpenAI", "azure", None),
        ("Ollama", "ollama", ollama_url),
        ("NVIDIA NIM", "nvidia", "https://integrate.api.nvidia.com/v1"),
        ("LiteLLM", "litellm", "http://localhost:4000/v1"),
    ]

    prefs = load_prefs()
    default_provider = prefs.get("default_provider", "openai")
    
    default_index = 0
    for idx, (_, p_key, _) in enumerate(PROVIDERS):
        if p_key == default_provider:
            default_index = idx
            break

    choices = [
        questionary.Choice(display, value=(provider_key, url))
        for display, provider_key, url in PROVIDERS
    ]

    choice = questionary.select(
        "Select your LLM Provider:",
        choices=choices,
        default=choices[default_index] if choices else None,
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
    prefs["default_provider"] = provider
    save_prefs(prefs)
    
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

    Controls token usage and response thoroughness on Claude 4.5 / 4.6 / 4.7
    models. The API also accepts "max"; we expose low/medium/high as the
    common selection range.
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


def ask_glm_region() -> tuple[str, str]:
    """Ask which GLM platform (Z.AI international vs BigModel China) to use.

    Zhipu serves the same GLM models under two brands with separate
    accounts; keys aren't interchangeable. Returns (provider_key, backend_url).
    """
    return questionary.select(
        "Select GLM platform:",
        choices=[
            questionary.Choice(
                "Z.AI — api.z.ai (international, uses ZHIPU_API_KEY)",
                value=("glm", "https://api.z.ai/api/paas/v4/"),
            ),
            questionary.Choice(
                "BigModel — open.bigmodel.cn (China, uses ZHIPU_CN_API_KEY)",
                value=("glm-cn", "https://open.bigmodel.cn/api/paas/v4/"),
            ),
        ],
        style=questionary.Style([
            ("selected", "fg:cyan noinherit"),
            ("highlighted", "fg:cyan noinherit"),
            ("pointer", "fg:cyan noinherit"),
        ]),
    ).ask()


def ask_qwen_region() -> tuple[str, str]:
    """Ask which Qwen region (international vs China) to use.

    Alibaba DashScope exposes two endpoints with separate accounts —
    a key from one region does NOT authenticate against the other
    (fixes #758). Returns (provider_key, backend_url).
    """
    return questionary.select(
        "Select Qwen region:",
        choices=[
            questionary.Choice(
                "International — dashscope-intl.aliyuncs.com (uses DASHSCOPE_API_KEY)",
                value=("qwen", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
            ),
            questionary.Choice(
                "China — dashscope.aliyuncs.com (uses DASHSCOPE_CN_API_KEY)",
                value=("qwen-cn", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            ),
        ],
        style=questionary.Style([
            ("selected", "fg:cyan noinherit"),
            ("highlighted", "fg:cyan noinherit"),
            ("pointer", "fg:cyan noinherit"),
        ]),
    ).ask()


def ask_minimax_region() -> tuple[str, str]:
    """Ask which MiniMax region (global vs China) to use.

    MiniMax exposes two endpoints with separate accounts — a key from
    one region does NOT authenticate against the other. Returns
    (provider_key, backend_url).
    """
    return questionary.select(
        "Select MiniMax region:",
        choices=[
            questionary.Choice(
                "Global — api.minimax.io (uses MINIMAX_API_KEY)",
                value=("minimax", "https://api.minimax.io/v1"),
            ),
            questionary.Choice(
                "China — api.minimaxi.com (uses MINIMAX_CN_API_KEY)",
                value=("minimax-cn", "https://api.minimaxi.com/v1"),
            ),
        ],
        style=questionary.Style([
            ("selected", "fg:cyan noinherit"),
            ("highlighted", "fg:cyan noinherit"),
            ("pointer", "fg:cyan noinherit"),
        ]),
    ).ask()


def confirm_ollama_endpoint(url: str) -> None:
    """Show the resolved Ollama endpoint after provider selection.

    Surfaces three things the user benefits from seeing before model
    selection: which URL we'll actually hit, where it came from
    (\`OLLAMA_BASE_URL\` vs default), and a soft warning if the URL is
    missing the scheme/port that ollama-serve expects. The warning is
    advisory only — we don't reject malformed input, since the user may
    be doing something deliberately unusual (e.g. a reverse-proxy path).
    """
    from_env = os.environ.get("OLLAMA_BASE_URL")
    origin = " (from OLLAMA_BASE_URL)" if from_env and from_env == url else ""
    console.print(f"[green]✓ Using Ollama at {url}{origin}[/green]")

    if not url.startswith(("http://", "https://")):
        console.print(
            f"[yellow]Note: {url!r} is missing a scheme. "
            f"Ollama-serve typically expects a URL like "
            f"http://<host>:11434/v1.[/yellow]"
        )
    elif ":11434" not in url and "://localhost" not in url and "://127.0.0.1" not in url:
        # Soft hint when the port differs from the ollama-serve default
        # and the host isn't local (where users sometimes proxy on :80).
        console.print(
            f"[yellow]Note: {url!r} doesn't include port 11434. "
            f"Make sure your remote ollama-serve listens on the port "
            f"shown above.[/yellow]"
        )


def ensure_api_key(provider: str) -> Optional[str]:
    """Make sure the API key for `provider` is available in the environment.

    If the env var is already set, returns its value untouched. Otherwise
    interactively prompts the user, persists the value to the project's
    .env file via python-dotenv's set_key (creating .env if needed), and
    exports it into os.environ so the current process picks it up.

    Returns None for providers that do not require a key (e.g. ollama)
    and for providers not found in the canonical mapping.
    """
    env_var = get_api_key_env(provider)
    if env_var is None:
        return None  # ollama / unknown — no key check possible

    existing = os.environ.get(env_var)
    if existing:
        return existing

    console.print(
        f"\n[yellow]{env_var} is not set in your environment.[/yellow]"
    )
    key = questionary.password(
        f"Paste your {env_var} (will be saved to .env):",
        style=questionary.Style([
            ("text", "fg:cyan"),
            ("highlighted", "noinherit"),
        ]),
    ).ask()
    if not key:
        console.print(
            f"[red]Skipped. API calls will fail until {env_var} is set.[/red]"
        )
        return None

    env_path = find_dotenv(usecwd=True) or str(Path.cwd() / ".env")
    Path(env_path).touch(exist_ok=True)
    set_key(env_path, env_var, key)
    os.environ[env_var] = key
    console.print(f"[green]Saved {env_var} to {env_path}[/green]")
    return key


def ask_output_language() -> str:
    """Ask for report output language."""
    choice = questionary.select(
        "Select Output Language:",
        choices=[
            questionary.Choice("English (default)", "English"),
            questionary.Choice("Chinese (中文)", "Chinese"),
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
