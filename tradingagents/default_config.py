"""TradingAgents default configuration builder.

Config precedence is explicit and deterministic:
1. hardcoded defaults
2. values from .env
3. explicit process environment

This module is the single owner of .env loading behavior.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping, MutableMapping

from dotenv import dotenv_values


_PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DOTENV_PREFIX = "TRADINGAGENTS_"


def _is_truthy(raw: str | None, *, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _should_load_dotenv_by_default() -> bool:
    """Decide whether DEFAULT_CONFIG should include .env values."""
    explicit = os.getenv("TRADINGAGENTS_LOAD_DOTENV")
    if explicit is not None:
        return _is_truthy(explicit, default=True)
    # Tests should be deterministic by default and must opt in explicitly.
    return "pytest" not in sys.modules


def _dotenv_paths(dotenv_path: str | Path | None) -> list[Path]:
    if dotenv_path is not None:
        return [Path(dotenv_path)]

    candidates = [Path.cwd() / ".env", _REPO_ROOT / ".env"]
    deduped: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(candidate)
    return deduped


def _load_dotenv_overlay(dotenv_path: str | Path | None) -> dict[str, str]:
    """Load dotenv values without mutating os.environ.

    Path precedence matches historical behavior:
    - CWD .env first
    - repo-root .env as fallback
    """
    overlay: dict[str, str] = {}
    for path in _dotenv_paths(dotenv_path):
        if not path.exists():
            continue
        values = dotenv_values(path)
        for key, value in values.items():
            if not key or value is None:
                continue
            # First file wins for dotenv-level precedence.
            overlay.setdefault(key, value)
    return overlay


def _build_env_snapshot(
    *,
    load_dotenv: bool,
    dotenv_path: str | Path | None,
    environ: Mapping[str, str] | None,
) -> MutableMapping[str, str]:
    process_env = dict(os.environ if environ is None else environ)
    if not load_dotenv:
        return process_env

    merged = _load_dotenv_overlay(dotenv_path)
    # Explicit process env overrides .env.
    merged.update(process_env)
    return merged


def get_env_value(
    key: str,
    default=None,
    *,
    load_dotenv: bool | None = None,
    dotenv_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
):
    """Read an arbitrary environment variable with optional .env overlay.

    This preserves the config module's non-mutating dotenv behavior while
    allowing runtime integrations that still rely on standard env var names
    (for example ``OPENROUTER_API_KEY``) to resolve values from ``.env``.
    """
    if load_dotenv is None:
        load_dotenv = _should_load_dotenv_by_default()
    env = _build_env_snapshot(
        load_dotenv=load_dotenv,
        dotenv_path=dotenv_path,
        environ=environ,
    )
    value = env.get(key)
    if not value:  # None or empty string
        return default
    return value


def _env(key: str, default=None, *, env: Mapping[str, str] | None = None):
    """Read TRADINGAGENTS_<KEY> from the provided environment mapping."""
    source = (
        _build_env_snapshot(
            load_dotenv=_should_load_dotenv_by_default(),
            dotenv_path=None,
            environ=None,
        )
        if env is None
        else env
    )
    val = source.get(f"{_DOTENV_PREFIX}{key.upper()}")
    if not val:  # None or empty string
        return default
    return val


def _env_int(key: str, default=None, *, env: Mapping[str, str] | None = None):
    val = _env(key, env=env)
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _env_float(key: str, default=None, *, env: Mapping[str, str] | None = None):
    val = _env(key, env=env)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _tool_vendor_overrides(*, env: Mapping[str, str]) -> dict[str, str]:
    tool_env_map = {
        "get_insider_transactions": "VENDOR_INSIDER_TRANSACTIONS",
        "get_gap_candidates": "VENDOR_GAP_CANDIDATES",
        "get_gold_price": "VENDOR_GOLD_PRICE",
        "get_oil_prices": "VENDOR_OIL_PRICES",
        "get_bitcoin_price": "VENDOR_BITCOIN_PRICE",
    }
    overrides: dict[str, str] = {}
    for method, env_key in tool_env_map.items():
        vendor = _env(env_key, env=env)
        if vendor:
            overrides[method] = vendor
    return overrides


def build_default_config(
    *,
    load_dotenv: bool = True,
    dotenv_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict:
    """Build TradingAgents default configuration with explicit precedence."""
    env = _build_env_snapshot(
        load_dotenv=load_dotenv,
        dotenv_path=dotenv_path,
        environ=environ,
    )
    results_dir = _env(
        "RESULTS_DIR",
        _env("REPORTS_DIR", "./reports", env=env),
        env=env,
    )

    return {
        "project_dir": _PROJECT_DIR,
        "results_dir": results_dir,
        "data_cache_dir": os.path.join(_PROJECT_DIR, "dataflows/data_cache"),
        # LLM settings — all overridable via TRADINGAGENTS_<KEY> env vars
        "llm_provider": _env("LLM_PROVIDER", "openai", env=env),
        "deep_think_llm": _env("DEEP_THINK_LLM", "gpt-5.2", env=env),
        # Falls back to quick_think_llm when None.
        "mid_think_llm": _env("MID_THINK_LLM", env=env),
        "quick_think_llm": _env("QUICK_THINK_LLM", "gpt-5-mini", env=env),
        "backend_url": _env("BACKEND_URL", "https://api.openai.com/v1", env=env),
        # Per-role provider overrides (fallback to shared llm_provider/backend_url).
        "deep_think_llm_provider": _env("DEEP_THINK_LLM_PROVIDER", env=env),
        "deep_think_backend_url": _env("DEEP_THINK_BACKEND_URL", env=env),
        "mid_think_llm_provider": _env("MID_THINK_LLM_PROVIDER", env=env),
        "mid_think_backend_url": _env("MID_THINK_BACKEND_URL", env=env),
        "quick_think_llm_provider": _env("QUICK_THINK_LLM_PROVIDER", env=env),
        "quick_think_backend_url": _env("QUICK_THINK_BACKEND_URL", env=env),
        # Per-tier fallback LLM (used when primary model is unavailable).
        "quick_think_fallback_llm": _env("QUICK_THINK_FALLBACK_LLM", env=env),
        "quick_think_fallback_llm_provider": _env(
            "QUICK_THINK_FALLBACK_LLM_PROVIDER", env=env
        ),
        "mid_think_fallback_llm": _env("MID_THINK_FALLBACK_LLM", env=env),
        "mid_think_fallback_llm_provider": _env(
            "MID_THINK_FALLBACK_LLM_PROVIDER", env=env
        ),
        "deep_think_fallback_llm": _env("DEEP_THINK_FALLBACK_LLM", env=env),
        "deep_think_fallback_llm_provider": _env(
            "DEEP_THINK_FALLBACK_LLM_PROVIDER", env=env
        ),
        # Provider-specific thinking configuration (global + per role).
        "google_thinking_level": _env("GOOGLE_THINKING_LEVEL", env=env),
        "openai_reasoning_effort": _env("OPENAI_REASONING_EFFORT", env=env),
        "anthropic_effort": _env("ANTHROPIC_EFFORT", env=env),
        "deep_think_google_thinking_level": _env(
            "DEEP_THINK_GOOGLE_THINKING_LEVEL", env=env
        ),
        "deep_think_openai_reasoning_effort": _env(
            "DEEP_THINK_OPENAI_REASONING_EFFORT", env=env
        ),
        "mid_think_google_thinking_level": _env(
            "MID_THINK_GOOGLE_THINKING_LEVEL", env=env
        ),
        "mid_think_openai_reasoning_effort": _env(
            "MID_THINK_OPENAI_REASONING_EFFORT", env=env
        ),
        "quick_think_google_thinking_level": _env(
            "QUICK_THINK_GOOGLE_THINKING_LEVEL", env=env
        ),
        "quick_think_openai_reasoning_effort": _env(
            "QUICK_THINK_OPENAI_REASONING_EFFORT", env=env
        ),
        # Debate and discussion settings
        "max_debate_rounds": _env_int("MAX_DEBATE_ROUNDS", 2, env=env),
        "max_risk_discuss_rounds": _env_int("MAX_RISK_DISCUSS_ROUNDS", 2, env=env),
        "max_recur_limit": _env_int("MAX_RECUR_LIMIT", 100, env=env),
        # Concurrency settings
        "max_concurrent_pipelines": _env_int("MAX_CONCURRENT_PIPELINES", 5, env=env),
        "max_auto_tickers": _env_int("MAX_AUTO_TICKERS", 10, env=env),
        "scan_horizon_days": _env_int("SCAN_HORIZON_DAYS", 30, env=env),
        "trading_lookback_days": _env_int("TRADING_LOOKBACK_DAYS", 90, env=env),
        # Data vendor configuration
        "data_vendors": {
            "core_stock_apis": _env("VENDOR_CORE_STOCK_APIS", "yfinance", env=env),
            "technical_indicators": _env(
                "VENDOR_TECHNICAL_INDICATORS", "yfinance", env=env
            ),
            "fundamental_data": _env("VENDOR_FUNDAMENTAL_DATA", "yfinance", env=env),
            "news_data": _env("VENDOR_NEWS_DATA", "yfinance", env=env),
            "scanner_data": _env("VENDOR_SCANNER_DATA", "yfinance", env=env),
            "calendar_data": _env("VENDOR_CALENDAR_DATA", "finnhub", env=env),
        },
        # Tool-level overrides are opt-in only.
        "tool_vendors": _tool_vendor_overrides(env=env),
        # Report storage backend
        "mongo_uri": _env("MONGO_URI", env=env),
        "mongo_db": _env("MONGO_DB", "tradingagents", env=env),
        "default_portfolio_id": _env("DEFAULT_PORTFOLIO_ID", "main_portfolio", env=env),
    }


DEFAULT_CONFIG = build_default_config(
    load_dotenv=_should_load_dotenv_by_default(),
)
