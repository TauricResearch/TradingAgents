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

from cli.models import AssetType
from cli.prefs import load_last_run, save_last_run
from cli.prompts import (
    _llm_provider_table,
    detect_asset_type,
    is_valid_ticker_input,
    normalize_ticker_symbol,
    resolve_backend_url,
)
from cli.run import _build_run_config
from cli.webui.jobs import (
    SECTION_TITLES,
    TEAMS,
    AnalysisJob,
    AnalysisQueue,
    BacktestJob,
    JobRegistry,
    QueueFull,
    backtest_summary,
    list_backtests,
    list_saved_reports,
    load_decisions,
    load_judgments,
    load_report_sections,
    report_rating,
)
from cli.webui.ticker_search import search_tickers
from tradingagents.backtest import iter_grid
from tradingagents.dataflows.errors import NoMarketDataError, VendorError, VendorRateLimitError
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.api_key_env import PROVIDER_API_KEY_ENV, get_api_key_env
from tradingagents.llm_clients.model_catalog import get_model_options
from tradingagents.portfolio import PortfolioContext

STATIC = Path(__file__).parent / "static"
PAGES = {"/": "landing.html", "/analyze": "app.html", "/sentiment": "app.html",
         "/company": "app.html", "/screens": "app.html", "/reports": "app.html", "/backtest": "app.html",
         "/industry": "app.html", "/watchlists": "app.html", "/alerts": "app.html"}
MAX_QUEUED_PICKS = 10  # stocks one "Analyze with agents" may queue from the Screens page

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
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST, **extra):
        super().__init__(message)
        self.status = status
        self.extra = extra  # more fields for the JSON body (error spans, a setup hint)


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

def _analysis_jobs(body: dict, tickers: list[str]) -> list[AnalysisJob]:
    """One validated AnalysisJob per ticker, all on the body's date and settings."""
    for ticker in tickers:
        if not is_valid_ticker_input(ticker):
            raise ApiError("Tickers use letters, digits and . _ - ^ = only.")
    trade_date = _date(body.get("date"), "Analysis date")
    if trade_date > date.today():
        raise ApiError("The analysis date cannot be in the future.")
    picks = []
    for raw in tickers:
        ticker = normalize_ticker_symbol(raw or "SPY")
        asset_type = detect_asset_type(ticker)
        picks.append((ticker, asset_type, _analysts(body.get("analysts"), asset_type == AssetType.CRYPTO)))
    selections = _selections(body.get("settings") or {})
    portfolio = _portfolio(body.get("portfolio"))
    config = _build_run_config(selections, bool((body.get("settings") or {}).get("checkpoint")))
    save_last_run({**selections, "analysts": picks[0][2]})
    return [AnalysisJob(ticker, trade_date.isoformat(), asset_type.value, analysts, config, portfolio)
            for ticker, asset_type, analysts in picks]


def start_analysis(registry: JobRegistry, body: dict) -> dict:
    [job] = _analysis_jobs(body, [str(body.get("ticker") or "").strip()])
    registry.add(job.start())
    return {"id": job.id}


def queue_analyses(queue: AnalysisQueue, body: dict) -> dict:
    """Queue one analysis per picked stock; they run one after another."""
    tickers = body.get("tickers")
    if not isinstance(tickers, list) or not tickers or not all(isinstance(t, str) and t.strip() for t in tickers):
        raise ApiError("Pick at least one stock to analyze.")
    tickers = list(dict.fromkeys(t.strip() for t in tickers))
    if len(tickers) > MAX_QUEUED_PICKS:
        raise ApiError(f"Pick at most {MAX_QUEUED_PICKS} stocks at a time; each one is a full, paid run.")
    jobs = _analysis_jobs(body, tickers)
    try:
        ids = queue.submit(jobs)
    except QueueFull as exc:
        raise ApiError(str(exc), HTTPStatus.CONFLICT) from None
    return {"ids": ids, "queue": queue.status()}


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


# --- Company page -------------------------------------------------------------

