"""Settings persistence and run-config builder for the web UI."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tradingagents.default_config import DEFAULT_CONFIG

_SETTINGS_PATH = Path.home() / ".tradingagents" / "web_config.json"

PROVIDER_URLS: dict[str, str | None] = {
    "openai":     "https://api.openai.com/v1",
    "anthropic":  "https://api.anthropic.com/",
    "xai":        "https://api.x.ai/v1",
    "deepseek":   "https://api.deepseek.com",
    "qwen":       "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "glm":        "https://open.bigmodel.cn/api/paas/v4/",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama":     "http://localhost:11434/v1",
    "google":     None,
    "azure":      None,
}

DEFAULT_WEB_SETTINGS: dict[str, Any] = {
    "llm_provider": "openai",
    "backend_url": PROVIDER_URLS["openai"],
    "quick_think_llm": "gpt-4.1-mini",
    "deep_think_llm": "gpt-4.1",
    "anthropic_effort": None,
    "google_thinking_level": None,
    "openai_reasoning_effort": None,
    "research_depth": 1,
    "analysts": ["market", "news", "fundamentals"],
    "output_language": "English",
    "data_vendors": {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
    },
}


def load_settings(path: Path = _SETTINGS_PATH) -> dict[str, Any]:
    """Load web settings from disk, deep-merged over defaults so all keys are always present."""
    if not path.exists():
        return dict(DEFAULT_WEB_SETTINGS)
    with path.open(encoding="utf-8") as f:
        saved = json.load(f)
    merged = dict(DEFAULT_WEB_SETTINGS)
    for key, value in saved.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def save_settings(settings: dict[str, Any], path: Path = _SETTINGS_PATH) -> None:
    """Persist web settings to disk, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def build_run_config(web_config: dict[str, Any]) -> dict[str, Any]:
    """Merge web settings over DEFAULT_CONFIG, translating UI-only keys."""
    config = DEFAULT_CONFIG.copy()
    for key, value in web_config.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key] = {**config[key], **value}
        else:
            config[key] = value
    depth = web_config.get("research_depth", 1)
    config["max_debate_rounds"] = depth
    config["max_risk_discuss_rounds"] = depth
    config.pop("research_depth", None)
    return config
