import os
import socket
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import questionary
from rich.console import Console
from rich.panel import Panel

from cli.models import AnalystType
from tradingagents.llm_clients.model_catalog import get_model_options

console = Console()

TICKER_INPUT_EXAMPLES = "Examples: SPY, CNC.TO, 7203.T, 0700.HK"

ANALYST_ORDER = [
    ("Market Analyst", AnalystType.MARKET),
    ("Social Media Analyst", AnalystType.SOCIAL),
    ("News Analyst", AnalystType.NEWS),
    ("Fundamentals Analyst", AnalystType.FUNDAMENTALS),
]

# Default OpenAI-compatible base URLs (mirrors openai_client._PROVIDER_CONFIG).
# Used when ``--backend-url`` is omitted in non-interactive mode. Anthropic /
# Google / Azure use their own clients; we still expose wizard defaults here
# for consistency when those providers are wired through the same config key.
DEFAULT_BACKEND_URL_BY_PROVIDER: Dict[str, Optional[str]] = {
    "openai": "https://api.openai.com/v1",
    "xai": "https://api.x.ai/v1",
    "deepseek": "https://api.deepseek.com",
    "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "glm": "https://api.z.ai/api/paas/v4/",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
    "mlx": "http://localhost:8000/v1",
    "anthropic": "https://api.anthropic.com/",
    "google": None,
    "azure": None,
}


def default_backend_url_for_provider(provider: str) -> Optional[str]:
    """Return the default API base URL for a provider, or None if not applicable."""
    return DEFAULT_BACKEND_URL_BY_PROVIDER.get(provider.lower())


def parse_research_depth_flag(value: str) -> int:
    """Parse --depth shallow|medium|deep or 1|3|5."""
    v = value.strip().lower()
    mapping = {
        "shallow": 1,
        "medium": 3,
        "deep": 5,
        "1": 1,
        "3": 3,
        "5": 5,
    }
    if v not in mapping:
        raise ValueError(f"Invalid research depth {value!r}; use shallow, medium, deep, or 1, 3, 5.")
    return mapping[v]


def parse_analysts_flag(value: str) -> List[AnalystType]:
    """Parse comma-separated analyst keys (market,social,news,fundamentals)."""
    allowed = {a.value for a in AnalystType}
    parts = [p.strip().lower() for p in value.split(",") if p.strip()]
    if not parts:
        raise ValueError("At least one analyst is required.")
    out: List[AnalystType] = []
    for p in parts:
        if p not in allowed:
            raise ValueError(f"Unknown analyst {p!r}; allowed: {', '.join(sorted(allowed))}")
        out.append(AnalystType(p))
    return out


def validate_analysis_date_cli(date_str: str) -> str:
    """Validate YYYY-MM-DD and reject future dates."""
    import re
    from datetime import datetime

    s = date_str.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        raise ValueError("Date must be YYYY-MM-DD.")
    try:
        d = datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError as e:
        raise ValueError("Invalid calendar date.") from e
    if d > datetime.now().date():
        raise ValueError("Analysis date cannot be in the future.")
    return s


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
        validate=lambda x: validate_date(x.strip()) or "Please enter a valid date in YYYY-MM-DD format.",
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
        choices=[questionary.Choice(display, value=value) for display, value in ANALYST_ORDER],
        instruction=(
            "\n- Press Space to select/unselect analysts\n- Press 'a' to select/unselect all\n- Press Enter when done"
        ),
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
        choices=[questionary.Choice(display, value=value) for display, value in DEPTH_OPTIONS],
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


def select_openrouter_model() -> str:
    """Select an OpenRouter model from the newest available, or enter a custom ID."""
    models = _fetch_openrouter_models()

    choices = [questionary.Choice(name, value=mid) for name, mid in models[:5]]
    choices.append(questionary.Choice("Custom model ID", value="custom"))

    choice = questionary.select(
        "Select OpenRouter Model (latest available):",
        choices=choices,
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:magenta noinherit"),
                ("highlighted", "fg:magenta noinherit"),
                ("pointer", "fg:magenta noinherit"),
            ]
        ),
    ).ask()

    if choice is None or choice == "custom":
        return (
            questionary.text(
                "Enter OpenRouter model ID (e.g. google/gemma-4-26b-a4b-it):",
                validate=lambda x: len(x.strip()) > 0 or "Please enter a model ID.",
            )
            .ask()
            .strip()
        )

    return choice