def company(symbol: str, basis: str | None = None) -> dict:
    """One stock's fundamentals as known today: Yahoo Finance, with the India
    database's filings over it for Indian stocks it has. A live view only: the agents
    and backtests never read it, since it is not cut at any analysis date."""
    from tradingagents.dataflows.vendors.india.profile import build_company_profile

    symbol = symbol.strip()
    if not symbol:
        raise ApiError("Enter a symbol or company name, e.g. RELIANCE.NS or AAPL.")
    if not is_valid_ticker_input(symbol):
        raise ApiError("Tickers use letters, digits and . _ - ^ = only.")
    if basis not in (None, "", "standalone", "consolidated"):
        raise ApiError("basis is standalone or consolidated.")
    try:
        return build_company_profile(symbol, basis or None)
    except NoMarketDataError:
        raise ApiError(f"Yahoo Finance has no data for {symbol.upper()}. Indian stocks need "
                       "their exchange suffix: .NS for NSE or .BO for BSE.",
                       HTTPStatus.NOT_FOUND) from None
    except VendorRateLimitError as exc:
        raise ApiError(f"{exc}. Try again in a minute.", HTTPStatus.SERVICE_UNAVAILABLE) from None
    except VendorError as exc:
        raise ApiError(str(exc), HTTPStatus.BAD_GATEWAY) from None


# --- Screens ------------------------------------------------------------------

def _screener_errors(fn):
    """Screener failures as API errors: a query's span, or what to run when the
    India database or its snapshot is missing. Never a 500 for those."""
    from tradingagents.screener.alerts import AlertError
    from tradingagents.screener.engine import ScreenerUnavailable, ScreenTimeout
    from tradingagents.screener.peers import IndustryNotFound, PeersUnavailable
    from tradingagents.screener.query import QueryError
    from tradingagents.screener.screens import ScreenError
    from tradingagents.screener.snapshot import SnapshotError
    from tradingagents.screener.watchlists import WatchlistError

    try:
        return fn()
    except QueryError as exc:
        raise ApiError(str(exc), errors=[exc.to_dict()]) from None
    except ScreenError as exc:
        raise ApiError(str(exc), errors=exc.errors) from None
    except AlertError as exc:
        status = HTTPStatus.NOT_FOUND if str(exc).startswith("No such") else HTTPStatus.BAD_REQUEST
        raise ApiError(str(exc), status, errors=exc.errors) from None
    except WatchlistError as exc:
        status = HTTPStatus.NOT_FOUND if str(exc).startswith("No such") else HTTPStatus.BAD_REQUEST
        raise ApiError(str(exc), status) from None
    except IndustryNotFound as exc:
        raise ApiError(str(exc), HTTPStatus.NOT_FOUND) from None
    except (ScreenerUnavailable, SnapshotError, PeersUnavailable) as exc:
        raise ApiError(str(exc), HTTPStatus.SERVICE_UNAVAILABLE, setup=True) from None
    except ScreenTimeout as exc:
        raise ApiError(str(exc), HTTPStatus.REQUEST_TIMEOUT) from None


def _with_user_store(work):
    """``work(conn)`` on the saved-screens database, closed afterwards."""
    from tradingagents.screener import screens

    conn = screens.connect()
    try:
        return _screener_errors(lambda: work(conn))
    finally:
        conn.close()


def screen_metrics() -> dict:
    from tradingagents.dataflows.vendors.india import store
    from tradingagents.screener import engine

    india = store.open_existing()
    try:
        return _with_user_store(lambda user: engine.metrics_payload(user, india))
    finally:
        if india is not None:
            india.close()


def screen_validate(body: dict) -> dict:
    from tradingagents.screener import engine

    return _with_user_store(lambda user: engine.validate(str(body.get("query") or ""), user))


