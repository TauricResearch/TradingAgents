from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from cli.utils import normalize_ticker_symbol


ALL_ANALYSTS = ("market", "social", "news", "fundamentals")
VALID_TRADE_DATE_MODES = {"latest_available", "today", "previous_business_day", "explicit"}


@dataclass(frozen=True)
class RunSettings:
    tickers: list[str]
    analysts: list[str] = field(default_factory=lambda: list(ALL_ANALYSTS))
    output_language: str = "Korean"
    trade_date_mode: str = "latest_available"
    explicit_trade_date: str | None = None
    timezone: str = "Asia/Seoul"
    max_debate_rounds: int = 1
    max_risk_discuss_rounds: int = 1
    latest_market_data_lookback_days: int = 14
    continue_on_ticker_error: bool = True


@dataclass(frozen=True)
class LLMSettings:
    provider: str = "codex"
    deep_model: str = "gpt-5.4"
    quick_model: str = "gpt-5.4"
    codex_reasoning_effort: str = "medium"
    codex_summary: str = "none"
    codex_personality: str = "none"
    codex_request_timeout: float = 180.0
    codex_max_retries: int = 2
    codex_cleanup_threads: bool = True
    codex_workspace_dir: str | None = None
    codex_binary: str | None = None


@dataclass(frozen=True)
class StorageSettings:
    archive_dir: Path
    site_dir: Path


@dataclass(frozen=True)
class SiteSettings:
    title: str = "TradingAgents Daily Reports"
    subtitle: str = "Automated multi-agent market analysis powered by Codex"
    max_runs_on_homepage: int = 30


@dataclass(frozen=True)
class ScheduledAnalysisConfig:
    run: RunSettings
    llm: LLMSettings
    storage: StorageSettings
    site: SiteSettings
    config_path: Path


def load_scheduled_config(path: str | Path) -> ScheduledAnalysisConfig:
    config_path = Path(path).resolve()
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    run_raw = raw.get("run") or {}
    llm_raw = raw.get("llm") or {}
    storage_raw = raw.get("storage") or {}
    site_raw = raw.get("site") or {}

    tickers = _normalize_tickers(run_raw.get("tickers") or [])
    if not tickers:
        raise ValueError("Scheduled analysis config must declare at least one ticker in [run].tickers.")

    analysts = _normalize_analysts(run_raw.get("analysts") or list(ALL_ANALYSTS))

    trade_date_mode = str(run_raw.get("trade_date_mode", "latest_available")).strip().lower()
    explicit_trade_date = None
    if run_raw.get("trade_date"):
        trade_date_mode = "explicit"
        explicit_trade_date = _validate_trade_date(str(run_raw["trade_date"]))
    elif trade_date_mode == "explicit":
        explicit_trade_date = _validate_trade_date(str(run_raw.get("explicit_trade_date", "")).strip())

    if trade_date_mode not in VALID_TRADE_DATE_MODES:
        raise ValueError(
            f"Unsupported trade_date_mode '{trade_date_mode}'. "
            f"Expected one of: {', '.join(sorted(VALID_TRADE_DATE_MODES))}."
        )

    timezone_name = str(run_raw.get("timezone", "Asia/Seoul")).strip()
    ZoneInfo(timezone_name)

    base_dir = config_path.parent
    archive_dir = _resolve_path(storage_raw.get("archive_dir", ".tradingagents-scheduled/archive"), base_dir)
    site_dir = _resolve_path(storage_raw.get("site_dir", "site"), base_dir)

    return ScheduledAnalysisConfig(
        run=RunSettings(
            tickers=tickers,
            analysts=analysts,
            output_language=str(run_raw.get("output_language", "Korean")).strip() or "Korean",
            trade_date_mode=trade_date_mode,
            explicit_trade_date=explicit_trade_date,
            timezone=timezone_name,
            max_debate_rounds=int(run_raw.get("max_debate_rounds", 1)),
            max_risk_discuss_rounds=int(run_raw.get("max_risk_discuss_rounds", 1)),
            latest_market_data_lookback_days=int(run_raw.get("latest_market_data_lookback_days", 14)),
            continue_on_ticker_error=bool(run_raw.get("continue_on_ticker_error", True)),
        ),
        llm=LLMSettings(
            provider=str(llm_raw.get("provider", "codex")).strip().lower() or "codex",
            deep_model=str(llm_raw.get("deep_model", "gpt-5.4")).strip() or "gpt-5.4",
            quick_model=str(llm_raw.get("quick_model", "gpt-5.4")).strip() or "gpt-5.4",
            codex_reasoning_effort=str(llm_raw.get("codex_reasoning_effort", "medium")).strip() or "medium",
            codex_summary=str(llm_raw.get("codex_summary", "none")).strip() or "none",
            codex_personality=str(llm_raw.get("codex_personality", "none")).strip() or "none",
            codex_request_timeout=float(llm_raw.get("codex_request_timeout", 180.0)),
            codex_max_retries=int(llm_raw.get("codex_max_retries", 2)),
            codex_cleanup_threads=bool(llm_raw.get("codex_cleanup_threads", True)),
            codex_workspace_dir=_optional_string(llm_raw.get("codex_workspace_dir")),
            codex_binary=_optional_string(llm_raw.get("codex_binary")),
        ),
        storage=StorageSettings(
            archive_dir=archive_dir,
            site_dir=site_dir,
        ),
        site=SiteSettings(
            title=str(site_raw.get("title", "TradingAgents Daily Reports")).strip() or "TradingAgents Daily Reports",
            subtitle=str(
                site_raw.get(
                    "subtitle",
                    "Automated multi-agent market analysis powered by Codex",
                )
            ).strip()
            or "Automated multi-agent market analysis powered by Codex",
            max_runs_on_homepage=int(site_raw.get("max_runs_on_homepage", 30)),
        ),
        config_path=config_path,
    )


def with_overrides(
    config: ScheduledAnalysisConfig,
    *,
    archive_dir: str | Path | None = None,
    site_dir: str | Path | None = None,
    tickers: Iterable[str] | None = None,
    trade_date: str | None = None,
) -> ScheduledAnalysisConfig:
    run = config.run
    storage = config.storage

    if tickers is not None:
        run = replace(run, tickers=_normalize_tickers(tickers))
    if trade_date:
        run = replace(run, trade_date_mode="explicit", explicit_trade_date=_validate_trade_date(trade_date))
    if archive_dir:
        storage = replace(storage, archive_dir=Path(archive_dir).expanduser().resolve())
    if site_dir:
        storage = replace(storage, site_dir=Path(site_dir).expanduser().resolve())

    return replace(config, run=run, storage=storage)


def _normalize_tickers(values: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        ticker = normalize_ticker_symbol(str(value))
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        normalized.append(ticker)
    return normalized


def _normalize_analysts(values: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        analyst = str(value).strip().lower()
        if analyst not in ALL_ANALYSTS:
            raise ValueError(
                f"Unsupported analyst '{analyst}'. Expected only: {', '.join(ALL_ANALYSTS)}."
            )
        if analyst in seen:
            continue
        seen.add(analyst)
        normalized.append(analyst)
    return normalized or list(ALL_ANALYSTS)


def _resolve_path(value: str | os.PathLike[str], base_dir: Path) -> Path:
    expanded = os.path.expanduser(os.path.expandvars(str(value)))
    path = Path(expanded)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _validate_trade_date(value: str) -> str:
    text = value.strip()
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        raise ValueError(f"Invalid trade date '{value}'. Expected YYYY-MM-DD.")
    return text
