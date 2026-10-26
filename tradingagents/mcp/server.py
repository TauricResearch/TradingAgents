"""The MCP tool surface for TradingAgents.

The server exposes two kinds of tools: long-running analyses and backtests,
which return a job id immediately, and read-only data lookups that answer in
one call.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

import tradingagents
from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.router import route_to_vendor
from tradingagents.default_config import build_default_config
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS

from . import runners
from .jobs import Job, JobManager, JobNotFound

logger = logging.getLogger(__name__)

INSTRUCTIONS = """\
TradingAgents is a multi-agent stock and crypto research framework. It runs a
team of analysts (market, sentiment, news, fundamentals), a bull/bear research
debate, a trader, and a risk/portfolio manager.

A full analysis takes minutes. Call analyze_ticker to start one; it returns a
job_id immediately. Poll get_job_status until the status is succeeded or failed,
then call get_job_result. Use get_analysis_report to read one report section.
run_backtest works the same way for a ticker/date grid.

For quick lookups without running the agent graph, use the data tools:
get_stock_data, get_technical_indicators, get_fundamentals,
get_financial_statement, get_news, get_global_news, get_insider_transactions,
get_macro_indicators, and get_prediction_markets.

Outputs are research, not financial, investment, or trading advice.
"""

_READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
_READ_ONLY_LOCAL = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
_WRITES = ToolAnnotations(readOnlyHint=False, openWorldHint=True)

_ANNOTATIONS = {
    "analyze_ticker": _WRITES,
    "run_backtest": _WRITES,
    "get_job_status": _READ_ONLY_LOCAL,
    "get_job_result": _READ_ONLY_LOCAL,
    "get_analysis_report": _READ_ONLY_LOCAL,
    "list_jobs": _READ_ONLY_LOCAL,
    "cancel_job": ToolAnnotations(readOnlyHint=False, openWorldHint=False, idempotentHint=True),
    "get_server_info": _READ_ONLY_LOCAL,
    "get_stock_data": _READ_ONLY,
    "get_technical_indicators": _READ_ONLY,
    "get_fundamentals": _READ_ONLY,
    "get_financial_statement": _READ_ONLY,
    "get_news": _READ_ONLY,
    "get_global_news": _READ_ONLY,
    "get_insider_transactions": _READ_ONLY,
    "get_macro_indicators": _READ_ONLY,
    "get_prediction_markets": _READ_ONLY,
}

_TOOL_NAMES = tuple(_ANNOTATIONS)

_SECTIONS = (
    "complete",
    "market",
    "sentiment",
    "news",
    "fundamentals",
    "research",
    "trader",
    "risk",
    "decision",
)

_MAX_WAIT_SECONDS = 300.0


def _provider_status(provider: str) -> dict[str, Any]:
    provider = (provider or "").lower()
    if not provider:
        return {"ready": False, "detail": "no LLM provider is configured"}
    if provider == "chatgpt":
        try:
            from tradingagents.llm_clients import chatgpt_auth
        except Exception as exc:
            return {
                "ready": False,
                "detail": f"ChatGPT sign-in is unavailable ({type(exc).__name__}: {exc})",
            }
        email = chatgpt_auth.signed_in_as()
        if email:
            return {"ready": True, "detail": f"signed in as {email}"}
        return {"ready": False, "detail": chatgpt_auth.LOGIN_HINT}
    if provider == "ollama":
        return {"ready": True, "detail": "local Ollama needs no API key"}
    if provider == "bedrock":
        return {"ready": None, "detail": "uses the AWS credential chain"}
    env = get_api_key_env(provider)
    if env is None:
        return {"ready": None, "detail": f"no key check for provider {provider!r}"}
    if os.environ.get(env):
        return {"ready": True, "detail": f"{env} is set"}
    return {"ready": False, "detail": f"{env} is not set"}


class TradingAgentsMCPServer:
    """Builds the FastMCP server and owns its job manager."""

    def __init__(
        self,
        manager: JobManager | None = None,
        host: str = "127.0.0.1",
        port: int = 8000,
        debug: bool = False,
        log_level: str = "INFO",
    ):
        self.manager = manager or JobManager()
        self.server = FastMCP(
            name="tradingagents",
            instructions=INSTRUCTIONS,
            host=host,
            port=port,
            debug=debug,
            log_level=log_level,
        )
        for name in _TOOL_NAMES:
            self.server.add_tool(
                getattr(self, name),
                name=name,
                annotations=_ANNOTATIONS[name],
            )

    def get_server_info(self) -> dict[str, Any]:
        """Report the version, available analysts/providers, defaults, and job counts."""
        config = build_default_config()
        keys = (
            "llm_provider",
            "deep_think_llm",
            "quick_think_llm",
            "deep_think_provider",
            "quick_think_provider",
            "max_debate_rounds",
            "max_risk_discuss_rounds",
            "output_language",
            "checkpoint_enabled",
            "data_vendors",
        )
        default_provider = config.get("llm_provider") or ""
        deep_provider = config.get("deep_think_provider") or default_provider
        quick_provider = config.get("quick_think_provider") or default_provider
        deep_status = _provider_status(deep_provider)
        quick_status = _provider_status(quick_provider)
        analysis_ready = deep_status["ready"] is not False and quick_status["ready"] is not False
        return {
            "name": "tradingagents",
            "version": tradingagents.__version__,
            "analysts": list(runners.ANALYSTS),
            "analyst_aliases": dict(runners.ANALYST_ALIASES),
            "asset_types": list(runners.ASSET_TYPES),
            "providers": sorted(MODEL_OPTIONS),
            "defaults": {key: config.get(key) for key in keys},
            "config_overrides": sorted(runners.ALLOWED_CONFIG_OVERRIDES),
            "analysis_ready": analysis_ready,
            "provider_status": {
                "deep": {"provider": deep_provider, **deep_status},
                "quick": {"provider": quick_provider, **quick_status},
            },
            "reports_dir": config["results_dir"],
            "memory_log": config["memory_log_path"],
            "jobs": self.manager.stats(),
            "notes": [
                "Data tools work without an LLM provider.",
                "Full analysis needs a provider key, a ChatGPT plan sign-in, or Ollama.",
                "A full analysis returns a job_id; poll get_job_status, then get_job_result.",
                "Outputs are research, not financial advice.",
            ],
        }

    def analyze_ticker(
        self,
        ticker: str,
        trade_date: str | None = None,
        analysts: list[str] | str | None = None,
        asset_type: str | None = None,
        portfolio: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        save_reports: bool = True,
        html: bool = True,
        wait_seconds: float = 0,
    ) -> dict[str, Any]:
        """Start a full multi-agent analysis of one ticker and return its job id.

        The analysis runs in the background because it takes minutes. Poll
        get_job_status(job_id) until the status is succeeded or failed, then call
        get_job_result(job_id). Set wait_seconds (at most 300) to block briefly
        for a result before returning.

        Args:
            ticker: Yahoo-style symbol, e.g. AAPL, 0700.HK, BTC-USD, GC=F.
            trade_date: Analysis date YYYY-MM-DD; defaults to today and cannot be in the future.
            analysts: Any of market, sentiment (alias social), news, fundamentals.
                Omit for every analyst the asset type allows.
            asset_type: "stock" or "crypto"; inferred from the ticker when omitted.
            portfolio: Optional book as {"cash": 25000, "currency": "USD",
                "positions": [{"ticker": "AAPL", "quantity": 10, "average_price": 190}]}.
            config: Optional per-run TradingAgents settings, e.g.
                {"llm_provider": "anthropic", "max_debate_rounds": 2}.
                API keys, paths, and retry policy cannot be set here.
            save_reports: Write the report tree under the configured results directory.
            html: Also write complete_report.html when saving.
            wait_seconds: Block up to this many seconds for completion.
        """
        symbol = runners.normalize_ticker(ticker)
        date = runners.validate_date(trade_date or get_current_date(), "trade_date")
        kind = runners.resolve_asset_type(symbol, asset_type)
        chosen = runners.resolve_analysts(analysts, kind)
        book = runners.resolve_portfolio(portfolio)
        runners.build_run_config(config)

        job = self.manager.submit(
            "analysis",
            runners.run_analysis_job,
            ticker=symbol,
            trade_date=date,
            asset_type=kind,
            analysts=chosen,
            portfolio=book,
            config=config,
            save_reports=bool(save_reports),
            html=bool(html),
        )
        self._wait(job.id, wait_seconds)
        return self._job_summary(job)

    def run_backtest(
        self,
        tickers: list[str] | str,
        start_date: str,
        end_date: str,
        every_n_days: int = 7,
        analysts: list[str] | str | None = None,
        asset_type: str | None = None,
        portfolio: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        run_id: str | None = None,
        wait_seconds: float = 0,
    ) -> dict[str, Any]:
        """Start a backtest over a ticker/date grid and return its job id.

        Each cell is a full analysis; the result scores settled decisions by
        rating against the instrument's regional benchmark. Poll get_job_status
        and then get_job_result, as for analyze_ticker.

        Args:
            tickers: One ticker or a list, e.g. ["NVDA", "AAPL"].
            start_date: First analysis date YYYY-MM-DD.
            end_date: Last analysis date YYYY-MM-DD, not after today.
            every_n_days: Days between analysis dates (default 7).
            analysts: Any of market, sentiment (alias social), news, fundamentals.
            asset_type: "stock" or "crypto"; inferred when omitted. One grid runs one type.
            portfolio: Optional standing book, identical for every cell.
            config: Optional per-run TradingAgents settings.
            run_id: Continue an earlier sweep; cells already in its log are skipped.
            wait_seconds: Block up to this many seconds for completion.
        """
        names = runners.resolve_tickers(tickers)
        start = runners.validate_date(start_date, "start_date")
        end = runners.validate_date(end_date, "end_date")
        if start > end:
            raise ValueError(f"end_date {end} is before start_date {start}")
        try:
            every = int(every_n_days)
        except (TypeError, ValueError):
            raise ValueError(f"every_n_days must be an integer, got {every_n_days!r}") from None
        if every < 1:
            raise ValueError("every_n_days must be at least 1")

        if asset_type is None:
            kinds = {runners.detect_asset_type(ticker) for ticker in names}
            if len(kinds) > 1:
                raise ValueError("a backtest runs one asset type at a time; split the tickers")
            kind = kinds.pop()
        else:
            kind = runners.resolve_asset_type(names[0], asset_type)

        chosen = runners.resolve_analysts(analysts, kind)
        book = runners.resolve_portfolio(portfolio)
        runners.build_run_config(config)

        job = self.manager.submit(
            "backtest",
            runners.run_backtest_job,
            tickers=names,
            start_date=start,
            end_date=end,
            every_n_days=every,
            asset_type=kind,
            analysts=chosen,
            portfolio=book,
            config=config,
            run_id=run_id,
        )
        self._wait(job.id, wait_seconds)
        return self._job_summary(job)

    def get_job_status(self, job_id: str, wait_seconds: float = 0) -> dict[str, Any]:
        """Check one background job, optionally waiting up to wait_seconds for it to finish.

        Returns status (queued/running/succeeded/failed/cancelled), the current
        stage, progress_percent, timestamps, and any error.
        """
        job = self._get_job(job_id)
        self._wait(job.id, wait_seconds)
        return self._job_status(job)

    def get_job_result(
        self,
        job_id: str,
        include_reports: bool = False,
        wait_seconds: float = 0,
    ) -> dict[str, Any]:
        """Fetch a finished job's result, waiting up to wait_seconds if needed.

        For an analysis, the result includes the rating, the Portfolio Manager's
        decision, saved report paths, and the run settings. Set include_reports
        to also return every report section; otherwise use get_analysis_report
        to read one section at a time.
        """
        job = self._get_job(job_id)
        self._wait(job.id, wait_seconds)
        snapshot = job.snapshot()
        result = dict(snapshot.pop("result", None) or {})
        snapshot.pop("result_ready", None)

        if job.status != "succeeded":
            snapshot["message"] = (
                "The job has not finished successfully; poll get_job_status."
                if job.status in {"queued", "running"}
                else "The job did not produce a result."
            )
            return snapshot

        if result.get("kind") == "analysis":
            reports = result.pop("reports", {})
            snapshot.update(result)
            snapshot["sections_available"] = [name for name in _SECTIONS[1:] if reports.get(name)]
            if include_reports:
                snapshot["reports"] = reports
            else:
                snapshot["reports_hint"] = (
                    "Call get_analysis_report(job_id, section) for one section: "
                    + ", ".join(snapshot["sections_available"])
                )
        else:
            snapshot.update(result)
        return snapshot

    def get_analysis_report(
        self,
        job_id: str,
        section: str = "complete",
        max_chars: int = 50000,
    ) -> dict[str, Any]:
        """Read one report section from a finished analysis.

        Sections: complete, market, sentiment, news, fundamentals, research,
        trader, risk, decision. "complete" reads the saved complete_report.md
        when available, else assembles the sections.
        """
        name = str(section).strip().lower()
        if name not in _SECTIONS:
            raise ValueError(f"unknown section {section!r}; choose from {', '.join(_SECTIONS)}")
        job = self._get_job(job_id)
        if job.status != "succeeded":
            return {**self._job_status(job), "content": None}

        result = job.snapshot().get("result") or {}
        if result.get("kind") != "analysis":
            raise ValueError(
                f"job {job_id!r} is a {result.get('kind') or 'non-analysis'} job; "
                "use get_job_result for its output"
            )
        reports = result.get("reports") or {}
        if name == "complete":
            path = result.get("report_path")
            content = None
            if path and Path(path).is_file():
                content = Path(path).read_text(encoding="utf-8")
            if not content:
                content = self._assemble_report(result, reports)
        else:
            content = reports.get(name) or ""

        truncated = False
        if max_chars and max_chars > 0 and len(content) > max_chars:
            content = content[:max_chars] + "\n\n[truncated; raise max_chars for the rest]"
            truncated = True
        return {
            "job_id": job.id,
            "ticker": result.get("ticker"),
            "trade_date": result.get("trade_date"),
            "section": name,
            "content": content,
            "truncated": truncated,
            "report_path": result.get("report_path"),
        }

    def list_jobs(self, limit: int = 20, status: str | None = None) -> dict[str, Any]:
        """List this server process's recent jobs, newest first."""
        jobs = self.manager.list(limit=limit, status=status)
        return {
            "jobs": [self._job_status(job) for job in jobs],
            "counts": self.manager.stats(),
        }

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        """Request cancellation of a queued or running job.

        A running analysis stops between graph steps, so it may take a moment
        to reach cancelled.
        """
        job = self._get_job(job_id)
        return self._job_status(self.manager.cancel(job.id))

    def get_stock_data(self, ticker: str, start_date: str, end_date: str) -> str:
        """Retrieve OHLCV price data for a ticker over an inclusive date range.

        Dates are YYYY-MM-DD and cannot be in the future. Uses the configured
        core_stock_apis vendor (yfinance by default).
        """
        symbol = runners.normalize_ticker(ticker)
        start = runners.validate_date(start_date, "start_date")
        end = runners.validate_date(end_date, "end_date")
        if start > end:
            raise ValueError(f"end_date {end} is before start_date {start}")
        return route_to_vendor("get_stock_data", symbol, start, end)

    def get_technical_indicators(
        self,
        ticker: str,
        indicator: str,
        curr_date: str | None = None,
        look_back_days: int = 30,
    ) -> str:
        """Retrieve one or more technical indicators for a ticker.

        Pass indicators comma-separated, e.g. "rsi,macd,close_50_sma". The date
        defaults to today; look_back_days controls the trailing window.
        """
        symbol = runners.normalize_ticker(ticker)
        date = runners.validate_date(curr_date or get_current_date(), "curr_date")
        names = [part.strip().lower() for part in str(indicator).split(",") if part.strip()]
        if not names:
            raise ValueError("name at least one indicator")
        try:
            look_back = int(look_back_days)
        except (TypeError, ValueError):
            raise ValueError(f"look_back_days must be an integer, got {look_back_days!r}") from None
        if look_back < 1:
            raise ValueError("look_back_days must be at least 1")
        return "\n\n".join(
            route_to_vendor("get_indicators", symbol, name, date, look_back) for name in names
        )

    def get_fundamentals(self, ticker: str, curr_date: str | None = None) -> str:
        """Retrieve a company's fundamental overview as of curr_date (default today)."""
        symbol = runners.normalize_ticker(ticker)
        date = runners.validate_date(curr_date or get_current_date(), "curr_date")
        return route_to_vendor("get_fundamentals", symbol, date)

    def get_financial_statement(
        self,
        ticker: str,
        statement: str = "income_statement",
        freq: str = "quarterly",
        curr_date: str | None = None,
    ) -> str:
        """Retrieve one financial statement: balance_sheet, cashflow, or income_statement.

        freq is "quarterly" or "annual"; curr_date defaults to today.
        """
        methods = {
            "balance_sheet": "get_balance_sheet",
            "cashflow": "get_cashflow",
            "income_statement": "get_income_statement",
        }
        name = str(statement).strip().lower()
        if name not in methods:
            raise ValueError(f"statement must be one of {', '.join(methods)}, got {statement!r}")
        frequency = str(freq).strip().lower()
        if frequency not in {"annual", "quarterly"}:
            raise ValueError(f"freq must be annual or quarterly, got {freq!r}")
        symbol = runners.normalize_ticker(ticker)
        date = runners.validate_date(curr_date or get_current_date(), "curr_date")
        return route_to_vendor(methods[name], symbol, frequency, date)

    def get_news(self, ticker: str, start_date: str, end_date: str) -> str:
        """Retrieve company news published in an inclusive YYYY-MM-DD window."""
        symbol = runners.normalize_ticker(ticker)
        start = runners.validate_date(start_date, "start_date")
        end = runners.validate_date(end_date, "end_date")
        if start > end:
            raise ValueError(f"end_date {end} is before start_date {start}")
        return route_to_vendor("get_news", symbol, start, end)

    def get_global_news(
        self,
        curr_date: str | None = None,
        look_back_days: int | None = None,
        limit: int | None = None,
    ) -> str:
        """Retrieve global/macro headlines, optionally setting the lookback and article limit."""
        date = runners.validate_date(curr_date or get_current_date(), "curr_date")
        return route_to_vendor("get_global_news", date, look_back_days, limit)

    def get_insider_transactions(self, ticker: str) -> str:
        """Retrieve insider transaction filings for a ticker."""
        symbol = runners.normalize_ticker(ticker)
        return route_to_vendor("get_insider_transactions", symbol, None)

    def get_macro_indicators(
        self,
        indicator: str,
        curr_date: str | None = None,
        look_back_days: int | None = None,
    ) -> str:
        """Retrieve a FRED macroeconomic series by alias (e.g. cpi, unemployment) or series ID."""
        date = runners.validate_date(curr_date or get_current_date(), "curr_date")
        return route_to_vendor("get_macro_indicators", indicator, date, look_back_days)

    def get_prediction_markets(
        self,
        topic: str,
        limit: int | None = None,
        as_of_date: str | None = None,
    ) -> str:
        """Retrieve live Polymarket odds for an event topic (e.g. "Fed rate cut").

        Live odds have no historical vintage, so a past as_of_date withholds them.
        """
        date = runners.validate_date(as_of_date, "as_of_date") if as_of_date else None
        return route_to_vendor("get_prediction_markets", topic, limit, date)

    def _get_job(self, job_id: str) -> Job:
        try:
            return self.manager.get(job_id)
        except JobNotFound:
            raise ValueError(f"no job with id {job_id!r}") from None

    def _wait(self, job_id: str, wait_seconds: float) -> None:
        if wait_seconds and wait_seconds > 0:
            self.manager.wait(job_id, min(float(wait_seconds), _MAX_WAIT_SECONDS))

    def _job_status(self, job: Job) -> dict[str, Any]:
        data = job.snapshot()
        data.pop("result", None)
        return data

    def _job_summary(self, job: Job) -> dict[str, Any]:
        data = self._job_status(job)
        if job.status == "succeeded":
            result = job.snapshot().get("result") or {}
            for key in (
                "rating",
                "needs_review",
                "decision",
                "report_path",
                "html_path",
                "run_id",
                "summary",
                "cells_run",
                "skipped",
            ):
                if key in result:
                    data[key] = result[key]
        return data

    @staticmethod
    def _assemble_report(result: dict[str, Any], reports: dict[str, str]) -> str:
        lines = [f"# Trading Analysis Report: {result.get('ticker', '?')}", ""]
        if result.get("trade_date"):
            lines.append(f"- Analysis date: {result['trade_date']}")
        if result.get("rating"):
            lines.append(f"- Rating: {result['rating']}")
        lines.append("")
        for name in _SECTIONS[1:]:
            text = reports.get(name)
            if text:
                lines.extend([f"## {name.capitalize()}", "", text, ""])
        return "\n".join(lines)


def create_server(
    manager: JobManager | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    debug: bool = False,
    log_level: str = "INFO",
) -> FastMCP:
    """Build the FastMCP server; kept separate so tests can use a fake job manager."""
    return TradingAgentsMCPServer(
        manager=manager,
        host=host,
        port=port,
        debug=debug,
        log_level=log_level,
    ).server