def screen_run(body: dict) -> dict:
    from tradingagents.screener import engine

    query = body.get("query")
    if not isinstance(query, str):
        raise ApiError("Send the screen's query as text.")
    try:
        page = int(body.get("page") or 1)
        page_size = int(body.get("pageSize") or engine.PAGE_SIZE)
    except (TypeError, ValueError):
        raise ApiError("page and pageSize are numbers.") from None
    return _with_user_store(lambda user: engine.run(
        query, columns=body.get("columns") or None, sort=body.get("sort") or None, page=page,
        page_size=page_size, as_of=body.get("as_of") or body.get("asOf"), user_conn=user))


def screens_list() -> dict:
    from tradingagents.screener import screens

    return _with_user_store(lambda user: {"presets": screens.presets(), "saved": screens.list_screens(user)})


def screen_save(body: dict) -> dict:
    from tradingagents.screener import screens

    return _with_user_store(lambda user: screens.save_screen(user, body, screens.list_ratios(user)))


def screen_delete(screen_id: str) -> dict:
    from tradingagents.screener import screens

    if not (screen_id.isdigit() or screen_id.startswith("preset:")):
        raise ApiError("No such screen.", HTTPStatus.NOT_FOUND)
    _with_user_store(lambda user: screens.delete_screen(user, screen_id))
    return {"ok": True}


def ratios_list() -> list[dict]:
    from tradingagents.screener import screens

    return _with_user_store(lambda user: [r.describe() for r in screens.list_ratios(user)])


def ratio_save(body: dict) -> dict:
    from tradingagents.screener import screens

    return _with_user_store(lambda user: screens.save_ratio(user, body).describe())


def ratio_delete(ratio_id: str) -> dict:
    from tradingagents.screener import screens

    if not ratio_id.isdigit():
        raise ApiError("No such custom ratio.", HTTPStatus.NOT_FOUND)
    _with_user_store(lambda user: screens.delete_ratio(user, int(ratio_id)))
    return {"ok": True}


# --- Peers, industries, watchlists, alerts and exports ----------------------
# The engine is in tradingagents/screener (peers, watchlists, alerts, export);
# these wrap it for HTTP. Tables share engine.run's layout, so the page draws
# every one of them with the same component.

def _columns(value) -> list[str] | None:
    """``a,b,c`` from a query string, or a JSON body's list."""
    if value in (None, ""):
        return None
    if isinstance(value, list):
        return [str(v) for v in value]
    return [c for c in str(value).split(",") if c]


def _sort(value) -> dict | None:
    """``key:asc`` from a query string, or a JSON body's dict."""
    if value in (None, ""):
        return None
    if isinstance(value, dict):
        return value
    key, _, direction = str(value).partition(":")
    return {"key": key, "dir": direction or "desc"}


def _int(value, label: str, default: int) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        raise ApiError(f"{label} is a number.") from None


def _india_or_setup():
    """The India database, read-only, or a 503 naming the command that fills it."""
    from tradingagents.dataflows.vendors.india import store

    conn = store.open_existing()
    if conn is None:
        raise ApiError(f"There is no India database yet at {store.db_path()}. Fill it with: "
                       "python -m cli.main india sync-all", HTTPStatus.SERVICE_UNAVAILABLE, setup=True)
    return conn


def peers_api(q: dict) -> dict:
    """A company's peers; with no snapshot or no industry, ``available: false`` and a
    note naming the command to run, so the Company page hides the section."""
    from tradingagents.screener import peers

    symbol = q.get("symbol", "").strip()
    if not symbol or not is_valid_ticker_input(symbol):
        raise ApiError("Give a symbol, e.g. RELIANCE.NS.")
    try:
        return _with_user_store(lambda user: peers.peers(symbol, columns=_columns(q.get("columns")),
                                                         sort=_sort(q.get("sort")), user_conn=user))
    except ApiError as exc:
        if exc.status == HTTPStatus.SERVICE_UNAVAILABLE:
            return {"available": False, "note": str(exc)}
        raise


def industries_api() -> list[dict]:
    from tradingagents.screener import peers

    return _with_user_store(lambda user: peers.industries())


