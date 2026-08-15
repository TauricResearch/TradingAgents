import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cli.utils import provider_default_url
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.model_catalog import get_model_options

_TRADINGAGENTS_HOME = Path.home() / ".tradingagents"
PREFERENCES_PATH = _TRADINGAGENTS_HOME / "preferences.json"

PREFERENCE_KEYS = [
    "llm_provider",
    "quick_think_llm",
    "deep_think_llm",
    "backend_url",
    "output_language",
    "max_debate_rounds",
    "max_risk_discuss_rounds",
    "google_thinking_level",
    "openai_reasoning_effort",
    "anthropic_effort",
]

CURRENT_VERSION = 1

_ROUND_KEYS = {"max_debate_rounds", "max_risk_discuss_rounds"}
_OPTIONAL_STRING_KEYS = {
    "backend_url",
    "google_thinking_level",
    "openai_reasoning_effort",
    "anthropic_effort",
}
_REQUIRED_STRING_KEYS = {
    "llm_provider",
    "quick_think_llm",
    "deep_think_llm",
    "output_language",
}


@dataclass(frozen=True)
class PreferenceLoadResult:
    status: Literal["missing", "valid", "invalid", "future"]
    preferences: dict | None = None

console = Console()

_PROVIDER_DISPLAY = {
    "openai": "OpenAI",
    "google": "Google (Gemini)",
    "anthropic": "Anthropic (Claude)",
    "xai": "xAI",
    "deepseek": "DeepSeek",
    "qwen": "Qwen (International)",
    "qwen-cn": "Qwen (China)",
    "glm": "GLM (Z.AI)",
    "glm-cn": "GLM (BigModel China)",
    "minimax": "MiniMax (Global)",
    "minimax-cn": "MiniMax (China)",
    "openrouter": "OpenRouter",
    "mistral": "Mistral",
    "kimi": "Kimi (Moonshot)",
    "groq": "Groq",
    "nvidia": "NVIDIA NIM",
    "azure": "Azure OpenAI",
    "bedrock": "AWS Bedrock",
    "ollama": "Ollama",
    "openai_compatible": "OpenAI-compatible",
}


def _pretty_provider(provider: str) -> str:
    return _PROVIDER_DISPLAY.get(provider.lower(), provider)


def _is_valid_preference(key: str, value: Any) -> bool:
    if key in _ROUND_KEYS:
        return isinstance(value, int) and not isinstance(value, bool) and value > 0
    if key in _OPTIONAL_STRING_KEYS:
        return value is None or (isinstance(value, str) and bool(value.strip()))
    if key in _REQUIRED_STRING_KEYS:
        return isinstance(value, str) and bool(value.strip())
    return False


def _validate_preference_bundle(prefs: dict) -> str | None:
    required_keys = _REQUIRED_STRING_KEYS | _ROUND_KEYS
    missing_keys = sorted(required_keys - prefs.keys())
    if missing_keys:
        return f"missing: {', '.join(missing_keys)}"
    invalid_keys = [
        key for key in PREFERENCE_KEYS
        if key in prefs and not _is_valid_preference(key, prefs[key])
    ]
    if invalid_keys:
        return f"invalid: {', '.join(invalid_keys)}"
    try:
        get_model_options(prefs["llm_provider"], "quick")
        get_model_options(prefs["llm_provider"], "deep")
    except KeyError:
        return f"unknown provider: {prefs['llm_provider']}"
    return None


