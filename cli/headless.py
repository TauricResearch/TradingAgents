"""Resolve prompt-free inputs, then use the native interactive CLI runner.

Only argument/default resolution and the JSON summary are headless-specific;
execution, incremental logging, report names and the live view are shared.
"""

from __future__ import annotations

import json
import math
import os
from contextlib import suppress
from copy import deepcopy
from datetime import datetime
from enum import Enum
from pathlib import Path

from cli.models import AnalystType
from cli.run_output import run_directory
from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.symbols import normalize_symbol, safe_ticker_component
from tradingagents.llm_clients.api_key_env import PROVIDER_API_KEY_ENV
from tradingagents.llm_clients.headers import parse_llm_headers
from tradingagents.portfolio import load_portfolio


class ResearchEffort(str, Enum):
    SHALLOW = "shallow"
    MEDIUM = "medium"
    DEEP = "deep"


class AssetMode(str, Enum):
    AUTO = "auto"
    STOCK = "stock"
    CRYPTO = "crypto"


class ProviderAPI(str, Enum):
    AUTO = "auto"
    CHAT_COMPLETIONS = "chat_completions"
    RESPONSES = "responses"
    MESSAGES = "messages"


_EFFORT_ROUNDS = {"shallow": 1, "medium": 3, "deep": 5}
_ANALYST_KEYS = tuple(a.value for a in AnalystType)
_ROUND_ENV = {
    "max_debate_rounds": "TRADINGAGENTS_MAX_DEBATE_ROUNDS",
    "max_risk_discuss_rounds": "TRADINGAGENTS_MAX_RISK_ROUNDS",
}


def build_headless_config(
    base: dict,
    *,
    effort: str | None = None,
    debate_rounds: int | None = None,
    risk_rounds: int | None = None,
    headers: list[str] | None = None,
    **overrides,
) -> dict:
    """Explicit flags > environment > headless defaults (medium = 3 rounds).

    DEFAULT_CONFIG already contains the environment overlay. Do not mistake its
    ordinary one-round defaults for an explicit environment value. Changing the
    provider requires both model flags, and drops the previous endpoint/headers
    so credentials or provider-specific settings are not sent to the wrong host.
    """
    config = deepcopy(base)
    provider = overrides.get("llm_provider")
    if provider is not None:
        provider = provider.strip().lower()
        overrides["llm_provider"] = provider
        if provider != str(base.get("llm_provider", "")).lower():
            if not all(overrides.get(k) for k in ("quick_think_llm", "deep_think_llm")):
                raise ValueError("Changing --provider requires both --quick-model and --deep-model")
            config["backend_url"] = None
            config["llm_headers"] = None
    config.update({key: value for key, value in overrides.items() if value is not None})
    provider = str(config.get("llm_provider", "")).strip().lower()
    if provider not in PROVIDER_API_KEY_ENV:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    config["llm_provider"] = provider
    for key in ("quick_think_llm", "deep_think_llm"):
        model = config.get(key)
        if not isinstance(model, str) or not model.strip() or model.strip() == "custom":
            raise ValueError(f"{key} must contain a real, nonempty model ID")
        config[key] = model.strip()

    if effort is not None and effort not in _EFFORT_ROUNDS:
        raise ValueError("effort must be shallow, medium or deep")
    for key, env_var in _ROUND_ENV.items():
        if effort is not None or not os.environ.get(env_var):
            config[key] = _EFFORT_ROUNDS[effort or "medium"]
    if debate_rounds is not None:
        config["max_debate_rounds"] = debate_rounds
    if risk_rounds is not None:
        config["max_risk_discuss_rounds"] = risk_rounds
    for key in _ROUND_ENV:
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{key} must be a positive integer")

    # Preserve env headers unless a flag replaces the same name. HTTP names are
    # case-insensitive; last CLI occurrence wins without creating duplicates.
    merged = {key.lower(): (key, value)
              for key, value in parse_llm_headers(config.get("llm_headers")).items()}
    for header in headers or []:
        name, separator, value = header.partition(":")
        if not separator:
            raise ValueError("--header must use 'Name: value' syntax")
        pair = parse_llm_headers({name.strip(): value.strip()})
        merged[name.strip().lower()] = next(iter(pair.items()))
    config["llm_headers"] = dict(merged.values()) or None
    if config["llm_headers"] and provider in {"google", "bedrock"}:
        raise ValueError(f"llm_headers is not supported by the {provider} adapter")

    # None-valued defaults are overlaid as strings by DEFAULT_CONFIG. Coerce
    # them here just as the LLM factory does, rather than rejecting valid .env.
    for key, minimum in (("max_tokens", 1), ("llm_max_retries", 0)):
        value = config.get(key)
        if value is None or value == "":
            config[key] = None
            continue
        try:
            if isinstance(value, bool) or not isinstance(value, (int, str)):
                raise ValueError
            parsed = int(value)
            if parsed < minimum:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be an integer >= {minimum}") from None
        config[key] = parsed
    temperature = config.get("temperature")
    if temperature is not None and temperature != "":
        try:
            if isinstance(temperature, bool):
                raise ValueError
            temperature = float(temperature)
            if not math.isfinite(temperature) or temperature < 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("temperature must be a finite non-negative number") from None
        config["temperature"] = temperature
    return config