def industry_api(q: dict) -> dict:
    from tradingagents.screener import peers

    name = q.get("name", "").strip()
    if not name:
        raise ApiError("Give an industry's name.")
    return _with_user_store(lambda user: peers.industry(
        name, columns=_columns(q.get("columns")), sort=_sort(q.get("sort")), page=_int(q.get("page"), "page", 1),
        user_conn=user))


def watchlists_list() -> list[dict]:
    from tradingagents.screener import watchlists

    return _with_user_store(watchlists.list_watchlists)


def watchlist_table(watchlist_id: str, q: dict) -> dict:
    from tradingagents.dataflows.vendors.india import store
    from tradingagents.screener import watchlists

    india = store.open_existing()
    try:
        return _with_user_store(lambda user: watchlists.table(user, watchlist_id, india,
                                                              columns=_columns(q.get("columns")),
                                                              sort=_sort(q.get("sort"))))
    finally:
        if india is not None:
            india.close()


def watchlist_portfolio(watchlist_id: str) -> dict:
    """The holdings as a portfolio JSON, the shape a portfolio file has; the Analyze
    page sends it with a run the way it sends a file's."""
    from tradingagents.screener import watchlists

    return _with_user_store(lambda user: watchlists.portfolio(user, watchlist_id).model_dump())


def watchlist_save(body: dict) -> dict:
    from tradingagents.screener import watchlists

    return _with_user_store(lambda user: watchlists.save(user, body))


def watchlist_change(watchlist_id: str, action: str, body: dict):
    """Adding, removing, importing or updating a watchlist's stocks."""
    from tradingagents.screener import watchlists

    if action in ("items", "import"):
        india = _india_or_setup()
        try:
            if action == "items":
                return _with_user_store(lambda user: watchlists.add(user, watchlist_id, body.get("symbols"), india))
            return _with_user_store(lambda user: watchlists.import_csv(user, watchlist_id, body.get("csv"), india))
        finally:
            india.close()
    if action == "remove":
        return {"removed": _with_user_store(lambda user: watchlists.remove(user, watchlist_id, body.get("symbols")))}
    if action == "update":
        return _with_user_store(lambda user: watchlists.update_item(user, watchlist_id, str(body.get("symbol") or ""),
                                                                    {k: body[k] for k in ("note", "quantity",
                                                                                          "avgPrice") if k in body}))
    if action == "delete":
        _with_user_store(lambda user: watchlists.delete(user, watchlist_id))
        return {"ok": True}
    raise ApiError("Not found", HTTPStatus.NOT_FOUND)


def alerts_overview(poller) -> dict:
    from tradingagents.screener import alerts, delivery

    def work(user):
        return {"alerts": alerts.list_alerts(user), "unread": alerts.unread(user), "channels": delivery.status(),
                "poller": poller.status() if poller is not None else {
                    "enabled": False, "note": "Off. Set TRADINGAGENTS_ALERT_POLL_MINUTES (5 or more) to check price "
                                              "alerts on Yahoo's delayed quotes during market hours."},
                "kinds": list(alerts.KINDS), "filingKinds": list(alerts.FILING_KINDS)}
    return _with_user_store(work)


def alert_save(body: dict) -> dict:
    from tradingagents.dataflows.vendors.india import store
    from tradingagents.screener import alerts

    india = store.open_existing()
    try:
        return _with_user_store(lambda user: alerts.save(user, body, india))
    finally:
        if india is not None:
            india.close()


def alerts_evaluate(body: dict) -> dict:
    from tradingagents.screener import alerts

    ids = body.get("ids")
    if ids is not None and (not isinstance(ids, list) or not all(isinstance(i, int) for i in ids)):
        raise ApiError("ids is a list of alert ids.")

    def work(user):
        result = alerts.evaluate(user, alert_ids=ids)
        return {"evaluated": result.evaluated, "fired": len(result.fired), "suppressed": result.suppressed,
                "skipped": result.skipped, "errors": result.errors, "unread": alerts.unread(user)}
    return _with_user_store(work)