def _prompt_custom_model_id() -> str:
    """Prompt user to type a custom model ID."""
    return (
        questionary.text(
            "Enter model ID:",
            validate=lambda x: len(x.strip()) > 0 or "Please enter a model ID.",
        )
        .ask()
        .strip()
    )


# Hugging Face orgs known to publish MLX-converted weights, plus repo-name
# substrings that are usually MLX-flavored. Used to filter the local HF cache
# so the autocomplete prompt only suggests things that actually run on
# `mlx_lm.server`.
_MLX_HF_ORGS = {"mlx-community", "lmstudio-community", "apple"}
_MLX_REPO_HINTS = ("MLX", "mlx", "OptiQ", "-4bit", "-8bit", "-bf16")


def _hf_cache_dir() -> Path:
    """Resolve the HuggingFace hub cache, honouring HF_HOME / HF_HUB_CACHE."""
    if env := os.environ.get("HF_HUB_CACHE"):
        return Path(env)
    if env := os.environ.get("HF_HOME"):
        return Path(env) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _scan_hf_cache_mlx_models() -> List[str]:
    """Return cached HF repo IDs that look like MLX models, in `org/repo` form.

    Cache directory format is `models--<org>--<repo>`; the repo segment may
    contain its own hyphens but never a literal `--`, so a 3-part split is safe.
    Filters to MLX-publishing orgs OR repos whose name carries the usual MLX
    quantization hints.
    """
    cache = _hf_cache_dir()
    if not cache.is_dir():
        return []

    found: List[str] = []
    for entry in cache.iterdir():
        name = entry.name
        if not name.startswith("models--") or not entry.is_dir():
            continue
        parts = name.split("--", 2)
        if len(parts) != 3:
            continue
        _, org, repo = parts
        if org in _MLX_HF_ORGS or any(hint in repo for hint in _MLX_REPO_HINTS):
            found.append(f"{org}/{repo}")
    return sorted(found)


def _prompt_mlx_custom_model_id() -> str:
    """Custom MLX model id prompt with HF-cache autocomplete.

    Cached suggestions come from `~/.cache/huggingface/hub/models--*` and are
    filtered to MLX-publishing orgs or MLX-flavored repo names. Tab cycles
    through matches; you can still type an arbitrary HF id to download a new
    one on first use.
    """
    suggestions = _scan_hf_cache_mlx_models()

    if suggestions:
        console.print(
            f"[dim]Found {len(suggestions)} MLX model(s) in your HF cache. "
            "Press Tab to autocomplete, or type a new ID (will download on first use).[/dim]"
        )
        try:
            answer = questionary.autocomplete(
                "Enter MLX model ID:",
                choices=suggestions,
                ignore_case=True,
                match_middle=True,
                validate=lambda x: len(x.strip()) > 0 or "Please enter a model ID.",
            ).ask()
        except Exception:
            # Fallback if the terminal can't handle the prompt_toolkit autocomplete UI.
            answer = questionary.text(
                "Enter MLX model ID:",
                validate=lambda x: len(x.strip()) > 0 or "Please enter a model ID.",
            ).ask()
    else:
        console.print(
            "[dim]No MLX models found in your HF cache yet. "
            "Type any 'org/repo' id (e.g. mlx-community/Qwen2.5-32B-Instruct-4bit) "
            "and mlx_lm.server will download it on first use.[/dim]"
        )
        answer = questionary.text(
            "Enter MLX model ID:",
            validate=lambda x: len(x.strip()) > 0 or "Please enter a model ID.",
        ).ask()

    if not answer:
        console.print("\n[red]No model ID entered. Exiting...[/red]")
        exit(1)
    return answer.strip()


