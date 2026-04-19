import questionary
from typing import List, Optional, Tuple, Dict

from cli.models import AnalystType

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
            ("GPT-5.4 Nano - Cheapest GPT-5.4-class, high-volume", "gpt-5.4-nano"),
            ("GPT-5.4 Mini - Strong mini for coding & agents", "gpt-5.4-mini"),
            ("GPT-5 Nano - Fast, cost-efficient", "gpt-5-nano"),
            ("GPT-5 Mini - Cost-optimized reasoning", "gpt-5-mini"),
            ("GPT-4.1 - Smartest non-reasoning, 1M context", "gpt-4.1"),
        ],
        "anthropic": [
            ("Claude Haiku 4.5 - Fastest, near-frontier intelligence", "claude-haiku-4-5"),
            ("Claude Sonnet 4.6 - Best speed + intelligence balance", "claude-sonnet-4-6"),
            ("Claude Sonnet 4.5 - Previous gen balanced", "claude-sonnet-4-5"),
        ],
        "google": [
            ("Gemini 3 Flash - Next-gen fast, 1M context", "gemini-3-flash-preview"),
            ("Gemini 3.1 Flash Lite - Cheapest Gemini 3 series", "gemini-3.1-flash-lite-preview"),
            ("Gemini 2.5 Flash - Balanced, recommended", "gemini-2.5-flash"),
            ("Gemini 2.5 Flash Lite - Fast, low-cost", "gemini-2.5-flash-lite"),
        ],
        "xai": [
            ("Grok 4.20 (Non-Reasoning) - Latest flagship, 2M ctx", "grok-4.20-0309-non-reasoning"),
            ("Grok 4.1 Fast (Non-Reasoning) - Speed optimized, 2M ctx", "grok-4-1-fast-non-reasoning"),
            ("Grok 4.1 Fast (Reasoning) - High-performance, 2M ctx", "grok-4-1-fast-reasoning"),
        ],
        "openrouter": [
            ("NVIDIA Nemotron 3 Nano 30B (free)", "nvidia/nemotron-3-nano-30b-a3b:free"),
            ("Z.AI GLM 4.5 Air (free)", "z-ai/glm-4.5-air:free"),
        ],
        "groq": [
            ("GPT-OSS 20B - Fast open-weight", "openai/gpt-oss-20b"),
            ("Llama 3.3 70B Versatile - Fast inference", "llama-3.3-70b-versatile"),
            ("Llama 3.1 8B Instant - Ultra-fast", "llama-3.1-8b-instant"),
            ("Qwen3 32B - Strong reasoning", "qwen/qwen3-32b"),
        ],
        "together": [
            ("Qwen3.5 9B - Fast, efficient", "Qwen/Qwen3.5-9B"),
            ("Llama 4 Scout 17B - Llama 4, 16 experts", "meta-llama/Llama-4-Scout-17B-16E-Instruct"),
            ("Llama 3.3 70B Turbo - Fast inference", "meta-llama/Meta-Llama-3.3-70B-Instruct-Turbo"),
        ],
        "ollama": [
            ("Llama 3.3:latest (70B, local)", "llama3.3:latest"),
            ("Llama 3.2:latest (3B, local)", "llama3.2:latest"),
            ("Qwen3:latest (8B, local)", "qwen3:latest"),
            ("GPT-OSS:latest (20B, local)", "gpt-oss:latest"),
            ("Gemma4:latest (31B, local)", "gemma4:latest"),
        ],
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
            ("GPT-5.4 - Latest flagship, agentic & coding", "gpt-5.4"),
            ("GPT-5.4 Mini - GPT-5.4-class, faster", "gpt-5.4-mini"),
            ("GPT-5 - Advanced reasoning", "gpt-5"),
            ("o3 - Frontier reasoning model", "o3"),
            ("o3 Pro - Enhanced reasoning, highest quality", "o3-pro"),
            ("GPT-4.1 - Smartest non-reasoning, 1M context", "gpt-4.1"),
        ],
        "anthropic": [
            ("Claude Opus 4.7 - Most capable, agentic coding", "claude-opus-4-7"),
            ("Claude Opus 4.6 - Previous flagship", "claude-opus-4-6"),
            ("Claude Sonnet 4.6 - Best speed + intelligence", "claude-sonnet-4-6"),
            ("Claude Opus 4.5 - Premium intelligence", "claude-opus-4-5"),
            ("Claude Haiku 4.5 - Fast + extended thinking", "claude-haiku-4-5"),
        ],
        "google": [
            ("Gemini 3.1 Pro - Latest flagship, reasoning-first", "gemini-3.1-pro-preview"),
            ("Gemini 3 Flash - Next-gen fast, 1M context", "gemini-3-flash-preview"),
            ("Gemini 2.5 Pro - Stable, strong reasoning", "gemini-2.5-pro"),
            ("Gemini 2.5 Flash - Balanced, recommended", "gemini-2.5-flash"),
        ],
        "xai": [
            ("Grok 4.20 (Reasoning) - Latest flagship, 2M ctx", "grok-4.20-0309-reasoning"),
            ("Grok 4.20 Multi-Agent - Multi-agent optimized, 2M ctx", "grok-4.20-multi-agent-0309"),
            ("Grok 4.1 Fast (Reasoning) - High-performance, 2M ctx", "grok-4-1-fast-reasoning"),
            ("Grok 4.20 (Non-Reasoning) - Fast flagship, 2M ctx", "grok-4.20-0309-non-reasoning"),
        ],
        "openrouter": [
            ("Z.AI GLM 4.5 Air (free)", "z-ai/glm-4.5-air:free"),
            ("NVIDIA Nemotron 3 Nano 30B (free)", "nvidia/nemotron-3-nano-30b-a3b:free"),
        ],
        "groq": [
            ("GPT-OSS 120B - Largest open-weight", "openai/gpt-oss-120b"),
            ("GPT-OSS 20B - Fast open-weight", "openai/gpt-oss-20b"),
            ("Llama 4 Scout 17B - Llama 4, 16 experts", "meta-llama/llama-4-scout-17b-16e-instruct"),
            ("Llama 3.3 70B Versatile - Fast inference", "llama-3.3-70b-versatile"),
        ],
        "together": [
            ("Qwen3.5 397B - Strongest open-weight reasoning", "Qwen/Qwen3.5-397B-A17B"),
            ("DeepSeek V3.1 - Latest DeepSeek, 671B", "deepseek-ai/DeepSeek-V3.1"),
            ("DeepSeek R1 - Full reasoning model", "deepseek-ai/DeepSeek-R1"),
            ("Llama 4 Maverick 17B - Llama 4, 128 experts", "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"),
        ],
        "ollama": [
            ("Llama 3.3:latest (70B, local)", "llama3.3:latest"),
            ("Llama 3.1:latest (8B, local)", "llama3.1:latest"),
            ("DeepSeek-R1:latest (local)", "deepseek-r1:latest"),
            ("GPT-OSS:latest (20B, local)", "gpt-oss:latest"),
            ("Qwen3:latest (8B, local)", "qwen3:latest"),
            ("Gemma4:latest (31B, local)", "gemma4:latest"),
        ],
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
        ("Google", "https://generativelanguage.googleapis.com/v1"),
        ("Anthropic", "https://api.anthropic.com/"),
        ("xAI", "https://api.x.ai/v1"),
        ("Groq", "https://api.groq.com/openai/v1"),
        ("Together", "https://api.together.xyz/v1"),
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