def resolve_analysis_inputs(
    symbol: str, analysis_date: str | None, analysts: str, asset_type: str,
) -> tuple[str, str, list[str], str]:
    """Validate all user inputs before constructing the graph or making requests."""
    ticker = safe_ticker_component(normalize_symbol(symbol))
    today = get_current_date()  # At invocation time, not import time; machine-local date.
    trade_date = today if analysis_date is None else analysis_date
    try:
        canonical = datetime.strptime(trade_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        raise ValueError("--date must use YYYY-MM-DD") from None
    if trade_date != canonical:
        raise ValueError("--date must use YYYY-MM-DD")
    if trade_date > today:
        raise ValueError("--date cannot be in the future")
    if asset_type not in {"auto", "stock", "crypto"}:
        raise ValueError("--asset-type must be auto, stock or crypto")
    if asset_type == "auto":
        asset_type = ("crypto" if ticker.endswith(("-USD", "-USDT", "-USDC", "-BTC", "-ETH"))
                      else "stock")

    requested = [part.strip().lower() for part in analysts.split(",")]
    requested = ["social" if key == "sentiment" else key for key in requested]
    if requested == ["all"]:
        selected = list(_ANALYST_KEYS)
    else:
        if not requested or any(key not in _ANALYST_KEYS for key in requested):
            raise ValueError("--analysts must be 'all' or a comma-separated selection of "
                             "market,social,news,fundamentals (sentiment is an alias for social)")
        # Match the UI's canonical execution order and remove duplicates.
        selected = [key for key in _ANALYST_KEYS if key in requested]
    # Match the existing interactive crypto flow: company fundamentals are not
    # applicable. An explicit incompatible request is an error, not a silent drop.
    if asset_type == "crypto" and "fundamentals" in selected:
        if requested != ["all"]:
            raise ValueError("The fundamentals analyst is not available for crypto")
        selected.remove("fundamentals")
    return ticker, trade_date, selected, asset_type


def _create_graph(selected_analysts: list[str], config: dict, callbacks=None):
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    return TradingAgentsGraph(selected_analysts=selected_analysts, config=config,
                              debug=False, callbacks=callbacks)


def run_headless_analysis(
    symbol: str,
    *,
    config: dict,
    analysis_date: str | None = None,
    analysts: str = "all",
    asset_type: str = "auto",
    portfolio_path: Path | None = None,
    output_dir: Path | None = None,
    progress_mode: str = "off",
    show_report: bool = False,
    save_report: bool = True,
    clear_checkpoints: bool = False,
) -> dict:
    """Resolve inputs and use the native runner without any prompts.

    `output_dir` is the complete-report export path (the interactive Save path),
    not a replacement results root. Logs always use results_dir/ticker/date.
    """
    from cli.run import run_analysis

    ticker, trade_date, selected, asset_type = resolve_analysis_inputs(
        symbol, analysis_date, analysts, asset_type
    )
    if output_dir is not None and not save_report:
        raise ValueError("--output-dir requires --save-report")
    book = load_portfolio(portfolio_path) if portfolio_path is not None else None
    if output_dir is not None and Path(output_dir).expanduser().exists() and not Path(output_dir).expanduser().is_dir():
        raise ValueError("--output-dir must be a directory")
    run_settings = deepcopy(config)  # Never relocate results_dir under runs/.
    directory = run_directory(run_settings, ticker, trade_date).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    summary = {
        "symbol": ticker,
        "date": trade_date,
        "asset_type": asset_type,
        "analysts": selected,
        "provider": run_settings["llm_provider"],
        "quick_model": run_settings["quick_think_llm"],
        "deep_model": run_settings["deep_think_llm"],
        "debate_rounds": run_settings["max_debate_rounds"],
        "risk_rounds": run_settings["max_risk_discuss_rounds"],
        "status": "running",
        "decision": None,
        "needs_review": True,
        "output_dir": str(directory),
        "log_file": str(directory / "message_tool.log"),
        "report": None,
    }

    def save_summary():
        # An allowlist: no headers, credentials, holdings or exception text.
        (directory / "run.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    save_summary()  # A failed rerun must not leave an older success summary.
    try:
        result = run_analysis(
            portfolio=book, config=run_settings,
            selections={"ticker": ticker, "analysis_date": trade_date,
                        "analysts": [AnalystType(key) for key in selected], "asset_type": asset_type},
            interactive=False, output_dir=output_dir, progress_mode=progress_mode,
            show_report=show_report, save_report=save_report, clear_checkpoints=clear_checkpoints,
            graph_factory=_create_graph,
        )
        summary.update(status="completed", decision=result.decision,
                       needs_review=result.decision == "REVIEW", report=str(result.report) if result.report is not None else None)
        save_summary()
    except BaseException as exc:
        summary.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                       decision=None, needs_review=True, report=None)
        # Do not replace the original error with a secondary disk failure.
        with suppress(OSError):
            save_summary()
        raise
    return summary
