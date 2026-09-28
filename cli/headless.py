"""Non-interactive analysis using the same graph and report writer as the UI.

No prompt or user-preference file is touched by this path. The caller supplies
a symbol; an optional progress observer never changes the execution workflow.
"""

from __future__ import annotations

import json
import math
import os
from copy import deepcopy
from datetime import datetime
from enum import Enum
from pathlib import Path
from tempfile import mkdtemp

from cli.models import AnalystType
from cli.progress import analysis_progress
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


def _create_graph(selected_analysts: list[str], config: dict):
    # Keep the planning/validation helpers usable without importing LLM SDKs.
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    return TradingAgentsGraph(selected_analysts=selected_analysts, config=config, debug=False)


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
) -> dict:
    """Run once, automatically save all reports, and return a JSON-safe summary.

    Each invocation owns a new output directory, including the graph's JSON
    state logs. The normal decision memory and checkpoint cache paths are kept.
    Report/save failures propagate to the command so automation sees failure.
    """
    ticker, trade_date, selected, asset_type = resolve_analysis_inputs(
        symbol, analysis_date, analysts, asset_type
    )
    book = load_portfolio(portfolio_path) if portfolio_path is not None else None
    if output_dir is None:
        root = Path(config["results_dir"]).expanduser().resolve() / "runs"
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = Path(mkdtemp(prefix=f"{ticker}_{trade_date}_{stamp}_", dir=root))
    else:
        run_dir = Path(output_dir).expanduser().resolve()
        if run_dir.exists() and (not run_dir.is_dir() or any(run_dir.iterdir())):
            raise ValueError("--output-dir must be a new or empty directory (existing reports are never overwritten)")
        run_dir.mkdir(parents=True, exist_ok=True)
    run_config = {**deepcopy(config), "results_dir": str(run_dir)}
    with analysis_progress(progress_mode, ticker, trade_date, selected) as progress:
        graph = _create_graph(selected, run_config)
        if progress is not None:
            graph.propagator.callbacks.append(progress)
        state, decision = graph.propagate(ticker, trade_date, asset_type=asset_type, portfolio=book)
        if progress is not None:
            progress.stage("Saving reports")
        report = graph.save_reports(state, ticker, save_path=run_dir / "reports")
        # An allowlist, not a config dump: headers, API keys and portfolio holdings
        # must not accidentally end up in stdout or metadata.
        summary = {
            "symbol": ticker,
            "date": trade_date,
            "asset_type": asset_type,
            "analysts": selected,
            "provider": run_config["llm_provider"],
            "quick_model": run_config["quick_think_llm"],
            "deep_model": run_config["deep_think_llm"],
            "debate_rounds": run_config["max_debate_rounds"],
            "risk_rounds": run_config["max_risk_discuss_rounds"],
            "decision": decision,
            "needs_review": decision == "REVIEW",
            "output_dir": str(run_dir),
            "report": str(Path(report).resolve()),
        }
        (run_dir / "run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8")
        if progress is not None:
            progress.complete()
        return summary
