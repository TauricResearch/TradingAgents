"""The browser UI's HTTP server: static pages plus a small JSON API.

Standard library only. Pages are plain HTML/CSS/JS under ``static/``; every
number they show comes from the API below, which reads the same job registry
and on-disk history the CLI writes. Runs execute on worker threads (see
``jobs.py``), so a page reload or a second tab picks up where the first left off.

Bind to localhost unless you mean to share it: the API starts paid LLM runs and
accepts an API key for the session.
"""

from __future__ import annotations

import json
import mimetypes
import os
import threading
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from pydantic import ValidationError

from cli.main import _build_run_config
from cli.models import AssetType
from cli.prefs import load_last_run, save_last_run
from cli.utils import (
    _llm_provider_table,
    detect_asset_type,
    is_valid_ticker_input,
    normalize_ticker_symbol,
    resolve_backend_url,
)
from cli.webui.jobs import (
    SECTION_TITLES,
    TEAMS,
    AnalysisJob,
    BacktestJob,
    JobRegistry,
    backtest_summary,
    list_backtests,
    list_saved_reports,
    load_decisions,
    load_judgments,
    load_report_sections,
    report_rating,
)
from tradingagents.backtest import iter_grid
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.api_key_env import PROVIDER_API_KEY_ENV, get_api_key_env
from tradingagents.llm_clients.model_catalog import get_model_options
from tradingagents.portfolio import PortfolioContext

STATIC = Path(__file__).parent / "static"
PAGES = {"/": "landing.html", "/analyze": "app.html", "/sentiment": "app.html",
         "/reports": "app.html", "/backtest": "app.html"}

ANALYSTS = ["market", "social", "news", "fundamentals"]
DEPTHS = {"Shallow": 1, "Medium": 3, "Deep": 5}
LANGUAGES = ["English", "Chinese", "Japanese", "Korean", "Hindi", "Spanish", "Portuguese",
             "French", "German", "Arabic", "Russian"]