def select_persona() -> Optional[str]:
    """Select an investment persona using an interactive selection."""

    PERSONA_OPTIONS = [
        ("Default - No specific investment persona", None),
        ("Warren Buffett - Value investing, long-term holding, margin of safety", "warren_buffett"),
        ("Ray Dalio - Diversified ETF, rebalancing, macro-driven systematic decisions", "ray_dalio"),
        ("Peter Lynch - Growth stocks, PEG ratio, invest in what you know", "peter_lynch"),
    ]

    choice = questionary.select(
        "Select Your [Investment Persona]:",
        choices=[
            questionary.Choice(display, value=value)
            for display, value in PERSONA_OPTIONS
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

    return choice


def select_broker_mode() -> dict:
    """Interactive broker execution configuration."""
    enable = questionary.confirm(
        "Enable broker execution? (Execute trades after analysis)",
        default=False,
        style=questionary.Style(
            [
                ("highlighted", "fg:red noinherit"),
            ]
        ),
    ).ask()

    if not enable:
        return {"enabled": False}

    mode = questionary.select(
        "Select Trading Mode:",
        choices=[
            questionary.Choice(
                "Paper Trading (모의투자) - Safe, no real money", value="paper"
            ),
            questionary.Choice(
                "Real Trading (실투자) - Uses real money!", value="real"
            ),
        ],
        style=questionary.Style(
            [
                ("selected", "fg:red noinherit"),
                ("highlighted", "fg:red noinherit"),
                ("pointer", "fg:red noinherit"),
            ]
        ),
    ).ask()

    if mode == "real":
        confirm = questionary.confirm(
            "WARNING: Real trading will execute real orders with real money. Continue?",
            default=False,
        ).ask()
        if not confirm:
            mode = "paper"

    position_pct = questionary.select(
        "Position Sizing (% of portfolio per trade):",
        choices=[
            questionary.Choice("5% of portfolio per trade", value=0.05),
            questionary.Choice("10% of portfolio per trade", value=0.10),
            questionary.Choice("2% of portfolio per trade (conservative)", value=0.02),
        ],
        style=questionary.Style(
            [
                ("selected", "fg:red noinherit"),
                ("highlighted", "fg:red noinherit"),
                ("pointer", "fg:red noinherit"),
            ]
        ),
    ).ask()

    return {
        "enabled": True,
        "mode": mode,
        "default_position_pct": position_pct,
    }


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