def _select_model(provider: str, mode: str) -> str:
    """Select a model for the given provider and mode (quick/deep)."""
    if provider.lower() == "openrouter":
        return select_openrouter_model()

    if provider.lower() == "azure":
        return (
            questionary.text(
                f"Enter Azure deployment name ({mode}-thinking):",
                validate=lambda x: len(x.strip()) > 0 or "Please enter a deployment name.",
            )
            .ask()
            .strip()
        )

    choice = questionary.select(
        f"Select Your [{mode.title()}-Thinking LLM Engine]:",
        choices=[questionary.Choice(display, value=value) for display, value in get_model_options(provider, mode)],
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
        if provider.lower() == "mlx":
            return _prompt_mlx_custom_model_id()
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
        ("Apple oMLX", "mlx", "http://localhost:8000/v1"),
    ]

    choice = questionary.select(
        "Select your LLM Provider:",
        choices=[questionary.Choice(display, value=(provider_key, url)) for display, provider_key, url in PROVIDERS],
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


def print_mlx_setup_reminder(backend_url: Optional[str]) -> None:
    """Tell the user to start an MLX server before analysis (printed right after MLX is chosen).

    Supports both stock `mlx_lm.server` (single model, no auth) and
    [oMLX](https://omlx.ai) (`omlx serve`, multi-model, requires an API key).
    """
    base = backend_url or "http://localhost:8000/v1"
    example = "mlx-community/Qwen2.5-32B-Instruct-4bit"
    console.print(
        Panel(
            "[bold]Apple MLX needs a running local server.[/bold]\n\n"
            "Pick one and start it in another terminal:\n\n"
            "  [bold]oMLX (multi-model, recommended for quick + deep)[/bold]\n"
            "    [cyan]brew install jundot/omlx/omlx[/cyan]\n"
            "    [cyan]omlx serve --port 8000[/cyan]\n"
            "    [dim]oMLX requires an API key by default. Either:[/dim]\n"
            "    [dim]· export [bold]OMLX_API_KEY[/bold]=<key> in this shell, or[/dim]\n"
            "    [dim]· launch with --api-key <key>, or[/dim]\n"
            "    [dim]· toggle off API-key auth for localhost in oMLX settings.[/dim]\n\n"
            "  [bold]mlx_lm.server (single model per process, no auth)[/bold]\n"
            "    [cyan]pip install mlx-lm[/cyan]\n"
            f"    [cyan]mlx_lm.server --model {example} --port 8000[/cyan]\n"
            "    [dim]Use the same model ID for quick + deep, or run two servers on "
            "different ports.[/dim]\n\n"
            f"TradingAgents will call [bold]{base}[/bold].\n\n"
            "[dim]Pick a model that fits your Mac's unified memory and how long you want "
            "agent traces to run; larger 4-bit models need more RAM for weights and KV "
            "cache—if you hit pressure, use a smaller model or fewer debate rounds.[/dim]",
            title="MLX prerequisite",
            border_style="yellow",
        )
    )


def warn_mlx_quick_deep_mismatch(quick_model: str, deep_model: str) -> None:
    """Warn when quick and deep differ; mlx_lm.server only serves one loaded model."""
    if quick_model == deep_model:
        return
    console.print(
        Panel(
            "[yellow]Quick-thinking and deep-thinking model IDs differ.[/yellow]\n\n"
            "[bold]mlx_lm.server[/bold] only has one weights bundle in memory. Requests still send "
            "different [bold]model[/bold] names, but the server will keep answering with whatever "
            "it loaded at startup.\n\n"
            "Pick the [bold]same[/bold] model in both steps, or run two servers (e.g. ports "
            "8000 and 8001) and point quick/deep at different [bold]backend_url[/bold] values in code.",
            title="MLX: one server, one model",
            border_style="yellow",
        )
    )


def verify_mlx_server_reachable(backend_url: Optional[str]) -> None:
    """Validate the MLX endpoint before the dashboard takes over.

    Two failure modes get short, actionable panels instead of letting LangGraph
    bury the cause in a 200-line traceback:

      1. Nothing listening on host:port (server not started, wrong port).
      2. Server is up but rejects the bearer with HTTP 401 — typical for oMLX
         when ``OMLX_API_KEY`` is unset; rare for stock ``mlx_lm.server``.
    """
    raw = backend_url or "http://localhost:8000/v1"
    parsed = urlparse(raw)
    host = parsed.hostname or "localhost"
    scheme = (parsed.scheme or "http").lower()
    if scheme == "https":
        port = parsed.port or 443
    else:
        port = parsed.port or 80

    try:
        with socket.create_connection((host, port), timeout=5):
            pass
    except OSError as exc:
        example = "mlx-community/Qwen2.5-32B-Instruct-4bit"
        console.print(
            Panel(
                f"[bold red]Nothing is accepting connections at {host}:{port}[/bold red] "
                f"(expected MLX server for [bold]{raw}[/bold]).\n\n"
                "Start a server in another terminal, then re-run the CLI:\n"
                f"  [cyan]omlx serve --port {port}[/cyan]   # multi-model (jundot/omlx)\n"
                f"  [cyan]mlx_lm.server --model {example} --port {port}[/cyan]   # single model\n\n"
                f"[dim]Details: {exc}[/dim]",
                title="Connection refused",
                border_style="red",
            )
        )
        exit(1)

    import requests as _requests

    bearer = os.environ.get("OMLX_API_KEY") or "local"
    try:
        resp = _requests.get(
            raw.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {bearer}"},
            timeout=5,
        )
    except _requests.RequestException:
        # Server is up enough to accept TCP but the /models probe failed for
        # other reasons — defer to the agent run, which will surface the real
        # error if any.
        return

    if resp.status_code == 401:
        body_hint = ""
        try:
            err = resp.json().get("error", {}).get("message")
            if err:
                body_hint = f"\n[dim]Server says: {err}[/dim]"
        except Exception:
            pass
        omlx_running = "omlx" in resp.headers.get("server", "").lower()
        suspected = "oMLX" if omlx_running else "your MLX server"
        console.print(
            Panel(
                f"[bold red]{suspected} returned HTTP 401 at {raw}/models.[/bold red]\n\n"
                "It requires an API key, but [bold]OMLX_API_KEY[/bold] is not set in your "
                "shell. Pick one:\n\n"
                "  1. Export the key TradingAgents should send:\n"
                "     [cyan]export OMLX_API_KEY=<your-key>[/cyan]\n"
                "     then re-run the CLI.\n\n"
                "  2. Or restart the server with that same key:\n"
                "     [cyan]omlx serve --api-key <your-key> --port "
                f"{port}[/cyan]\n\n"
                "  3. Or disable API-key auth for localhost in oMLX's settings "
                "(Admin UI → Global Settings) and restart the server."
                f"{body_hint}",
                title="MLX server requires an API key",
                border_style="red",
            )
        )
        exit(1)


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
        style=questionary.Style(
            [
                ("selected", "fg:cyan noinherit"),
                ("highlighted", "fg:cyan noinherit"),
                ("pointer", "fg:cyan noinherit"),
            ]
        ),
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
        style=questionary.Style(
            [
                ("selected", "fg:cyan noinherit"),
                ("highlighted", "fg:cyan noinherit"),
                ("pointer", "fg:cyan noinherit"),
            ]
        ),
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
        style=questionary.Style(
            [
                ("selected", "fg:green noinherit"),
                ("highlighted", "fg:green noinherit"),
                ("pointer", "fg:green noinherit"),
            ]
        ),
    ).ask()


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
        style=questionary.Style(
            [
                ("selected", "fg:yellow noinherit"),
                ("highlighted", "fg:yellow noinherit"),
                ("pointer", "fg:yellow noinherit"),
            ]
        ),
    ).ask()

    if choice == "custom":
        return (
            questionary.text(
                "Enter language name (e.g. Turkish, Vietnamese, Thai, Indonesian):",
                validate=lambda x: len(x.strip()) > 0 or "Please enter a language name.",
            )
            .ask()
            .strip()
        )

    return choice