REGIONS = {  # provider -> China-mainland (key, url)
    "qwen": ("qwen-cn", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    "glm": ("glm-cn", "https://open.bigmodel.cn/api/paas/v4/"),
    "minimax": ("minimax-cn", "https://api.minimaxi.com/v1"),
}
EFFORTS = {  # provider -> (selection key, label, choices); "default" = provider default
    "openai": ("openai_reasoning_effort", "Reasoning effort", ["default", "medium", "high", "low"]),
    "anthropic": ("anthropic_effort", "Effort", ["default", "high", "medium", "low"]),
    "google": ("google_thinking_level", "Thinking", ["default", "high", "minimal"]),
}
PORTFOLIO_HELP = ('JSON like {"cash": 10000, "currency": "USD", "positions": '
                  '[{"ticker": "AAPL", "quantity": 20, "average_price": 180}]}')


class ApiError(Exception):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = status


# --- Model settings ---------------------------------------------------------

def _models(provider: str, mode: str) -> list[list[str]]:
    try:
        options = get_model_options(provider, mode)
    except KeyError:  # OpenRouter, Azure deployments, custom endpoints: free text
        return []
    return [[label, value] for label, value in options if value != "custom"]


def _key_status(provider: str) -> dict:
    from tradingagents.llm_clients.openai_client import OPENAI_COMPATIBLE_PROVIDERS

    env_var = get_api_key_env(provider)
    spec = OPENAI_COMPATIBLE_PROVIDERS.get(provider)
    if env_var is None or (spec is not None and spec.key_optional):
        note = "Uses the AWS credential chain" if provider == "bedrock" else "No API key needed"
        return {"env": None, "set": True, "note": note}
    return {"env": env_var, "set": bool(os.environ.get(env_var)), "note": ""}


def options() -> dict:
    """Everything the settings panel offers, with the remembered choices."""
    prefs = load_last_run()
    providers = []
    for name, key, url in _llm_provider_table():
        variants = [(key, url)] + ([REGIONS[key]] if key in REGIONS else [])
        for variant, variant_url in variants:
            effort = EFFORTS.get(variant)
            providers.append({
                "key": variant, "base": key, "name": name, "china": variant != key,
                "url": resolve_backend_url(variant, variant_url, env_url=DEFAULT_CONFIG["backend_url"]),
                "models": {"quick": _models(variant, "quick"), "deep": _models(variant, "deep")},
                "effort": effort and {"key": effort[0], "label": effort[1], "choices": effort[2],
                                      "default": DEFAULT_CONFIG.get(effort[0]) or "default"},
                "apiKey": _key_status(variant),
            })
    env_provider = os.environ.get("TRADINGAGENTS_LLM_PROVIDER") and DEFAULT_CONFIG["llm_provider"]
    provider = (env_provider or prefs.get("llm_provider") or DEFAULT_CONFIG["llm_provider"]).lower()
    remembered = prefs if prefs.get("llm_provider") == provider else {}
    if env_provider == provider:
        remembered = {"quick_think_llm": DEFAULT_CONFIG["quick_think_llm"],
                      "deep_think_llm": DEFAULT_CONFIG["deep_think_llm"]}
    return {
        "providers": providers,
        "depths": DEPTHS,
        "languages": LANGUAGES,
        "defaults": {
            "provider": provider,
            "quick": remembered.get("quick_think_llm") or "",
            "deep": remembered.get("deep_think_llm") or "",
            "depth": next((k for k, v in DEPTHS.items() if v == prefs.get("research_depth")),
                          "Shallow"),
            "language": prefs.get("output_language") or "English",
            "analysts": [a for a in prefs.get("analysts") or ANALYSTS if a in ANALYSTS],
            "checkpoint": bool(DEFAULT_CONFIG["checkpoint_enabled"]),
        },
        "resultsDir": str(DEFAULT_CONFIG["results_dir"]),
        "today": date.today().isoformat(),
        "portfolioHelp": PORTFOLIO_HELP,
    }


def set_api_key(body: dict) -> dict:
    env_var, value = body.get("env"), str(body.get("value") or "").strip()
    if env_var not in set(PROVIDER_API_KEY_ENV.values()):
        raise ApiError("Unknown API key variable.")
    if not value:
        raise ApiError("Paste the key first.")
    os.environ[env_var] = value  # this server's memory only
    return {"ok": True}


def _selections(settings: dict) -> dict:
    """CLI-shaped selections from the settings panel, validated like the CLI's."""
    provider = str(settings.get("provider") or "").lower()
    known = {p["key"]: p for p in options()["providers"]}
    if provider not in known:
        raise ApiError("Choose an LLM provider.")
    if not known[provider]["apiKey"]["set"]:
        raise ApiError(f"Set {known[provider]['apiKey']['env']} in the settings panel first.")
    quick, deep = (str(settings.get(k) or "").strip() for k in ("quick", "deep"))
    if not quick or not deep:
        raise ApiError("Choose both models in the settings panel first.")
    depth = settings.get("depth") if settings.get("depth") in DEPTHS else "Shallow"
    effort = {}
    if provider in EFFORTS:
        key, _, choices = EFFORTS[provider]
        value = settings.get("effort")
        effort[key] = value if value in choices and value != "default" else None
    backend_url = str(settings.get("backendUrl") or "").strip() or known[provider]["url"]
    return {
        "llm_provider": provider, "backend_url": backend_url or None,
        "quick_think_llm": quick, "deep_think_llm": deep,
        "research_depth": DEPTHS[depth],
        "output_language": str(settings.get("language") or "").strip() or "English",
        "google_thinking_level": None, "openai_reasoning_effort": None, "anthropic_effort": None,
        **effort,
    }


def _portfolio(value) -> PortfolioContext | None:
    if value in (None, ""):
        return None
    try:
        return PortfolioContext.model_validate(value)
    except ValidationError as exc:
        raise ApiError(f"That portfolio file is not usable: {exc}") from None


def _analysts(value, crypto: bool) -> list[str]:
    analysts = [a for a in ANALYSTS if a in set(value or [])]
    if crypto:
        analysts = [a for a in analysts if a != "fundamentals"]
    if not analysts:
        raise ApiError("Pick at least one analyst.")
    return analysts


# --- Analysis ---------------------------------------------------------------

def start_analysis(registry: JobRegistry, body: dict) -> dict:
    ticker = str(body.get("ticker") or "").strip()
    if not is_valid_ticker_input(ticker):
        raise ApiError("Tickers use letters, digits and . _ - ^ = only.")
    ticker = normalize_ticker_symbol(ticker or "SPY")
    trade_date = _date(body.get("date"), "Analysis date")
    if trade_date > date.today():
        raise ApiError("The analysis date cannot be in the future.")
    asset_type = detect_asset_type(ticker)
    analysts = _analysts(body.get("analysts"), asset_type == AssetType.CRYPTO)
    selections = _selections(body.get("settings") or {})
    portfolio = _portfolio(body.get("portfolio"))
    config = _build_run_config(selections, bool((body.get("settings") or {}).get("checkpoint")))
    save_last_run({**selections, "analysts": analysts})
    job = AnalysisJob(ticker, trade_date.isoformat(), asset_type.value, analysts, config, portfolio)
    registry.add(job.start())
    return {"id": job.id}


def _date(value, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ApiError(f"{label} must be a date.") from None


def analysis_list(registry: JobRegistry) -> list[dict]:
    return [{"id": j.id, "ticker": j.ticker, "date": j.trade_date, "status": j.status,
             "rating": j.rating} for j in registry.of_type(AnalysisJob)]


def analysis_detail(job: AnalysisJob) -> dict:
    snap = job.snapshot()
    activity = [{"time": t, "kind": kind, "detail": str(content)[:600]}
                for t, kind, content in snap["messages"]]
    activity += [{"time": t, "kind": "Tool", "detail": f"{name}({_args(args)})"}
                 for t, name, args in snap["tool_calls"]]
    activity.sort(key=lambda r: r["time"], reverse=True)
    report_path = snap["report_path"]
    return {
        "id": job.id, "ticker": job.ticker, "date": job.trade_date, "analysts": job.analysts,
        "status": snap["status"], "rating": snap["rating"],
        "error": snap["error"], "elapsed": snap["elapsed"], "stats": snap["stats"],
        "agents": snap["agent_status"],
        "teams": [[team, [a for a in agents if a in snap["agent_status"]]]
                  for team, agents in TEAMS.items()],
        "sections": [{"key": k, "title": SECTION_TITLES.get(k, k), "body": v}
                     for k, v in snap["sections"].items()],
        "activity": activity[:200],
        "reportDir": str(Path(report_path).parent) if report_path else None,
        "judgments": snap["judgments"],
    }


def _args(args) -> str:
    return ", ".join(f"{k}={v}" for k, v in args.items()) if isinstance(args, dict) else str(args)


# --- Saved reports and decision logs -----------------------------------------

def _report_id(report) -> str:
    return report.path.relative_to(Path(DEFAULT_CONFIG["results_dir"])).as_posix()


def _find_report(report_id: str):
    """A saved report by id; only paths the listing produced are ever opened."""
    for report in list_saved_reports(DEFAULT_CONFIG["results_dir"]):
        if _report_id(report) == report_id:
            return report
    raise ApiError("No such report.", HTTPStatus.NOT_FOUND)


def reports_list() -> list[dict]:
    out = []
    for r in list_saved_reports(DEFAULT_CONFIG["results_dir"]):
        try:
            rating = report_rating(load_report_sections(r))
        except (OSError, ValueError):
            rating = None
        out.append({"id": _report_id(r), "ticker": r.ticker, "date": r.trade_date,
                    "modified": r.modified.strftime("%Y-%m-%d %H:%M"), "kind": r.kind,
                    "rating": rating, "hasJudgments": r.judgments_path is not None})
    return out


def report_detail(report_id: str) -> dict:
    report = _find_report(report_id)
    sections = load_report_sections(report)
    return {"id": report_id, "ticker": report.ticker, "date": report.trade_date,
            "modified": report.modified.strftime("%Y-%m-%d %H:%M"), "kind": report.kind,
            "path": str(report.path), "rating": report_rating(sections),
            "sections": [{"title": t, "body": b} for t, b in sections],
            "hasJudgments": report.judgments_path is not None}


def _log_path(run: str | None) -> Path:
    if not run:
        return Path(DEFAULT_CONFIG["memory_log_path"])
    for path in list_backtests(DEFAULT_CONFIG):
        if path.name == run:
            return path / "trading_memory.md"
    raise ApiError("No such backtest run.", HTTPStatus.NOT_FOUND)


def decisions(run: str | None) -> list[dict]:
    return list(reversed(load_decisions(_log_path(run))))


# --- Backtests ----------------------------------------------------------------

def start_backtest(registry: JobRegistry, body: dict) -> dict:
    names = [normalize_ticker_symbol(t.strip())
             for t in str(body.get("tickers") or "").split(",") if t.strip()]
    if not names or not all(is_valid_ticker_input(t) for t in names):
        raise ApiError("Enter comma-separated tickers, e.g. NVDA,AAPL.")
    asset_type = "crypto" if body.get("assetType") == "crypto" else "stock"
    analysts = _analysts(body.get("analysts"), asset_type == "crypto")
    start, end = _date(body.get("from"), "From"), _date(body.get("to"), "To")
    try:
        every = int(body.get("every") or 1)
        dates = iter_grid(start.isoformat(), end.isoformat(), every)
    except (TypeError, ValueError) as exc:
        raise ApiError(str(exc)) from None
    portfolio = _portfolio(body.get("portfolio"))
    selections = _selections(body.get("settings") or {})
    config = _build_run_config(selections, bool((body.get("settings") or {}).get("checkpoint")))
    run_id = str(body.get("runId") or "").strip()
    try:
        job = BacktestJob(names, dates, config, analysts, asset_type, portfolio,
                          **({"run_id": run_id} if run_id else {}))
    except ValueError as exc:
        raise ApiError(str(exc)) from None
    if (existing := registry.get(job.id)) is not None and existing.active:
        raise ApiError(f"Backtest {job.run_id} is already running.")
    registry.add(job.start())
    return {"id": job.id, "runId": job.run_id}


def backtest_jobs(registry: JobRegistry) -> list[dict]:
    out = []
    for job in registry.of_type(BacktestJob):
        logged = min(job.cells_logged(), job.total_cells)
        result = job.result
        out.append({
            "id": job.id, "runId": job.run_id, "tickers": job.tickers, "status": job.status,
            "stopping": job.stopping, "total": job.total_cells, "logged": logged,
            "cellsDone": max(0, logged - job.initial_logged),
            "elapsed": job.elapsed(), "current": list(job.current) if job.current else None,
            "error": job.error,
            "cellsRun": result.cells_run if result else None,
            "skipped": result.skipped if result else None,
            "failures": [list(f) for f in result.failures] if result else [],
            "settlementFailures": [list(f) for f in result.settlement_failures] if result else [],
        })
    return out


def backtest_runs() -> list[str]:
    return [p.name for p in list_backtests(DEFAULT_CONFIG)]


def backtest_detail(run: str) -> dict:
    log_path = _log_path(run)
    summary = backtest_summary(log_path)
    order = ["Buy", "Overweight", "Hold", "Underweight", "Sell"]
    scores = sorted(summary.by_rating.items(), key=lambda kv: order.index(kv[0])
                    if kv[0] in order else 99)
    return {
        "run": run, "resolved": summary.resolved, "pending": summary.pending,
        "unscored": summary.unscored, "holding": summary.holding,
        "byRating": [{"rating": r, "count": s.count, "hitRate": s.hit_rate,
                      "meanAlpha": s.mean_alpha} for r, s in scores],
        "cells": list(reversed(load_decisions(log_path))),
    }


# --- HTTP -----------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "TradingAgentsUI"
    registry: JobRegistry  # set by make_server

    def log_message(self, format, *args):  # noqa: A002 — the stdlib's signature
        pass  # the terminal belongs to the runs' own logging

    # GET -----------------------------------------------------------------
    def do_GET(self):
        url = urlsplit(self.path)
        path, query = url.path.rstrip("/") or "/", parse_qs(url.query)
        try:
            if path in PAGES:
                return self._file(STATIC / PAGES[path])
            if path.startswith("/static/"):
                return self._static(path.removeprefix("/static/"))
            if path.startswith("/api/"):
                return self._get_api(path.removeprefix("/api"), query)
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except ApiError as exc:
            self._send_json({"error": str(exc)}, exc.status)
        except Exception as exc:  # noqa: BLE001 — one bad request must not stop the server
            self._send_json({"error": f"{type(exc).__name__}: {exc}"},
                            HTTPStatus.INTERNAL_SERVER_ERROR)

    def _get_api(self, path: str, query: dict):
        q = {k: v[0] for k, v in query.items()}
        registry = self.registry
        parts = path.strip("/").split("/")
        match parts:
            case ["options"]:
                return self._send_json(options())
            case ["analyses"]:
                return self._send_json(analysis_list(registry))
            case ["analyses", job_id]:
                return self._send_json(analysis_detail(self._analysis(job_id)))
            case ["analyses", job_id, "report.md"]:
                job = self._analysis(job_id)
                if job.report_path is None or not Path(job.report_path).exists():
                    raise ApiError("This run has no saved report yet.", HTTPStatus.NOT_FOUND)
                return self._download(Path(job.report_path),
                                      f"{job.ticker}_{job.trade_date}.md")
            case ["reports"]:
                return self._send_json(reports_list())
            case ["report"]:
                return self._send_json(report_detail(q.get("id", "")))
            case ["report", "judgments"]:
                judgments = load_judgments(_find_report(q.get("id", "")))
                if judgments is None:
                    raise ApiError("This report has no Jev judgments.", HTTPStatus.NOT_FOUND)
                return self._send_json(judgments)
            case ["report", "download"]:
                report = _find_report(q.get("id", ""))
                return self._download(report.path, f"{report.ticker}_{report.path.parent.name}"
                                      + report.path.suffix)
            case ["decisions"]:
                return self._send_json(decisions(q.get("run")))
            case ["backtests"]:
                return self._send_json({"runs": backtest_runs(), "jobs": backtest_jobs(registry)})
            case ["backtests", run]:
                return self._send_json(backtest_detail(unquote(run)))
        raise ApiError("Not found", HTTPStatus.NOT_FOUND)

    def _analysis(self, job_id: str) -> AnalysisJob:
        job = self.registry.get(job_id)
        if not isinstance(job, AnalysisJob):
            raise ApiError("No such run. Runs are kept in memory until the server stops.",
                           HTTPStatus.NOT_FOUND)
        return job

    # POST ----------------------------------------------------------------
    def do_POST(self):
        path = urlsplit(self.path).path.rstrip("/")
        try:
            # A page on another origin cannot read these responses, but it could
            # still start a paid run; only this server's own pages may post.
            origin = self.headers.get("Origin")
            if origin and origin.split("://", 1)[-1] != self.headers.get("Host"):
                raise ApiError("Cross-origin request refused.", HTTPStatus.FORBIDDEN)
            body = self._body()
            registry = self.registry
            match path.strip("/").split("/"):
                case ["api", "key"]:
                    return self._send_json(set_api_key(body))
                case ["api", "analyses"]:
                    return self._send_json(start_analysis(registry, body), HTTPStatus.CREATED)
                case ["api", "analyses", job_id, "stop"]:
                    self._analysis(job_id).cancel()
                    return self._send_json({"ok": True})
                case ["api", "backtests"]:
                    return self._send_json(start_backtest(registry, body), HTTPStatus.CREATED)
                case ["api", "backtests", job_id, "stop"]:
                    job = registry.get(job_id)
                    if not isinstance(job, BacktestJob):
                        raise ApiError("No such backtest.", HTTPStatus.NOT_FOUND)
                    job.cancel()
                    return self._send_json({"ok": True})
            raise ApiError("Not found", HTTPStatus.NOT_FOUND)
        except ApiError as exc:
            self._send_json({"error": str(exc)}, exc.status)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": f"{type(exc).__name__}: {exc}"},
                            HTTPStatus.INTERNAL_SERVER_ERROR)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 5_000_000:
            raise ApiError("Request too large.", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            raise ApiError("Request body is not JSON.") from None
        if not isinstance(body, dict):
            raise ApiError("Request body must be a JSON object.")
        return body

    # Responses -------------------------------------------------------------
    def _send(self, data: bytes, content_type: str, status=HTTPStatus.OK, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload, status=HTTPStatus.OK):
        data = json.dumps(payload, default=str).encode("utf-8")
        self._send(data, "application/json; charset=utf-8", status)

    def _file(self, path: Path):
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type.endswith("javascript"):
            content_type += "; charset=utf-8"
        self._send(path.read_bytes(), content_type)

    def _static(self, name: str):
        path = (STATIC / name).resolve()
        if STATIC.resolve() not in path.parents or not path.is_file():
            raise ApiError("Not found", HTTPStatus.NOT_FOUND)
        self._file(path)

    def _download(self, path: Path, filename: str):
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
        kind = "application/json" if path.suffix == ".json" else "text/markdown"
        self._send(path.read_bytes(), f"{kind}; charset=utf-8",
                   headers={"Content-Disposition": f'attachment; filename="{safe}"'})


def make_server(host: str = "127.0.0.1", port: int = 8501,
                registry: JobRegistry | None = None) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"registry": registry or JobRegistry()})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def serve(host: str, port: int, open_browser: bool = True) -> None:
    server = make_server(host, port)
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0', '::') else host}:{port}"
    print(f"TradingAgents UI on {url}  (Ctrl+C to stop)")
    if open_browser:
        import webbrowser

        threading.Timer(0.5, webbrowser.open, [url + "/analyze"]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

