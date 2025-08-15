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


# Centralized model definitions - single source of truth
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
        ("Claude Opus 4 - Most powerful Anthropic model", "claude-opus-4-0"),
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


def _get_all_models_for_custom_provider(model_type: str) -> list:
    """Get unified model list for custom provider with all available models from all providers.

    Args:
        model_type: Either 'shallow' or 'deep' to get the appropriate model set

    Returns:
        List of (description, model_value) tuples
    """
    # Use the centralized model definitions
    if model_type == "shallow":
        provider_models = SHALLOW_AGENT_OPTIONS
    else:  # deep
        provider_models = DEEP_AGENT_OPTIONS

    # Combine all models with provider labels
    all_models = []
    for provider_name, models in provider_models.items():
        provider_display_name = provider_name.title()
        for description, model_value in models:
            labeled_description = f"{description} ({provider_display_name})"
            all_models.append((labeled_description, model_value))

    # Add custom model option at the end
    all_models.append(("Custom Model - Enter your own model name", "__CUSTOM_MODEL__"))

    return all_models


def _select_custom_provider_model(model_type: str, title: str, default_model: str) -> str:
    """Handle model selection for custom provider with unified model list.

    Args:
        model_type: Either 'shallow' or 'deep'
        title: Title for the selection prompt
        default_model: Default model name for custom input

    Returns:
        Selected model name
    """
    all_models = _get_all_models_for_custom_provider(model_type)

    choice = questionary.select(
        title,
        choices=[
            questionary.Choice(display, value=value)
            for display, value in all_models
        ],
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select\n- Your custom endpoint should support the selected model",
        style=questionary.Style(
            [
                ("selected", "fg:magenta noinherit"),
                ("highlighted", "fg:magenta noinherit"),
                ("pointer", "fg:magenta noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        from rich.console import Console
        console = Console()
        console.print(f"\n[red]No {model_type} thinking model selected. Exiting...[/red]")
        exit(1)

    # Handle custom model input
    if choice == "__CUSTOM_MODEL__":
        custom_model = questionary.text(
            f"Enter your custom {model_type} thinking model name:",
            default=default_model,
            instruction="\n- Enter the exact model name as supported by your custom endpoint\n- Press Enter to confirm"
        ).ask()

        if not custom_model:
            from rich.console import Console
            console = Console()
            console.print(f"\n[red]No custom {model_type} model name entered. Exiting...[/red]")
            exit(1)

        return custom_model

    return choice


def select_shallow_thinking_agent(provider) -> str:
    """Select shallow thinking llm engine using an interactive selection."""

    # Handle custom provider - use unified model selection
    if provider.lower().startswith("custom"):
        return _select_custom_provider_model(
            model_type="shallow",
            title="Select Your [Quick-Thinking LLM Engine] (Custom Provider - All Models Available):",
            default_model="gpt-4o-mini"
        )

    # Use centralized shallow thinking model definitions

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
        from rich.console import Console
        console = Console()
        console.print(
            "\n[red]No shallow thinking llm engine selected. Exiting...[/red]"
        )
        exit(1)

    return choice


def select_deep_thinking_agent(provider) -> str:
    """Select deep thinking llm engine using an interactive selection."""

    # Handle custom provider - use unified model selection
    if provider.lower().startswith("custom"):
        return _select_custom_provider_model(
            model_type="deep",
            title="Select Your [Deep-Thinking LLM Engine] (Custom Provider - All Models Available):",
            default_model="o4-mini"
        )

    # Use centralized deep thinking model definitions

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
        from rich.console import Console
        console = Console()
        console.print("\n[red]No deep thinking llm engine selected. Exiting...[/red]")
        exit(1)

    return choice

def validate_custom_url(url: str) -> str:
    """Validate that a custom URL is properly formatted and has a valid hostname."""
    import re
    from urllib.parse import urlparse
    from rich.console import Console

    if not url:
        return ""

    console = Console()

    # Basic URL format validation
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    if not url_pattern.match(url):
        console.print(f"[red]Error: Invalid CUSTOM_BASE_URL format: {url}[/red]")
        console.print(f"[red]Please provide a valid URL (e.g., https://api.example.com/v1)[/red]")
        exit(1)

    # Additional validation using urlparse
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            raise ValueError("No hostname found")
        return url
    except Exception as e:
        console.print(f"[red]Error: Invalid CUSTOM_BASE_URL: {url}[/red]")
        console.print(f"[red]URL parsing error: {e}[/red]")
        exit(1)


def get_custom_provider_info() -> tuple[str, str] | None:
    """Get custom provider info if both URL and API key are provided."""
    import os
    from urllib.parse import urlparse

    custom_url = os.getenv("CUSTOM_BASE_URL")
    custom_api_key = os.getenv("CUSTOM_API_KEY")

    if custom_url and custom_api_key:
        validated_url = validate_custom_url(custom_url)
        parsed = urlparse(validated_url)
        hostname = parsed.netloc
        return f"Custom ({hostname})", validated_url

    return None


def select_llm_provider() -> tuple[str, str]:
    """Select the LLM provider with support for a custom OpenAI-compatible endpoint."""

    # Define default providers
    BASE_URLS = [
        ("OpenAI", "https://api.openai.com/v1"),
        ("Anthropic", "https://api.anthropic.com/"),
        ("Google", "https://generativelanguage.googleapis.com/v1"),
        ("Openrouter", "https://openrouter.ai/api/v1"),
        ("Ollama", "http://localhost:11434/v1"),
    ]

    # Add custom provider at the beginning if available
    custom_info = get_custom_provider_info()
    if custom_info:
        BASE_URLS.insert(0, custom_info)
    
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
        from rich.console import Console
        console = Console()
        console.print("\n[red]No LLM provider selected. Exiting...[/red]")
        exit(1)

    display_name, url = choice
    print(f"You selected: {display_name}\tURL: {url}")

    return display_name, url