def load_preferences_result() -> PreferenceLoadResult:
    if not PREFERENCES_PATH.exists():
        return PreferenceLoadResult("missing")
    try:
        data = json.loads(PREFERENCES_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return PreferenceLoadResult("invalid")
        version = data.get("_version", 0)
        if not isinstance(version, int) or isinstance(version, bool):
            console.print(
                "[yellow]Preferences file has an invalid version. "
                "Running full setup.[/yellow]"
            )
            return PreferenceLoadResult("invalid")
        if version > CURRENT_VERSION:
            console.print(
                "[yellow]Preferences file is from a newer version of TradingAgents. "
                "Run 'tradingagents config reset' and then reconfigure.[/yellow]"
            )
            return PreferenceLoadResult("future")
        prefs = {}
        invalid_keys = []
        for key in PREFERENCE_KEYS:
            if key in data and _is_valid_preference(key, data[key]):
                prefs[key] = data[key]
            elif key in data:
                invalid_keys.append(key)
        if invalid_keys:
            console.print(
                "[yellow]Ignoring invalid saved preference(s): "
                f"{', '.join(invalid_keys)}.[/yellow]"
            )
        bundle_error = _validate_preference_bundle(prefs)
        if bundle_error:
            console.print(
                "[yellow]Saved preferences are incomplete or invalid ("
                f"{bundle_error}). Running full setup.[/yellow]"
            )
            return PreferenceLoadResult("invalid")
        return PreferenceLoadResult("valid", prefs)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        console.print("[yellow]Preferences file is corrupted. Running full setup.[/yellow]")
        return PreferenceLoadResult("invalid")


def load_preferences() -> dict | None:
    return load_preferences_result().preferences


def save_preferences(prefs: dict) -> bool:
    bundle_error = _validate_preference_bundle(prefs)
    if bundle_error:
        console.print(
            "[red]Cannot save incomplete or invalid preferences ("
            f"{bundle_error}).[/red]"
        )
        return False
    data = {
        "_version": CURRENT_VERSION,
        "_updated": datetime.now(timezone.utc).isoformat(),
    }
    for key in PREFERENCE_KEYS:
        if key in prefs:
            data[key] = prefs[key]
    temporary_path = None
    try:
        _TRADINGAGENTS_HOME.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=_TRADINGAGENTS_HOME,
            prefix=f".{PREFERENCES_PATH.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        if os.name != "nt":
            temporary_path.chmod(0o600)
        os.replace(temporary_path, PREFERENCES_PATH)
        return True
    except OSError:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        console.print(f"[red]Failed to write preferences to {PREFERENCES_PATH}[/red]")
        return False


def clear_preferences() -> bool:
    try:
        if PREFERENCES_PATH.exists():
            PREFERENCES_PATH.unlink()
        return True
    except OSError:
        return False


def display_preferences_summary(prefs: dict):
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="dim")
    table.add_column("Value")

    provider = prefs.get("llm_provider", "")
    table.add_row("LLM Provider", _pretty_provider(provider))

    deep_model = prefs.get("deep_think_llm") or "-"
    quick_model = prefs.get("quick_think_llm") or "-"
    table.add_row("Deep Think Model", str(deep_model))
    table.add_row("Quick Think Model", str(quick_model))

    backend = prefs.get("backend_url")
    if backend:
        table.add_row("Backend URL", str(backend))
    else:
        table.add_row("Backend URL", "[dim]provider default[/dim]")

    table.add_row("Output Language", str(prefs.get("output_language", "English")))
    table.add_row(
        "Research Depth",
        f"{prefs.get('max_debate_rounds', 1)} debate / "
        f"{prefs.get('max_risk_discuss_rounds', 1)} risk rounds",
    )

    reasoning_effort = prefs.get("openai_reasoning_effort")
    if reasoning_effort:
        table.add_row("Reasoning Effort", str(reasoning_effort))
    thinking_level = prefs.get("google_thinking_level")
    if thinking_level:
        table.add_row("Gemini Thinking", str(thinking_level))
    anthropic_effort = prefs.get("anthropic_effort")
    if anthropic_effort:
        table.add_row("Claude Effort", str(anthropic_effort))

    panel = Panel(
        table,
        title="[bold]Saved Preferences[/bold]",
        border_style="blue",
        padding=(1, 2),
    )
    console.print()
    console.print(panel)


def prompt_use_preferences() -> Literal["use", "skip", "reconfigure"] | None:
    return questionary.select(
        "Use these preferences?",
        choices=[
            questionary.Choice(
                "Yes — use saved settings (Recommended)",
                value="use",
            ),
            questionary.Choice(
                "No — run full setup, without saving (one-off)",
                value="skip",
            ),
            questionary.Choice(
                "Reconfigure — run full setup and save new preferences",
                value="reconfigure",
            ),
        ],
        style=questionary.Style([
            ("selected", "fg:green noinherit"),
            ("highlighted", "fg:green noinherit"),
            ("pointer", "fg:green noinherit"),
        ]),
    ).ask()


def _env_or_pref(
    env_var: str,
    config_key: str,
    pref_key: str,
    prefs: dict,
    defaults: dict,
) -> Any:
    if os.environ.get(env_var):
        return defaults[config_key]
    return prefs.get(pref_key, defaults[config_key])


