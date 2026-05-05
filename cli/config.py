import json
import os
from pathlib import Path
from typing import Any

from cli.models import AnalystType
from tradingagents.dataflows.ticker_utils import normalize_ticker_symbol


CLI_CONFIG = {
    # Announcements
    "announcements_url": "https://api.tauric.ai/v1/announcements",
    "announcements_timeout": 1.0,
    "announcements_fallback": "[cyan]For more information, please visit[/cyan] [link=https://github.com/TauricResearch]https://github.com/TauricResearch[/link]",
}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL_CONFIG_PATH = PROJECT_ROOT / "tradingagents.local.json"


def load_cli_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load optional local JSON config and inject non-empty API keys into env."""
    config_path = Path(path) if path else DEFAULT_LOCAL_CONFIG_PATH
    if not config_path.exists():
        if config_path == DEFAULT_LOCAL_CONFIG_PATH or config_path.name == DEFAULT_LOCAL_CONFIG_PATH.name:
            return {}
        raise FileNotFoundError(f"配置文件不存在：{config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)
    if not isinstance(config, dict):
        raise ValueError("配置文件顶层必须是 JSON object。")

    for env_name, value in (config.get("api_keys") or {}).items():
        if value:
            os.environ[str(env_name)] = str(value)
    return config


def build_configured_selections(
    config: dict[str, Any],
    *,
    ticker: str,
    analysis_date: str,
) -> dict[str, Any]:
    """Build CLI selections from config plus runtime ticker/date inputs."""
    llm = config.get("llm") or {}
    run = config.get("run") or {}
    provider = str(llm.get("provider") or "mimo").lower()
    analysts = run.get("analysts") or ["market", "social", "news", "fundamentals"]

    return {
        "ticker": normalize_ticker_symbol(ticker),
        "analysis_date": analysis_date,
        "analysts": [_analyst_from_value(value) for value in analysts],
        "research_depth": int(run.get("research_depth", 1)),
        "llm_provider": provider,
        "backend_url": llm.get("backend_url") or _default_backend_url(provider),
        "shallow_thinker": llm.get("quick_think_llm") or _default_quick_model(provider),
        "deep_thinker": llm.get("deep_think_llm") or _default_deep_model(provider),
        "google_thinking_level": run.get("google_thinking_level"),
        "openai_reasoning_effort": run.get("openai_reasoning_effort"),
        "anthropic_effort": run.get("anthropic_effort"),
        "output_language": run.get("output_language", "Chinese"),
        "checkpoint_enabled": bool(run.get("checkpoint_enabled", False)),
        "save_report": bool(run.get("save_report", True)),
        "display_report": bool(run.get("display_report", False)),
        "data_vendors": config.get("data_vendors") or {},
    }


def _analyst_from_value(value: str) -> AnalystType:
    try:
        return AnalystType(str(value).lower())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in AnalystType)
        raise ValueError(f"未知分析师：{value}。可选值：{allowed}") from exc


def _default_backend_url(provider: str) -> str | None:
    if provider == "mimo":
        return "https://token-plan-sgp.xiaomimimo.com/anthropic"
    return None


def _default_quick_model(provider: str) -> str:
    if provider == "mimo":
        return "mimo-v2.5"
    return "gpt-5.4-mini"


def _default_deep_model(provider: str) -> str:
    if provider == "mimo":
        return "mimo-v2.5-pro"
    return "gpt-5.4"