def channel_test(name: str) -> dict:
    from tradingagents.screener import delivery

    if name not in delivery.CHANNELS:
        raise ApiError("No such channel.", HTTPStatus.NOT_FOUND)
    if not delivery.configured(name):
        raise ApiError(f"{delivery.CHANNELS[name]['label']} is not configured: set its TRADINGAGENTS_ALERT_* "
                       "variables and restart the server.")
    return delivery.send_test(name)


def _export_table(kind: str, ext: str, q: dict) -> tuple[bytes, str, str]:
    """A table of stocks as CSV or XLSX: (data, file name, content type)."""
    from tradingagents.dataflows.vendors.india import store
    from tradingagents.screener import engine, export, peers, watchlists

    columns, sort = _columns(q.get("columns")), _sort(q.get("sort"))
    extras, query, stem = (), None, kind
    if kind == "screen":
        query = q.get("query", "")
        if not query.strip():
            raise ApiError("Send the screen's query.")
        result = _with_user_store(lambda user: engine.run(
            query, columns=columns, sort=sort, as_of=q.get("as_of") or None, page_size=export.MAX_ROWS,
            max_page_size=export.MAX_ROWS, user_conn=user))
        stem, what = f"screen_{q.get('name') or 'untitled'}", f"Screen: {q.get('name') or 'untitled'}"
        kind = "results"
    elif kind == "peers":
        result = peers_api(q)
        if not result.get("available"):
            raise ApiError(result["note"], HTTPStatus.SERVICE_UNAVAILABLE, setup=True)
        stem, what = q.get("symbol", "").split(".")[0], f"Peers of {q.get('symbol')} ({result['industry']})"
        kind = "peers"
    elif kind == "industry":
        result = _with_user_store(lambda user: peers.industry(
            q.get("name", ""), columns=columns, sort=sort, page_size=export.MAX_ROWS, max_page_size=export.MAX_ROWS,
            user_conn=user))
        stem, what, query = f"industry_{result['industry']}", f"Industry: {result['industry']}", result["query"]
        kind = "stocks"
    else:  # watchlist
        india = store.open_existing()
        try:
            result = _with_user_store(lambda user: watchlists.table(user, q.get("id"), india, columns=columns,
                                                                    sort=sort))
        finally:
            if india is not None:
                india.close()
        extras = export.WATCHLIST_COLUMNS + (export.HOLDING_COLUMNS if result["watchlist"]["holdings"] else ())
        stem, what = f"watchlist_{result['watchlist']['name']}", f"Watchlist: {result['watchlist']['name']}"
        kind = "stocks"
    header, rows = export.table_rows(result, extras)
    name = export.file_name(stem, kind, ext)
    if ext == "csv":
        return export.csv_bytes(header, rows), name, export.CSV_TYPE
    notes = export.table_notes(result, what=what, query=query)
    return export.table_workbook(what, "Stocks", header, rows, notes), name, export.XLSX_TYPE


def _export_company(q: dict) -> tuple[bytes, str, str]:
    from tradingagents.screener import export

    symbol = q.get("symbol", "").strip()
    profile = company(symbol, q.get("basis"))
    peer_table, note = None, None
    if profile.get("india"):
        found = peers_api({"symbol": profile["symbol"]})
        peer_table, note = (found, None) if found.get("available") else (None, found.get("note"))
    else:
        note = "Peers come from the India database's snapshot, which covers Indian stocks only."
    data = export.company_workbook(profile, peer_table, note)
    stem = profile["symbol"].removesuffix(".NS")
    return data, export.file_name(stem, "financials", "xlsx"), export.XLSX_TYPE


def export_file(what: str, q: dict) -> tuple[bytes, str, str]:
    kind, _, ext = what.partition(".")
    if kind == "company" and ext == "xlsx":
        return _export_company(q)
    if kind in ("screen", "peers", "industry", "watchlist") and ext in ("csv", "xlsx"):
        return _export_table(kind, ext, q)
    raise ApiError("Exports are company.xlsx, or screen, peers, industry or watchlist as .csv or .xlsx.",
                   HTTPStatus.NOT_FOUND)