def _provider_default_model(provider: str, mode: str) -> str:
    for _, model in get_model_options(provider, mode):
        if model != "custom":
            return model
    raise ValueError(
        f"Provider '{provider}' has no default {mode} model. Set the matching "
        f"TRADINGAGENTS_{'QUICK' if mode == 'quick' else 'DEEP'}_THINK_LLM "
        "environment variable or run 'tradingagents analyze --configure'."
    )


def preferences_to_selections(prefs: dict, defaults: dict | None = None) -> dict:
    defaults = DEFAULT_CONFIG if defaults is None else defaults
    saved_provider = str(prefs.get("llm_provider", "")).lower()
    env_provider = os.environ.get("TRADINGAGENTS_LLM_PROVIDER")
    effective_provider = (
        env_provider.strip().lower() if env_provider else saved_provider or defaults["llm_provider"]
    )
    provider_changed = bool(env_provider) and effective_provider != saved_provider

    if provider_changed:
        backend_url = (
            defaults["backend_url"]
            if os.environ.get("TRADINGAGENTS_LLM_BACKEND_URL")
            else provider_default_url(effective_provider)
        )
        shallow_thinker = (
            defaults["quick_think_llm"]
            if os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM")
            else _provider_default_model(effective_provider, "quick")
        )
        deep_thinker = (
            defaults["deep_think_llm"]
            if os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM")
            else _provider_default_model(effective_provider, "deep")
        )
        google_thinking_level = (
            defaults["google_thinking_level"]
            if effective_provider == "google"
            and os.environ.get("TRADINGAGENTS_GOOGLE_THINKING_LEVEL")
            else None
        )
        openai_reasoning_effort = (
            defaults["openai_reasoning_effort"]
            if effective_provider == "openai"
            and os.environ.get("TRADINGAGENTS_OPENAI_REASONING_EFFORT")
            else None
        )
        anthropic_effort = (
            defaults["anthropic_effort"]
            if effective_provider == "anthropic"
            and os.environ.get("TRADINGAGENTS_ANTHROPIC_EFFORT")
            else None
        )
    else:
        backend_url = _env_or_pref(
            "TRADINGAGENTS_LLM_BACKEND_URL",
            "backend_url",
            "backend_url",
            prefs,
            defaults,
        )
        shallow_thinker = _env_or_pref(
            "TRADINGAGENTS_QUICK_THINK_LLM",
            "quick_think_llm",
            "quick_think_llm",
            prefs,
            defaults,
        )
        deep_thinker = _env_or_pref(
            "TRADINGAGENTS_DEEP_THINK_LLM",
            "deep_think_llm",
            "deep_think_llm",
            prefs,
            defaults,
        )
        google_thinking_level = _env_or_pref(
            "TRADINGAGENTS_GOOGLE_THINKING_LEVEL",
            "google_thinking_level",
            "google_thinking_level",
            prefs,
            defaults,
        )
        openai_reasoning_effort = _env_or_pref(
            "TRADINGAGENTS_OPENAI_REASONING_EFFORT",
            "openai_reasoning_effort",
            "openai_reasoning_effort",
            prefs,
            defaults,
        )
        anthropic_effort = _env_or_pref(
            "TRADINGAGENTS_ANTHROPIC_EFFORT",
            "anthropic_effort",
            "anthropic_effort",
            prefs,
            defaults,
        )

    max_debate_rounds = _env_or_pref(
        "TRADINGAGENTS_MAX_DEBATE_ROUNDS",
        "max_debate_rounds",
        "max_debate_rounds",
        prefs,
        defaults,
    )
    max_risk_discuss_rounds = _env_or_pref(
        "TRADINGAGENTS_MAX_RISK_ROUNDS",
        "max_risk_discuss_rounds",
        "max_risk_discuss_rounds",
        prefs,
        defaults,
    )

    return {
        "research_depth": max_debate_rounds,
        "max_debate_rounds": max_debate_rounds,
        "max_risk_discuss_rounds": max_risk_discuss_rounds,
        "shallow_thinker": shallow_thinker,
        "deep_thinker": deep_thinker,
        "backend_url": backend_url,
        "llm_provider": effective_provider,
        "google_thinking_level": google_thinking_level,
        "openai_reasoning_effort": openai_reasoning_effort,
        "anthropic_effort": anthropic_effort,
        "output_language": _env_or_pref(
            "TRADINGAGENTS_OUTPUT_LANGUAGE",
            "output_language",
            "output_language",
            prefs,
            defaults,
        ),
    }


def config_to_preferences(config: dict) -> dict:
    return {k: config.get(k) for k in PREFERENCE_KEYS}
