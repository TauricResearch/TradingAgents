"""GUI configuration: API keys + default run settings.

Stored at ~/.tradingagents/gui_config.json with mode 0600. The file is
plaintext JSON — it sits next to the rest of the user's local TradingAgents
state and never leaves the machine. API keys read from a project-local .env
take precedence when present so existing CLI workflows keep working.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Dict, cast

from tradingagents.default_config import DEFAULT_CONFIG

try:
    from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS  # noqa: F401
except Exception:  # pragma: no cover — surfaced as empty dropdowns
    MODEL_OPTIONS = {}

GUI_CONFIG_PATH = Path.home() / ".tradingagents" / "gui_config.json"

PROVIDER_KEYS: Dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "glm": "ZHIPU_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "alpha_vantage": "ALPHA_VANTAGE_API_KEY",
}

PROVIDER_LABELS: Dict[str, str] = {
    "openai": "OpenAI (GPT)",
    "google": "Google (Gemini)",
    "anthropic": "Anthropic (Claude)",
    "xai": "xAI (Grok)",
    "deepseek": "DeepSeek",
    "qwen": "Qwen (Alibaba DashScope)",
    "glm": "GLM (Zhipu)",
    "openrouter": "OpenRouter",
    "ollama": "Ollama (local)",
    "azure": "Azure OpenAI",
    "alpha_vantage": "Alpha Vantage (data)",
}

LLM_PROVIDERS = [
    "openai", "google", "anthropic", "xai", "deepseek",
    "qwen", "glm", "openrouter", "ollama", "azure",
]

DATA_VENDORS = ["yfinance", "alpha_vantage"]


def _empty_config() -> Dict[str, Any]:
    data_vendors = cast(Dict[str, str], DEFAULT_CONFIG["data_vendors"])
    defaults = {
        "llm_provider": DEFAULT_CONFIG["llm_provider"],
        "deep_think_llm": DEFAULT_CONFIG["deep_think_llm"],
        "quick_think_llm": DEFAULT_CONFIG["quick_think_llm"],
        "max_debate_rounds": DEFAULT_CONFIG["max_debate_rounds"],
        "max_risk_discuss_rounds": DEFAULT_CONFIG["max_risk_discuss_rounds"],
        "data_vendors": dict(data_vendors),
        "output_language": DEFAULT_CONFIG["output_language"],
        "checkpoint_enabled": DEFAULT_CONFIG["checkpoint_enabled"],
        # Ollama base URL — empty means "use the framework default" which is
        # http://localhost:11434/v1 from inside the container (i.e. talking
        # to the container itself, which is wrong for most setups). Set to
        # http://host.docker.internal:11434/v1 to reach a host-side Ollama
        # on the same machine, or http://<other-server>:11434/v1 for an
        # Ollama running elsewhere on your LAN.
        "ollama_base_url": "",
    }
    return {"api_keys": {}, "defaults": defaults, "ui": {}}


def load() -> Dict[str, Any]:
    """Load the GUI config. Returns a fresh default config if none exists."""
    if not GUI_CONFIG_PATH.exists():
        return _empty_config()
    try:
        with open(GUI_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return _empty_config()

    base = _empty_config()
    base["api_keys"].update(data.get("api_keys", {}))
    base["defaults"].update(data.get("defaults", {}))
    base["ui"].update(data.get("ui", {}))
    return base


def save(cfg: Dict[str, Any]) -> None:
    """Write GUI config to disk and chmod it to 0600 on POSIX.

    On Windows the chmod call still runs but only toggles the read-only bit;
    the file lives under the user profile so OS-level ACLs already restrict
    it to the current user.
    """
    GUI_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GUI_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    try:
        os.chmod(GUI_CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def resolve_api_key(provider: str) -> str | None:
    """Return the API key for ``provider`` honoring env vars first.

    Order: process env (set by the user or by .env via dotenv), then GUI
    config. The CLI workflow uses ``.env``; the GUI workflow stores keys in
    ``gui_config.json``. Either path works without conflict.
    """
    env_name = PROVIDER_KEYS.get(provider)
    if not env_name:
        return None
    if os.environ.get(env_name):
        return os.environ[env_name]
    return load().get("api_keys", {}).get(env_name)


def model_choices_for(provider: str, mode: str) -> tuple[list[str], Dict[str, str]]:
    """Return ``(values, labels)`` for a provider's model dropdown.

    ``mode`` is ``"deep"`` or ``"quick"``. ``values`` is the list of model
    ids ordered as in the catalog, suitable for an ``st.selectbox`` with
    ``accept_new_options=True``. ``labels`` is a value→display-string map
    for ``format_func``.
    """
    values: list[str] = []
    labels: Dict[str, str] = {}
    by_mode = (MODEL_OPTIONS.get(provider) or {}).get(mode) or []
    for label, value in by_mode:
        if value == "custom":
            continue  # catalog's own custom marker — accept_new_options replaces it
        if value in labels:
            continue
        values.append(value)
        labels[value] = label
    return values, labels


def export_env(cfg: Dict[str, Any]) -> Dict[str, str]:
    """Build an env dict for subprocess launch.

    Starts from the parent process env, then overlays any keys stored in the
    GUI config that are not already present, so .env-set keys still win.
    """
    env = dict(os.environ)
    for env_name, value in cfg.get("api_keys", {}).items():
        if value and not env.get(env_name):
            env[env_name] = value
    return env