def watchlist_symbols_csv(watchlist_id: str) -> tuple[bytes, str]:
    from tradingagents.screener import export, watchlists

    def work(user):
        header, rows = watchlists.csv_rows(user, watchlist_id)
        name = watchlists.get(user, watchlist_id)["name"]
        return export.csv_bytes(header, rows), export.file_name(f"watchlist_{name}", "symbols", "csv")
    return _with_user_store(work)


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
    queue: AnalysisQueue  # set by make_server
    poller = None  # the alerts' delayed-quote PricePoller, when TRADINGAGENTS_ALERT_POLL_MINUTES turns it on

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
            self._send_json({"error": str(exc), **exc.extra}, exc.status)
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
            case ["tickers"]:
                return self._send_json(search_tickers(q.get("q", "")))
            case ["company"]:
                return self._send_json(company(q.get("symbol", ""), q.get("basis")))
            case ["screen", "metrics"]:
                return self._send_json(screen_metrics())
            case ["screens"]:
                return self._send_json(screens_list())
            case ["ratios"]:
                return self._send_json(ratios_list())
            case ["queue"]:
                return self._send_json(self.queue.status())
            case ["peers"]:
                return self._send_json(peers_api(q))
            case ["industries"]:
                return self._send_json(industries_api())
            case ["industry"]:
                return self._send_json(industry_api(q))
            case ["watchlists"]:
                return self._send_json(watchlists_list())
            case ["watchlists", watchlist_id]:
                return self._send_json(watchlist_table(watchlist_id, q))
            case ["watchlists", watchlist_id, "portfolio"]:
                return self._send_json(watchlist_portfolio(watchlist_id))
            case ["watchlists", watchlist_id, "symbols.csv"]:
                data, name = watchlist_symbols_csv(watchlist_id)
                return self._download(data, name, "text/csv; charset=utf-8")
            case ["alerts"]:
                return self._send_json(alerts_overview(self.poller))
            case ["alerts", "inbox"]:
                from tradingagents.screener import alerts

                return self._send_json(_with_user_store(lambda user: alerts.inbox(
                    user, unread_only=q.get("unread") in ("1", "true"), alert_id=q.get("alert"),
                    limit=_int(q.get("limit"), "limit", 200))))
            case ["alerts", "unread"]:
                from tradingagents.screener import alerts

                return self._send_json({"unread": _with_user_store(alerts.unread)})
            case ["export", what]:
                data, name, kind = export_file(what, q)
                return self._download(data, name, kind)
            case ["export", "watchlist", file]:
                watchlist_id, _, ext = file.partition(".")
                data, name, kind = export_file(f"watchlist.{ext}", {**q, "id": watchlist_id})
                return self._download(data, name, kind)
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
                self._drain()  # unread, the body turns the refusal into a connection reset on Windows
                raise ApiError("Cross-origin request refused.", HTTPStatus.FORBIDDEN)
            body = self._body()
            registry = self.registry
            match path.strip("/").split("/"):
                case ["api", "key"]:
                    return self._send_json(set_api_key(body))
                case ["api", "analyses"]:
                    return self._send_json(start_analysis(registry, body), HTTPStatus.CREATED)
                case ["api", "analyses", job_id, "stop"]:
                    job = self._analysis(job_id)
                    if not self.queue.cancel(job_id):
                        job.cancel()
                    return self._send_json({"ok": True})
                case ["api", "screen", "validate"]:
                    return self._send_json(screen_validate(body))
                case ["api", "screen", "run"]:
                    return self._send_json(screen_run(body))
                case ["api", "screen", "analyze"]:
                    return self._send_json(queue_analyses(self.queue, body), HTTPStatus.CREATED)
                case ["api", "screens"]:
                    return self._send_json(screen_save(body))
                case ["api", "screens", screen_id, "delete"]:
                    return self._send_json(screen_delete(unquote(screen_id)))
                case ["api", "ratios"]:
                    return self._send_json(ratio_save(body))
                case ["api", "ratios", ratio_id, "delete"]:
                    return self._send_json(ratio_delete(ratio_id))
                case ["api", "watchlists"]:
                    return self._send_json(watchlist_save(body))
                case ["api", "watchlists", "order"]:
                    from tradingagents.screener import watchlists

                    return self._send_json(_with_user_store(lambda user: watchlists.reorder(user, body.get("ids"))))
                case ["api", "watchlists", watchlist_id, action]:
                    return self._send_json(watchlist_change(watchlist_id, action, body))
                case ["api", "watchlists", watchlist_id, "items", action]:
                    return self._send_json(watchlist_change(watchlist_id, action, body))
                case ["api", "alerts"]:
                    return self._send_json(alert_save(body))
                case ["api", "alerts", "evaluate"]:
                    return self._send_json(alerts_evaluate(body))
                case ["api", "alerts", "inbox", "read"]:
                    from tradingagents.screener import alerts

                    n = _with_user_store(lambda user: alerts.mark_read(user, body.get("ids"), body.get("read", True)))
                    return self._send_json({"changed": n, "unread": _with_user_store(alerts.unread)})
                case ["api", "alerts", "inbox", "delete"]:
                    from tradingagents.screener import alerts

                    n = _with_user_store(lambda user: alerts.delete_events(user, body.get("ids")))
                    return self._send_json({"deleted": n, "unread": _with_user_store(alerts.unread)})
                case ["api", "alerts", "channels", name, "test"]:
                    return self._send_json(channel_test(name))
                case ["api", "alerts", alert_id, "delete"]:
                    from tradingagents.screener import alerts

                    _with_user_store(lambda user: alerts.delete(user, alert_id))
                    return self._send_json({"ok": True})
                case ["api", "queue", "cancel"]:
                    return self._send_json({"cancelled": self.queue.cancel_all(), "queue": self.queue.status()})
                case ["api", "queue", job_id, "cancel"]:
                    self._analysis(job_id)
                    return self._send_json({"ok": self.queue.cancel(job_id), "queue": self.queue.status()})
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
            self._send_json({"error": str(exc), **exc.extra}, exc.status)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": f"{type(exc).__name__}: {exc}"},
                            HTTPStatus.INTERNAL_SERVER_ERROR)

    def _drain(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if 0 < length <= 5_000_000:
            self.rfile.read(length)

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

    def _download(self, source: Path | bytes, filename: str, content_type: str | None = None):
        """A file to save: a path on disk, or bytes made for the request (exports)."""
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename) or "download"
        if isinstance(source, bytes):
            data, kind = source, content_type or "application/octet-stream"
        else:
            data = source.read_bytes()
            kind = content_type or ("application/json" if source.suffix == ".json" else "text/markdown") + \
                "; charset=utf-8"
        self._send(data, kind, headers={"Content-Disposition": f'attachment; filename="{safe}"'})


def make_server(host: str = "127.0.0.1", port: int = 8501,
                registry: JobRegistry | None = None, poller=None) -> ThreadingHTTPServer:
    registry = registry or JobRegistry()
    handler = type("BoundHandler", (Handler,), {"registry": registry, "queue": AnalysisQueue(registry),
                                                "poller": poller})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def serve(host: str, port: int, open_browser: bool = True) -> None:
    from tradingagents.screener.alerts import PricePoller

    poller = PricePoller.from_config()
    server = make_server(host, port, poller=poller)
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0', '::') else host}:{port}"
    print(f"TradingAgents UI on {url}  (Ctrl+C to stop)")
    if poller is not None:
        poller.start()
        print(f"Price alerts: checking Yahoo's delayed quotes every {poller.minutes} minutes while NSE is open.")
    if open_browser:
        import webbrowser

        threading.Timer(0.5, webbrowser.open, [url + "/analyze"]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

