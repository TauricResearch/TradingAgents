"""Local-first web cockpit for cached personal research artifacts.

The cockpit intentionally reads only the JSONL cache written by the research
platform.  It does not call market-data vendors or invoke the legacy agent
graph, which keeps the viewing surface deterministic and cheap to run.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from tradingagents.dataflows.utils import safe_ticker_component

from .artifact_store import JsonArtifactStore
from .company_profile import build_company_profile
from .data_health import build_cache_data_health
from .decision_journal import (
    JsonDecisionJournal,
    build_journal_views,
    create_journal_entry,
    review_journal_entry,
)
from .financial_health import assess_financial_health
from .game_approvals import JsonGameApprovalStore
from .game_opportunity import build_game_opportunity_board, build_game_opportunity_snapshot
from .game_opportunity_history import (
    JsonGameOpportunityHistory,
    build_game_opportunity_history_view,
)
from .game_universe import build_game_research_snapshot, list_game_universe_symbols
from .multi_agent_research import multi_agent_configuration_status
from .report_workspace import build_report_workspace, render_archived_report
from .research_jobs import LocalResearchJobRunner, ResearchJobRequest
from .research_readiness import build_research_readiness
from .research_settings import JsonResearchSettingsStore, ResearchSettings
from .run_archive import JsonResearchRunArchive
from .settings_page import SETTINGS_HTML
from .universe_discovery import (
    TushareUniverseDiscovery,
)
from .valuation_context import build_valuation_context
from .watchlist import JsonWatchlistStore, WatchlistEntry
from .watchlist_board import build_watchlist_board
from .watchlist_refresh import WatchlistRefreshRequest, submit_watchlist_refresh

_EARLIEST_DATE = date(1900, 1, 1)


def discover_cached_symbols(
    store: JsonArtifactStore,
    watchlist: JsonWatchlistStore | None = None,
) -> list[str]:
    """Return symbols which have at least one cached artifact file."""

    symbols: set[str] = set()
    for kind in ("prices", "fundamentals", "news", "agent_outputs"):
        directory = store.root / kind
        if directory.exists():
            symbols.update(path.stem for path in directory.glob("*.jsonl"))
    runs_directory = store.root / "runs"
    if runs_directory.exists():
        symbols.update(path.name for path in runs_directory.iterdir() if path.is_dir())
    if watchlist is not None:
        symbols.update(entry.symbol for entry in watchlist.list_entries())
    return sorted(symbols)


def build_cockpit_snapshot(
    store: JsonArtifactStore,
    symbol: str,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Build one JSON-ready, read-only cockpit view from local artifacts."""

    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol is required")

    bars = sorted(
        store.load_price_bars(normalized_symbol, _EARLIEST_DATE, date.max),
        key=lambda bar: bar.date,
    )
    fundamentals = sorted(
        store.load_fundamentals(normalized_symbol),
        key=lambda item: (item.provenance.as_of_date, item.period_end),
    )
    news = sorted(
        store.load_news(normalized_symbol, _EARLIEST_DATE, date.max),
        key=lambda item: item.published_at,
        reverse=True,
    )
    agent_outputs = sorted(
        store.load_agent_outputs(normalized_symbol),
        key=lambda item: (item.as_of_date, item.agent_id, item.output_type.value),
        reverse=True,
    )

    market = _market_summary(bars)
    latest_fundamentals = fundamentals[-1] if fundamentals else None
    financial_quality = [
        item for item in fundamentals if (item.fiscal_period or "").startswith("financial_report_")
    ]
    latest_financial_quality = financial_quality[-1] if financial_quality else None
    financial_quality_history = [
        item
        for _, item in sorted(
            {item.period_end: item for item in financial_quality}.items(),
            reverse=True,
        )[:8]
    ]
    company_profile = build_company_profile(fundamentals, symbol=normalized_symbol)
    game_research = build_game_research_snapshot(normalized_symbol)
    game_approvals = JsonGameApprovalStore(store.root).digest(normalized_symbol)
    game_opportunity = build_game_opportunity_snapshot(store, normalized_symbol)
    game_opportunity_history = build_game_opportunity_history_view(
        JsonGameOpportunityHistory(store.root), normalized_symbol
    )
    valuation_context = build_valuation_context(fundamentals)
    financial_health = assess_financial_health(latest_financial_quality)
    journal = JsonDecisionJournal(store.root)
    journal_views = build_journal_views(
        journal.list_entries(normalized_symbol),
        price_bars=bars,
        as_of_date=date.today(),
    )
    archive = JsonResearchRunArchive(store.root)
    runs = archive.list_runs(normalized_symbol)
    selected_run_id = run_id or (runs[0].run_id if runs else None)
    latest_run = (
        archive.load_bundle(normalized_symbol, selected_run_id)
        if selected_run_id is not None
        else None
    )
    if selected_run_id is not None and latest_run is None:
        raise ValueError("run_id was not found for this symbol")
    displayed_agent_outputs = latest_run.agent_outputs if latest_run is not None else agent_outputs
    data_health = build_cache_data_health(
        price_bars=bars,
        fundamentals=fundamentals,
        news=news,
        reference_as_of_date=(latest_run.as_of_date.date() if latest_run is not None else None),
    )
    readiness = build_research_readiness(
        data_health=data_health,
        valuation_context=valuation_context,
        financial_health=financial_health,
        agent_outputs=(latest_run.agent_outputs if latest_run is not None else agent_outputs),
        signal=(latest_run.signal if latest_run is not None else None),
        risk_review=(latest_run.risk_review if latest_run is not None else None),
        backtest_result=(latest_run.backtest_result if latest_run is not None else None),
    )
    return {
        "symbol": normalized_symbol,
        "has_data": bool(
            bars
            or fundamentals
            or news
            or agent_outputs
            or latest_run
            or game_research.available
            or game_approvals.matched_count
        ),
        "market": market,
        "fundamentals": (
            latest_fundamentals.model_dump(mode="json") if latest_fundamentals is not None else None
        ),
        "financial_quality": (
            latest_financial_quality.model_dump(mode="json")
            if latest_financial_quality is not None
            else None
        ),
        "company_profile": company_profile.model_dump(mode="json"),
        "game_research": game_research.model_dump(mode="json"),
        "game_approvals": game_approvals.model_dump(mode="json"),
        "game_opportunity": game_opportunity.model_dump(mode="json"),
        "game_opportunity_history": game_opportunity_history.model_dump(mode="json"),
        "valuation_context": valuation_context.model_dump(mode="json"),
        "research_readiness": readiness.model_dump(mode="json"),
        "financial_health": financial_health.model_dump(mode="json"),
        "financial_quality_history": [
            item.model_dump(mode="json") for item in financial_quality_history
        ],
        "news": [item.model_dump(mode="json") for item in news[:12]],
        "agent_outputs": [item.model_dump(mode="json") for item in displayed_agent_outputs],
        "latest_run": _run_summary(latest_run, run_id=selected_run_id),
        "report_workspace": build_report_workspace(latest_run),
        "data_health": data_health,
        "runs": [item.model_dump(mode="json") for item in runs[:20]],
        "decision_journal": [item.model_dump(mode="json") for item in journal_views],
        "artifact_counts": {
            "price_bars": len(bars),
            "fundamental_snapshots": len(fundamentals),
            "news_items": len(news),
            "agent_outputs": len(agent_outputs),
        },
    }


def _market_summary(bars: list[Any]) -> dict[str, Any] | None:
    if not bars:
        return None
    first, last = bars[0], bars[-1]
    first_value = first.adjusted_close if first.adjusted_close is not None else first.close
    last_value = last.adjusted_close if last.adjusted_close is not None else last.close
    period_return = last_value / first_value - 1.0 if first_value else None
    adjusted_count = sum(bar.adjusted_close is not None for bar in bars)
    price_basis = (
        "forward_adjusted"
        if adjusted_count == len(bars)
        else "mixed"
        if adjusted_count
        else "raw_unadjusted"
    )
    return {
        "first_date": first.date.isoformat(),
        "last_date": last.date.isoformat(),
        "last_close": last_value,
        "price_basis": price_basis,
        "adjusted_bar_count": adjusted_count,
        "adjustment_coverage_pct": adjusted_count / len(bars),
        "currency": last.currency,
        "period_return_pct": period_return,
        "latest_volume": last.volume,
        "bar_count": len(bars),
        "series": [
            {
                "date": bar.date.isoformat(),
                "close": bar.adjusted_close if bar.adjusted_close is not None else bar.close,
                "volume": bar.volume,
            }
            for bar in bars[-90:]
        ],
    }


def _run_summary(
    bundle: Any | None,
    *,
    run_id: str | None,
) -> dict[str, Any] | None:
    if bundle is None:
        return None

    backtest = bundle.backtest_result
    return {
        "run_id": run_id,
        "as_of_date": bundle.as_of_date.isoformat(),
        "generated_at": bundle.generated_at.isoformat(),
        "signal": bundle.signal.model_dump(mode="json") if bundle.signal is not None else None,
        "risk_review": (
            bundle.risk_review.model_dump(mode="json") if bundle.risk_review is not None else None
        ),
        "run_audit": (
            bundle.run_audit.model_dump(mode="json") if bundle.run_audit is not None else None
        ),
        "backtest": (
            {
                "metrics": backtest.metrics.model_dump(mode="json"),
                "trade_count": len(backtest.trades),
                "round_trip_count": len(backtest.round_trips),
                "warning_count": len(backtest.warning_events) or len(backtest.warnings),
            }
            if backtest is not None
            else None
        ),
    }


class CockpitRequestHandler(BaseHTTPRequestHandler):
    """Serve the local cockpit and its read-only JSON endpoints."""

    store: JsonArtifactStore
    watchlist: JsonWatchlistStore
    jobs: LocalResearchJobRunner

    settings: JsonResearchSettingsStore
    universe_factory: Callable[[], TushareUniverseDiscovery]

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_text(HTTPStatus.OK, _APP_HTML, "text/html; charset=utf-8")
            return
        if parsed.path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if parsed.path == "/settings":
            self._send_text(HTTPStatus.OK, SETTINGS_HTML, "text/html; charset=utf-8")
            return
        if parsed.path == "/api/research-settings":
            settings = self.settings.load()
            self._send_json(
                HTTPStatus.OK,
                {
                    "settings": settings.model_dump(mode="json"),
                    "default_lookback_days": settings.default_lookback_days,
                    "tushare_configured": bool(os.environ.get("TUSHARE_TOKEN", "").strip()),
                },
            )
            return
        if parsed.path == "/api/llm-research-status":
            self._send_json(HTTPStatus.OK, multi_agent_configuration_status())
            return
        if parsed.path == "/api/research-jobs":
            self._send_json(
                HTTPStatus.OK,
                {"jobs": [job.model_dump(mode="json") for job in self.jobs.list_jobs()]},
            )
            return
        if parsed.path.startswith("/api/research-jobs/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            job = self.jobs.get(job_id)
            if job is None:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "job not found"})
            else:
                self._send_json(HTTPStatus.OK, {"job": job.model_dump(mode="json")})
            return
        if parsed.path.startswith("/api/reports/"):
            self._serve_archived_report(parsed)
            return
        if parsed.path == "/api/symbols":
            self._send_json(
                HTTPStatus.OK,
                {
                    "symbols": sorted(
                        set(discover_cached_symbols(self.store, self.watchlist))
                        | set(list_game_universe_symbols())
                    )
                },
            )
            return
        if parsed.path == "/api/game-universe":
            snapshots = [
                build_game_research_snapshot(symbol).model_dump(mode="json")
                for symbol in list_game_universe_symbols()
            ]
            self._send_json(HTTPStatus.OK, {"companies": snapshots})
            return
        if parsed.path == "/api/game-opportunity-history":
            query = parse_qs(parsed.query)
            symbol = query.get("symbol", [""])[0].strip().upper()
            if not symbol:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "symbol is required"})
                return
            view = build_game_opportunity_history_view(
                JsonGameOpportunityHistory(self.store.root), symbol
            )
            self._send_json(HTTPStatus.OK, view.model_dump(mode="json"))
            return
        if parsed.path == "/api/game-opportunities":
            board = build_game_opportunity_board(self.store)
            self._send_json(
                HTTPStatus.OK,
                {"companies": [item.model_dump(mode="json") for item in board]},
            )
            return
        if parsed.path == "/api/game-approvals":
            query = parse_qs(parsed.query)
            symbol = query.get("symbol", [""])[0].strip().upper()
            if not symbol:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "symbol is required"})
                return
            digest = JsonGameApprovalStore(self.store.root).digest(symbol)
            self._send_json(HTTPStatus.OK, digest.model_dump(mode="json"))
            return
        if parsed.path == "/api/watchlist-board":
            board = build_watchlist_board(self.store, self.watchlist)
            names = {item.id: item.name for item in self.settings.load().sector_rules}
            for item in board["items"]:
                item["sector_names"] = [names.get(value, value) for value in item["sectors"]]
            self._send_json(HTTPStatus.OK, board)
            return
        if parsed.path == "/api/watchlist":
            self._send_json(
                HTTPStatus.OK,
                {
                    "entries": [
                        entry.model_dump(mode="json") for entry in self.watchlist.list_entries()
                    ]
                },
            )
            return
        if parsed.path == "/api/decision-journal":
            query = parse_qs(parsed.query)
            symbol = query.get("symbol", [None])[0]
            entries = JsonDecisionJournal(self.store.root).list_entries(symbol)
            views = []
            for entry in entries:
                bars = self.store.load_price_bars(entry.symbol, _EARLIEST_DATE, date.max)
                views.extend(build_journal_views([entry], price_bars=bars, as_of_date=date.today()))
            self._send_json(
                HTTPStatus.OK,
                {"entries": [item.model_dump(mode="json") for item in views]},
            )
            return
        if parsed.path == "/api/snapshot":
            query = parse_qs(parsed.query)
            symbol = query.get("symbol", [""])[0]
            run_id = query.get("run_id", [None])[0]
            try:
                self._send_json(
                    HTTPStatus.OK,
                    build_cockpit_snapshot(self.store, symbol, run_id=run_id),
                )
            except ValueError as error:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def _serve_archived_report(self, parsed) -> None:
        parts = parsed.path.split("/")
        if len(parts) != 5 or not parts[-1].endswith(".md"):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "report not found"})
            return
        symbol = parts[3]
        run_id = parts[4][:-3]
        bundle = JsonResearchRunArchive(self.store.root).load_bundle(symbol, run_id)
        try:
            report = render_archived_report(bundle)
        except ValueError as error:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(error)})
            return
        download = parse_qs(parsed.query).get("download", ["0"])[0] == "1"
        disposition = None
        if download:
            disposition = (
                f'attachment; filename="{safe_ticker_component(bundle.symbol)}_{run_id}.md"'
            )
        self._send_text(
            HTTPStatus.OK,
            report,
            "text/markdown; charset=utf-8",
            content_disposition=disposition,
        )

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        if parsed.path in {"/api/universe-preview", "/api/universe-sync"}:
            try:
                result = self.universe_factory().discover(self.settings.load())
            except Exception as error:
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(error)})
                return
            payload: dict[str, Any] = {"discovery": result.model_dump(mode="json")}
            if parsed.path == "/api/universe-sync":
                entries = [
                    WatchlistEntry(
                        symbol=item.symbol,
                        name=item.name or None,
                        sectors=item.sectors,
                        source="tushare_concept",
                    )
                    for item in result.stocks
                ]
                merged = self.watchlist.add_many(entries)
                payload["watchlist_total"] = len(merged)
            self._send_json(HTTPStatus.OK, payload)
            return

        if parsed.path == "/api/decision-journal":
            try:
                payload = self._read_json_body()
                symbol = str(payload.get("symbol", "")).strip().upper()
                run_id = str(payload.get("run_id", "")).strip()
                review_due_date = date.fromisoformat(str(payload.get("review_due_date", "")))
                bundle = JsonResearchRunArchive(self.store.root).load_bundle(symbol, run_id)
                if bundle is None:
                    raise ValueError("research run was not found for this symbol")
                if bundle.signal is None:
                    raise ValueError("research run has no manual decision to journal")
                price_bars = [
                    *bundle.price_bars,
                    *self.store.load_price_bars(
                        symbol,
                        _EARLIEST_DATE,
                        bundle.as_of_date.date(),
                        as_of_date=bundle.as_of_date.date(),
                    ),
                ]
                journal = JsonDecisionJournal(self.store.root)
                if journal.find_for_run(symbol, run_id) is not None:
                    raise ValueError("research run is already in the decision journal")
                entry = create_journal_entry(
                    symbol=symbol,
                    research_run_id=run_id,
                    signal=bundle.signal,
                    review_due_date=review_due_date,
                    price_bars=price_bars,
                )
                journal.add_entry(entry)
            except (UnicodeDecodeError, ValueError) as error:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return
            self._send_json(HTTPStatus.CREATED, {"entry": entry.model_dump(mode="json")})
            return
        if parsed.path.startswith("/api/decision-journal/") and parsed.path.endswith("/review"):
            entry_id = (
                parsed.path.removeprefix("/api/decision-journal/")
                .removesuffix("/review")
                .strip("/")
            )
            try:
                payload = self._read_json_body()
                reviewed_on = date.fromisoformat(str(payload.get("reviewed_on", "")))
                journal = JsonDecisionJournal(self.store.root)
                entry = journal.get_entry(entry_id)
                if entry is None:
                    self._send_json(
                        HTTPStatus.NOT_FOUND, {"error": "decision journal entry was not found"}
                    )
                    return
                reviewed = review_journal_entry(
                    entry,
                    reviewed_on=reviewed_on,
                    price_bars=self.store.load_price_bars(
                        entry.symbol,
                        _EARLIEST_DATE,
                        reviewed_on,
                        as_of_date=reviewed_on,
                    ),
                    note=str(payload.get("note", "")),
                )
                journal.replace_entry(reviewed)
            except (UnicodeDecodeError, ValueError) as error:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return
            self._send_json(HTTPStatus.OK, {"entry": reviewed.model_dump(mode="json")})
            return
        if parsed.path == "/api/research-jobs":
            try:
                payload = self._read_json_body()
                settings = self.settings.load()
                payload.setdefault("lookback_days", settings.default_lookback_days)
                payload.setdefault("data_provider", settings.preferred_data_provider)
                request = ResearchJobRequest.model_validate(payload)
            except (UnicodeDecodeError, ValueError) as error:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return
            job = self.jobs.submit(request)
            self._send_json(HTTPStatus.ACCEPTED, {"job": job.model_dump(mode="json")})
            return
        if urlparse(self.path).path == "/api/watchlist-refresh":
            try:
                payload = self._read_json_body()
                settings = self.settings.load()
                payload.setdefault("lookback_days", settings.default_lookback_days)
                payload.setdefault("data_provider", settings.preferred_data_provider)
                request = WatchlistRefreshRequest.model_validate(payload)
            except (UnicodeDecodeError, ValueError) as error:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return
            batch = submit_watchlist_refresh(self.watchlist, self.jobs, request)
            self._send_json(HTTPStatus.ACCEPTED, batch.model_dump(mode="json"))
            return
        if urlparse(self.path).path != "/api/watchlist":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            payload = self._read_json_body()
            entry = self.watchlist.add(str(payload.get("symbol", "")))
        except (UnicodeDecodeError, ValueError) as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self._send_json(HTTPStatus.CREATED, {"entry": entry.model_dump(mode="json")})

    def do_PUT(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        if parsed.path != "/api/research-settings":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            settings = ResearchSettings.model_validate(self._read_json_body())
        except (UnicodeDecodeError, ValueError) as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self.settings.save(settings)
        self._send_json(
            HTTPStatus.OK,
            {
                "settings": settings.model_dump(mode="json"),
                "default_lookback_days": settings.default_lookback_days,
                "tushare_configured": bool(os.environ.get("TUSHARE_TOKEN", "").strip()),
            },
        )

    def do_DELETE(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        if parsed.path != "/api/watchlist":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        symbol = parse_qs(parsed.query).get("symbol", [""])[0]
        try:
            removed = self.watchlist.remove(symbol)
        except ValueError as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self._send_json(HTTPStatus.OK, {"removed": removed})

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("expected a JSON request body") from error
        if not isinstance(payload, dict):
            raise ValueError("expected a JSON object")
        return payload

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Keep normal browser navigation out of the terminal."""

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        self._send_text(
            status, json.dumps(payload, ensure_ascii=True), "application/json; charset=utf-8"
        )

    def _send_text(
        self,
        status: HTTPStatus,
        payload: str,
        content_type: str,
        *,
        content_disposition: str | None = None,
    ) -> None:
        encoded = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        if content_disposition is not None:
            self.send_header("Content-Disposition", content_disposition)
        self.end_headers()
        self.wfile.write(encoded)


def create_cockpit_server(
    data_dir: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    universe_factory: Callable[[], TushareUniverseDiscovery] | None = None,
) -> ThreadingHTTPServer:
    """Create a local server without starting it, suitable for tests and CLI use."""

    store = JsonArtifactStore(data_dir)
    watchlist = JsonWatchlistStore(data_dir)
    jobs = LocalResearchJobRunner(data_dir)
    settings = JsonResearchSettingsStore(data_dir)

    class BoundCockpitRequestHandler(CockpitRequestHandler):
        pass

    BoundCockpitRequestHandler.store = store
    BoundCockpitRequestHandler.watchlist = watchlist
    BoundCockpitRequestHandler.jobs = jobs
    BoundCockpitRequestHandler.settings = settings
    BoundCockpitRequestHandler.universe_factory = universe_factory or TushareUniverseDiscovery
    return ThreadingHTTPServer((host, port), BoundCockpitRequestHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local personal research cockpit.")
    parser.add_argument(
        "--data-dir",
        default=".research-data",
        help="JSONL artifact cache directory (default: .research-data)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    args = parser.parse_args(argv)

    server = create_cockpit_server(args.data_dir, host=args.host, port=args.port)
    print(f"Research cockpit ready at http://{args.host}:{args.port}")
    print(f"Reading local artifacts from {Path(args.data_dir).resolve()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nResearch cockpit stopped.")
    finally:
        server.server_close()
    return 0


_APP_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>个人股票投研</title>
  <style>
    :root { color-scheme: light; font-family: Inter, "Microsoft YaHei", ui-sans-serif, system-ui, sans-serif; color: #17232c; background: #f3f6f7; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #f3f6f7; }
    button, input, select, textarea { font: inherit; }
    button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible, summary:focus-visible, .view-tab:focus-visible { outline: 3px solid rgba(23, 111, 108, .22); outline-offset: 2px; }
    .shell { max-width: 1440px; margin: 0 auto; padding: 0 30px 48px; }
    .app-header { position: sticky; top: 0; z-index: 20; margin: 0 -30px; padding: 18px 30px 12px; border-bottom: 1px solid #cfdadd; background: rgba(243, 246, 247, .97); }
    .header-row { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
    .brand { min-width: 220px; }
    h1 { margin: 0; font-size: 23px; line-height: 1.2; font-weight: 720; letter-spacing: 0; }
    .eyebrow { margin: 0 0 5px; color: #39706e; font-size: 11px; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
    .commandbar { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
    input, select, button, .menu-summary { height: 38px; border: 1px solid #b8c7cd; border-radius: 5px; background: #fff; color: #17232c; padding: 0 11px; }
    select { min-width: 150px; }
    button { cursor: pointer; font-weight: 680; }
    button:hover, .menu-summary:hover { border-color: #39706e; background: #edf7f6; }
    button:disabled { cursor: not-allowed; color: #95a3a9; background: #f4f7f8; }
    .primary-action { border-color: #176f6c; background: #176f6c; color: #fff; }
    .primary-action:hover { border-color: #115d5a; background: #115d5a; }
    .secondary-action { border-color: #708088; }
    .watch-menu { position: relative; }
    .menu-summary { display: flex; align-items: center; cursor: pointer; font-weight: 680; list-style: none; }
    .menu-summary::-webkit-details-marker { display: none; }
    .menu-summary::after { content: "▾"; margin-left: 8px; color: #64747d; font-size: 11px; }
    .watch-menu[open] .menu-summary::after { content: "▴"; }
    .menu-content { position: absolute; right: 0; top: 44px; z-index: 30; width: 290px; padding: 12px; border: 1px solid #c3d0d4; border-radius: 6px; background: #fff; box-shadow: 0 12px 30px rgba(30, 49, 57, .14); }
    .menu-row { display: flex; gap: 7px; }
    .menu-row + .menu-row { margin-top: 8px; }
    .menu-row input { min-width: 0; width: 100%; }
    .menu-row button { flex: 1; white-space: nowrap; }
    .status-row { display: flex; align-items: center; justify-content: space-between; gap: 14px; min-height: 28px; margin-top: 9px; }
    .status { margin: 0; color: #60717a; font-size: 12px; line-height: 1.4; }
    .data-as-of { color: #60717a; font-size: 12px; white-space: nowrap; }
    .status::before { content: ""; display: inline-block; width: 7px; height: 7px; margin-right: 7px; border-radius: 50%; background: #829198; vertical-align: 1px; }
    .status[data-tone="busy"]::before { background: #2877a1; animation: status-pulse 1.2s ease-in-out infinite; }
    .status[data-tone="success"]::before { background: #087f5b; }
    .status[data-tone="warning"]::before { background: #a06628; }
    .status[data-tone="error"]::before { background: #b83d47; }
    @keyframes status-pulse { 50% { opacity: .35; } }
    .filter-group { display: inline-flex; gap: 0; border: 1px solid #bdcbd0; border-radius: 5px; overflow: hidden; }
    .filter-button { height: 28px; border: 0; border-right: 1px solid #d1dcdf; border-radius: 0; padding: 0 10px; background: #fff; color: #5e6d75; font-size: 11px; }
    .filter-button:last-child { border-right: 0; }
    .filter-button[aria-pressed="true"] { background: #e7f2f1; color: #115d5a; }
    .decision-conditional[hidden] { display: none; }
    .view-tabs { position: sticky; top: 98px; z-index: 15; display: flex; gap: 2px; margin: 0 -30px 18px; padding: 0 30px; border-bottom: 1px solid #cfdadd; background: #f3f6f7; overflow-x: auto; scrollbar-width: thin; }
    .view-tab { flex: 0 0 auto; height: 45px; border: 0; border-bottom: 3px solid transparent; border-radius: 0; background: transparent; color: #5e6d75; padding: 0 17px; }
    .view-tab:hover { border-color: #b9c8cb; background: transparent; }
    .view-tab[aria-selected="true"] { border-bottom-color: #176f6c; color: #17232c; }
    .view { display: none; }
    .view.active { display: block; }
    .view-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin: 0 0 12px; }
    .view-heading h2 { font-size: 19px; }
    .view-meta { color: #64747d; font-size: 12px; }
    .metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid #d1dcdf; border-radius: 6px; background: #fff; }
    .metric { min-height: 92px; padding: 16px 17px; border-right: 1px solid #dbe4e6; }
    .metric:last-child { border-right: 0; }
    .metric-label { color: #64747d; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }
    .metric-value { margin-top: 7px; font-size: 22px; font-weight: 720; overflow-wrap: anywhere; }
    .metric-detail { margin-top: 4px; color: #64747d; font-size: 11px; }
    .positive { color: #087f5b; }
    .negative { color: #b83d47; }
    .neutral { color: #17232c; }
    .section-grid { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(320px, .75fr); gap: 16px; margin-top: 16px; align-items: start; }
    .section-grid.equal { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .span-2 { grid-column: 1 / -1; }
    .panel { background: #fff; border: 1px solid #d1dcdf; border-radius: 6px; overflow: hidden; min-width: 0; }
    .panel-title { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 10px; min-height: 48px; padding: 13px 16px; border-bottom: 1px solid #dbe4e6; }
    h2 { margin: 0; font-size: 14px; letter-spacing: 0; }
    .panel-meta { color: #64747d; font-size: 11px; }
    .data-health { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .health-item { min-height: 76px; padding: 12px 15px; border-right: 1px solid #dbe4e6; }
    .health-item:last-child { border-right: 0; }
    .health-title { color: #64747d; font-size: 11px; font-weight: 680; }
    .health-status { display: inline-block; margin-top: 5px; font-size: 12px; font-weight: 720; color: #176f6c; }
    .health-status.lagging, .health-status.missing { color: #a06628; }
    .health-detail { margin-top: 4px; color: #64747d; font-size: 11px; line-height: 1.35; }
    .readiness-disclosure > summary, .report-disclosure > summary { cursor: pointer; list-style: none; }
    .readiness-disclosure > summary::-webkit-details-marker, .report-disclosure > summary::-webkit-details-marker { display: none; }
    .readiness-disclosure > summary::after, .report-disclosure > summary::after { content: "展开"; color: #176f6c; font-size: 11px; font-weight: 680; }
    .readiness-disclosure[open] > summary::after, .report-disclosure[open] > summary::after { content: "收起"; }
    .table-wrap { overflow-x: auto; }
    .watchlist-table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .watchlist-table th, .watchlist-table td { padding: 10px 15px; border-bottom: 1px solid #e3eaec; text-align: left; white-space: nowrap; }
    .watchlist-table th { color: #64747d; font-size: 10px; font-weight: 720; text-transform: uppercase; letter-spacing: .04em; }
    .watchlist-table tr:last-child td { border-bottom: 0; }
    .watch-symbol { height: auto; border: 0; border-radius: 0; background: transparent; color: #176f6c; padding: 0; font-weight: 720; }
    .watch-symbol:hover { background: transparent; text-decoration: underline; }
    .board-status { font-size: 11px; font-weight: 720; color: #39706e; }
    .board-status.lagging, .board-status.missing, .board-status.weak { color: #a06628; }
    .board-status.supportive, .board-status.ready, .board-status.aligned { color: #087f5b; }
    .chart { height: 250px; padding: 15px 17px 11px; }
    svg { display: block; width: 100%; height: 100%; overflow: visible; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; }
    .grid > div { padding: 12px 15px; border-bottom: 1px solid #e3eaec; min-width: 0; }
    .grid > div:nth-child(odd) { border-right: 1px solid #e3eaec; }
    .label { display: block; color: #64747d; font-size: 11px; }
    .value { display: block; margin-top: 4px; font-weight: 680; overflow-wrap: anywhere; }
    textarea { min-height: 78px; resize: vertical; border: 1px solid #b8c7cd; border-radius: 5px; background: #fff; color: #17232c; padding: 9px 11px; }
    .decision-form input, .decision-form select, .decision-form textarea { width: 100%; min-width: 0; }
    .decision-form .wide { grid-column: 1 / -1; }
    .items { margin: 0; padding: 0; list-style: none; }
    .item { padding: 12px 15px; border-bottom: 1px solid #e3eaec; }
    .item:last-child { border-bottom: 0; }
    .item-title { font-weight: 680; line-height: 1.4; }
    .item-meta { color: #64747d; font-size: 11px; margin-top: 4px; }
    .item-summary { color: #45565f; line-height: 1.45; margin-top: 6px; font-size: 12px; }
    .agent-card { padding: 0; background: #fff; }
    .agent-card > details > summary { cursor: pointer; list-style: none; padding: 14px 15px; }
    .agent-card > details > summary::-webkit-details-marker { display: none; }
    .agent-card > details > summary::after { content: "展开"; float: right; color: #176f6c; font-size: 10px; font-weight: 680; }
    .agent-card > details[open] > summary::after { content: "收起"; }
    .agent-card.manager { border-left: 4px solid #176f6c; background: #fbfefe; }
    .agent-card.failed { border-left: 4px solid #c9822d; background: #fffdf8; }
    .agent-card-title { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; padding-right: 42px; font-weight: 720; line-height: 1.4; }
    .agent-role-badge, .agent-status-badge { display: inline-block; padding: 2px 6px; border-radius: 999px; font-size: 10px; font-weight: 720; }
    .agent-role-badge { background: #e8f3f2; color: #176f6c; }
    .agent-status-badge { background: #eef2f3; color: #5d6d75; }
    .agent-status-badge.failed { background: #fff0dc; color: #9a5b18; }
    .agent-body { padding: 0 15px 15px; border-top: 1px solid #edf1f2; }
    .agent-lead { margin: 12px 0 0; color: #31454e; font-size: 13px; line-height: 1.65; white-space: pre-wrap; }
    .agent-section { margin-top: 13px; padding-top: 11px; border-top: 1px solid #e5ecee; }
    .agent-section h4 { margin: 0 0 6px; color: #176f6c; font-size: 12px; }
    .agent-section p { margin: 0; color: #45565f; font-size: 12px; line-height: 1.6; white-space: pre-wrap; }
    .agent-section ul { margin: 6px 0 0; padding-left: 18px; color: #45565f; font-size: 12px; line-height: 1.55; }
    .agent-evidence { margin-top: 12px; color: #64747d; font-size: 10px; line-height: 1.5; }
    .tags { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
    .tag { padding: 3px 6px; border: 1px solid #cbd8db; border-radius: 4px; color: #39706e; font-size: 10px; font-weight: 680; }
    .report-actions { display: flex; flex-wrap: wrap; gap: 10px; }
    .action-link { color: #176f6c; font-size: 12px; font-weight: 680; text-decoration: none; }
    .action-link:hover { text-decoration: underline; }
    .action-link[aria-disabled="true"] { color: #95a3a9; pointer-events: none; }
    .coverage-summary { padding: 12px 15px; border-bottom: 1px solid #e3eaec; color: #45565f; font-size: 12px; }
    .coverage-list { margin: 0; padding: 0; list-style: none; }
    .coverage-item { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 5px 12px; padding: 10px 15px; border-bottom: 1px solid #e3eaec; }
    .coverage-label { font-size: 12px; font-weight: 680; }
    .coverage-detail { color: #64747d; font-size: 11px; }
    .coverage-status { color: #39706e; font-size: 10px; font-weight: 680; }
    .coverage-status.missing { color: #a06628; }
    .report-preview { max-height: 520px; overflow: auto; margin: 0; padding: 15px; background: #fbfcfc; color: #35454d; font: 12px/1.55 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap; }
    .empty { padding: 28px 16px; color: #64747d; text-align: center; }
    a { color: #176f6c; }
    @media (max-width: 920px) {
      .shell { padding: 0 16px 34px; }
      .app-header { position: static; margin: 0 -16px; padding: 16px; }
      .header-row { align-items: stretch; flex-direction: column; }
      .brand { min-width: 0; }
      .commandbar { justify-content: flex-start; }
      .view-tabs { position: sticky; top: 0; margin: 0 -16px 16px; padding: 0 16px; }
      .section-grid, .section-grid.equal { grid-template-columns: 1fr; }
      .span-2 { grid-column: auto; }
      .data-health { grid-template-columns: 1fr; }
      .health-item { border-right: 0; border-bottom: 1px solid #dbe4e6; }
      .health-item:last-child { border-bottom: 0; }
    }
    @media (max-width: 560px) {
      .commandbar { display: grid; grid-template-columns: 1fr 1fr; width: 100%; }
      .commandbar #symbol { grid-column: 1 / -1; width: 100%; }
      .commandbar > button, .watch-menu, .menu-summary { width: 100%; }
      .menu-content { position: fixed; left: 12px; right: 12px; top: auto; width: auto; }
      .status-row { align-items: flex-start; flex-direction: column; gap: 3px; }
      .metrics { grid-template-columns: 1fr 1fr; }
      .metric { min-height: 82px; border-bottom: 1px solid #dbe4e6; }
      .metric:nth-child(2) { border-right: 0; }
      .metric-value { font-size: 19px; }
      .grid { grid-template-columns: 1fr; }
      .grid > div:nth-child(odd) { border-right: 0; }
      .view-tab { padding: 0 13px; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header class="app-header">
      <div class="header-row">
        <div class="brand"><p class="eyebrow">个人股票投研</p><h1 id="title">研究驾驶舱</h1></div>
        <div class="commandbar" aria-label="研究操作">
          <select id="symbol" aria-label="选择股票"></select>
          <a class="action-link" href="/settings">&#30740;&#31350;&#37197;&#32622;</a>
          <button id="refreshWatchlistResearch" class="secondary-action" type="button">更新全部自选股</button>
          <button id="runResearch" class="primary-action" type="button">研究当前股票</button>
          <details class="watch-menu">
            <summary class="menu-summary">自选管理</summary>
            <div class="menu-content">
              <div class="menu-row"><input id="watchSymbol" aria-label="输入股票代码" placeholder="股票代码"><button id="addSymbol" type="button">添加</button></div>
              <div class="menu-row"><button id="removeSymbol" type="button">移除当前股票</button><button id="refresh" type="button">读取本地数据</button></div>
            </div>
          </details>
        </div>
      </div>
      <div class="status-row"><p class="status" id="status" role="status">正在读取本地研究数据...</p><span class="data-as-of" id="headerAsOf">数据日期：--</span></div>
    </header>

    <nav class="view-tabs" role="tablist" aria-label="研究视图">
      <button class="view-tab" type="button" role="tab" aria-selected="true" aria-controls="view-overview" data-view-target="overview">研究概览</button>
      <button class="view-tab" type="button" role="tab" aria-selected="false" aria-controls="view-game" data-view-target="game">游戏业务</button>
      <button class="view-tab" type="button" role="tab" aria-selected="false" aria-controls="view-financials" data-view-target="financials">财务估值</button>
      <button class="view-tab" type="button" role="tab" aria-selected="false" aria-controls="view-research" data-view-target="research">研究报告</button>
      <button class="view-tab" type="button" role="tab" aria-selected="false" aria-controls="view-decision" data-view-target="decision">决策复盘</button>
    </nav>

    <section class="view active" id="view-overview" role="tabpanel" data-view="overview">
      <div class="view-heading"><h2>研究概览</h2><span class="view-meta" id="overviewMeta">--</span></div>
      <section class="metrics" aria-label="市场摘要" id="metrics"></section>
      <div class="section-grid">
        <div class="panel"><div class="panel-title"><h2>游戏机会雷达</h2><span class="panel-meta" id="gameOpportunityMeta"></span></div><ul class="items" id="gameOpportunity"></ul></div>
        <div class="panel"><div class="panel-title"><h2>最新变化</h2><span class="panel-meta" id="gameOpportunityHistoryMeta"></span></div><ul class="items" id="gameOpportunityHistory"></ul></div>
        <div class="panel span-2"><div class="panel-title"><h2>数据状态</h2><span class="panel-meta">价格 · 财务 · 事件</span></div><section class="data-health" aria-label="缓存数据状态" id="dataHealth"></section></div>
        <div class="panel"><div class="panel-title"><h2>价格走势</h2><span class="panel-meta" id="chartMeta"></span></div><div class="chart" id="chart"></div></div>
        <div class="panel"><div class="panel-title"><h2>公司概况</h2><span class="panel-meta" id="companyProfileMeta"></span></div><div class="grid" id="companyProfile"></div></div>
        <div class="panel span-2"><div class="panel-title"><h2>自选股</h2><span class="panel-meta" id="watchlistMeta"></span></div><div class="table-wrap"><table class="watchlist-table"><thead><tr><th>股票</th><th>最新价格</th><th>价格日期</th><th>数据状态</th><th>最近研究</th><th>决策</th></tr></thead><tbody id="watchlistBoard"></tbody></table></div></div>
        <details class="panel span-2 readiness-disclosure"><summary class="panel-title"><h2>研究准备度</h2><span class="panel-meta" id="readinessMeta"></span></summary><ul class="items" id="readiness"></ul></details>
      </div>
    </section>

    <section class="view" id="view-game" role="tabpanel" data-view="game" hidden>
      <div class="view-heading"><h2>游戏业务</h2><span class="view-meta">主体 · 产品 · 催化 · 版号</span></div>
      <div class="section-grid equal">
        <div class="panel"><div class="panel-title"><h2>业务主体</h2><span class="panel-meta" id="gameBusinessMeta"></span></div><ul class="items" id="gameBusiness"></ul></div>
        <div class="panel"><div class="panel-title"><h2>产品催化</h2><span class="panel-meta" id="gameCatalystsMeta"></span></div><ul class="items" id="gameCatalysts"></ul></div>
        <div class="panel span-2"><div class="panel-title"><h2>产品矩阵</h2><div class="report-actions"><span class="panel-meta" id="gameProductsMeta"></span><div class="filter-group" role="group" aria-label="筛选游戏产品"><button class="filter-button" type="button" data-product-filter="all" aria-pressed="true">全部</button><button class="filter-button" type="button" data-product-filter="live" aria-pressed="false">在营</button><button class="filter-button" type="button" data-product-filter="pipeline" aria-pressed="false">储备</button></div></div></div><div class="table-wrap"><table class="watchlist-table"><thead><tr><th>产品</th><th>状态</th><th>类型</th><th>平台</th><th>市场</th></tr></thead><tbody id="gameProducts"></tbody></table></div></div>
        <div class="panel span-2"><div class="panel-title"><h2>游戏版号</h2><span class="panel-meta" id="gameApprovalsMeta"></span></div><div class="table-wrap"><table class="watchlist-table"><thead><tr><th>批准日期</th><th>游戏</th><th>类型</th><th>运营单位</th><th>批复文号</th></tr></thead><tbody id="gameApprovals"></tbody></table></div></div>
      </div>
    </section>

    <section class="view" id="view-financials" role="tabpanel" data-view="financials" hidden>
      <div class="view-heading"><h2>财务估值</h2><span class="view-meta">质量 · 趋势 · 历史分位</span></div>
      <div class="section-grid equal">
        <div class="panel"><div class="panel-title"><h2>最新估值</h2><span class="panel-meta" id="fundamentalsMeta"></span></div><div class="grid" id="fundamentals"></div></div>
        <div class="panel"><div class="panel-title"><h2>财务健康</h2><span class="panel-meta" id="financialHealthMeta"></span></div><ul class="items" id="financialHealth"></ul></div>
        <div class="panel span-2"><div class="panel-title"><h2>估值区间</h2><span class="panel-meta" id="valuationContextMeta"></span></div><div class="table-wrap"><table class="watchlist-table"><thead><tr><th>指标</th><th>最新</th><th>历史分位</th><th>低位</th><th>中位</th><th>高位</th><th>样本</th></tr></thead><tbody id="valuationContext"></tbody></table></div></div>
        <div class="panel"><div class="panel-title"><h2>财务质量</h2><span class="panel-meta" id="financialQualityMeta"></span></div><div class="grid" id="financialQuality"></div></div>
        <div class="panel"><div class="panel-title"><h2>财务趋势</h2><span class="panel-meta" id="financialTrendMeta"></span></div><div class="table-wrap"><table class="watchlist-table"><thead><tr><th>报告期</th><th>营收</th><th>净利润</th><th>经营现金流</th><th>ROE</th></tr></thead><tbody id="financialTrend"></tbody></table></div></div>
      </div>
    </section>

    <section class="view" id="view-research" role="tabpanel" data-view="research" hidden>
      <div class="view-heading"><h2>研究报告</h2><span class="view-meta">研究记录 · 证据 · 报告</span></div>
      <div class="section-grid equal">
        <div class="panel"><div class="panel-title"><h2>结构化研究</h2><span class="panel-meta" id="agentsMeta"></span></div><ul class="items" id="agents"></ul></div>
        <div class="panel"><div class="panel-title"><h2>公司事件</h2><span class="panel-meta" id="newsMeta"></span></div><ul class="items" id="news"></ul></div>
        <div class="panel"><div class="panel-title"><h2>研究记录</h2><select id="runHistory" aria-label="选择历史研究记录"></select></div><div class="empty" id="runHistoryDetail"></div></div>
        <div class="panel"><div class="panel-title"><h2>报告覆盖</h2><div class="report-actions"><a id="openReport" class="action-link" target="_blank" rel="noreferrer" aria-disabled="true">打开报告</a><a id="exportReport" class="action-link" aria-disabled="true">导出 Markdown</a></div></div><div id="reportCoverage" class="empty">请选择一条研究记录。</div><details id="reportDisclosure" class="report-disclosure"><summary class="panel-title"><h2>报告全文</h2><span class="panel-meta">Markdown</span></summary><pre id="reportPreview" class="report-preview">暂无研究报告。</pre></details></div>
      </div>
    </section>

    <section class="view" id="view-decision" role="tabpanel" data-view="decision" hidden>
      <div class="view-heading"><h2>决策复盘</h2><span class="view-meta">判断 · 风控 · 回测 · 复盘</span></div>
      <div class="section-grid equal">
        <div class="panel"><div class="panel-title"><h2>形成判断</h2><span class="panel-meta">可选手工信号</span></div><div class="grid decision-form">
          <div class="wide"><label class="label" for="dataProvider">数据源</label><select id="dataProvider"><option value="auto" selected>自动（A/H股优先 Tushare）</option><option value="tushare">Tushare Pro</option><option value="yfinance">Yahoo Finance</option></select></div>
          <div class="wide"><label class="label" for="lookbackPeriod">&#30740;&#31350;&#25968;&#25454;&#21608;&#26399;</label><select id="lookbackPeriod"><option value="365">365 &#22825;</option></select></div>
          <div class="wide"><label class="label" for="narrativeMode">分析模式</label><select id="narrativeMode"><option value="deterministic" selected>确定性分析</option><option value="multi_agent_research">多智能体研究（研究命题，不批准仓位）</option><option value="openai_narrative">OpenAI 叙事分析</option></select><div class="item-meta" id="llmResearchStatus">正在检查服务端模型配置…</div></div>
          <div><label class="label" for="decisionDirection">方向</label><select id="decisionDirection"><option value="">暂不形成决策</option><option value="buy">买入</option><option value="hold">持有</option><option value="sell">卖出</option></select></div>
          <div class="decision-conditional" hidden><label class="label" for="decisionHorizon">周期</label><select id="decisionHorizon"><option value="short">短期</option><option value="medium" selected>中期</option><option value="long">长期</option></select></div>
          <div class="decision-conditional" hidden><label class="label" for="decisionConfidence">信心（%）</label><input id="decisionConfidence" type="number" min="0" max="100" step="1" value="60"></div>
          <div class="decision-conditional" hidden><label class="label" for="decisionPosition">拟议仓位（%）</label><input id="decisionPosition" type="number" min="0" max="100" step="0.1" value="5"></div>
          <div class="wide decision-conditional" hidden><label class="label" for="decisionRationale">判断依据</label><textarea id="decisionRationale">手工研究判断。</textarea></div>
        </div></div>
        <div class="panel"><div class="panel-title"><h2>决策与风控</h2><span class="panel-meta" id="decisionMeta"></span></div><div class="grid" id="decision"></div></div>
        <div class="panel"><div class="panel-title"><h2>回测结果</h2><span class="panel-meta" id="backtestMeta"></span></div><div class="grid" id="backtest"></div></div>
        <div class="panel"><div class="panel-title"><h2>决策日志</h2><button id="addJournalEntry" type="button">记录当前决策</button></div><div class="grid decision-form"><div><label class="label" for="journalReviewDue">计划复盘日期</label><input id="journalReviewDue" type="date"></div><div><label class="label" for="journalReviewedOn">实际复盘日期</label><input id="journalReviewedOn" type="date"></div><div class="wide"><label class="label" for="journalReviewNote">复盘记录</label><textarea id="journalReviewNote" placeholder="记录结果、偏差和后续调整"></textarea></div></div><ul class="items" id="decisionJournal"></ul><div class="empty" id="decisionJournalEmpty">选择包含手工决策的研究记录后，可写入决策日志。</div></div>
      </div>
    </section>
  </main>
  <script>
    const $ = id => document.getElementById(id);
    const money = (v, c) => v == null ? 'N/A' : `${c || ''}${c ? ' ' : ''}${Number(v).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    const pct = v => v == null ? 'N/A' : `${(Number(v) * 100).toFixed(2)}%`;
    const text = value => value == null || value === '' ? 'N/A' : String(value);
    const escape = value => text(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;', "'":'&#39;'}[char]));
    const initialParams = new URLSearchParams(window.location.search);
    const requestedSymbol = (initialParams.get('symbol') || '').toUpperCase();
    fetch('/api/llm-research-status').then(response => response.json()).then(status => {
      const target = $('llmResearchStatus');
      target.textContent = status.ready ? `已就绪：${status.provider} / ${status.model}` : status.message;
      target.className = 'item-meta ' + (status.ready ? 'positive' : 'warning');
    }).catch(() => { $('llmResearchStatus').textContent = '无法读取服务端模型配置状态'; });
    const validViews = new Set(['overview', 'game', 'financials', 'research', 'decision']);
    let activeView = validViews.has(initialParams.get('view')) ? initialParams.get('view') : 'overview';
    const translations = {
      'Last Close':'最新收盘', 'Period Return':'区间涨跌', 'Latest Volume':'最新成交量', 'Latest Decision':'最新决策',
      'Market data':'市场数据', 'Fundamentals':'基本面', 'Valuation context':'估值区间', 'Financial health':'财务健康',
      'Investment thesis':'投资逻辑', 'Corporate events':'公司事件', 'Manual decision':'手工决策', 'Risk review':'风控复核',
      'Backtest':'回测', 'Name':'公司名称', 'Industry':'行业', 'Area':'地区', 'Market':'板块', 'Exchange':'交易所',
      'Listing Date':'上市日期', 'Official approvals':'官方版号', 'Product catalysts':'产品催化',
      'Financial delivery':'财务兑现', 'Market confirmation':'市场确认', 'P/E (TTM)':'市盈率（TTM）',
      'Price to Book':'市净率', 'Price to Sales (TTM)':'市销率（TTM）', 'Dividend Yield (%)':'股息率',
      'ready':'就绪', 'aligned':'正常', 'lagging':'滞后', 'missing':'缺失', 'required':'必需', 'optional':'可选',
      'supportive':'支持', 'mixed':'混合', 'weak':'偏弱', 'healthy':'健康', 'watch':'关注',
      'high_attention':'高关注', 'low_signal':'低信号', 'insufficient_data':'数据不足',
      'listed_company':'上市公司', 'game_business':'游戏业务', 'developer_publisher':'研发发行',
      'live':'在营', 'pipeline':'储备', 'legacy_live':'长线运营', 'upcoming':'即将发生',
      'completed':'已完成', 'ongoing':'持续跟踪', 'undated':'待定档', 'domestic':'国产', 'imported':'进口',
      'buy':'买入', 'hold':'持有', 'sell':'卖出', 'short':'短期', 'medium':'中期', 'long':'长期',
      'cash_conversion':'现金转化', 'leverage':'杠杆水平', 'liquidity':'流动性', 'return_on_equity':'净资产收益率'
    };
    const zh = value => translations[String(value)] || String(value);
    const compactAmount = value => {
      if (value == null || !Number.isFinite(Number(value))) return 'N/A';
      const number = Number(value);
      if (Math.abs(number) >= 1e8) return (number / 1e8).toFixed(2) + ' 亿元';
      if (Math.abs(number) >= 1e4) return (number / 1e4).toFixed(2) + ' 万';
      return number.toLocaleString('zh-CN', {maximumFractionDigits: 2});
    };
    const conciseNumber = value => value == null || !Number.isFinite(Number(value)) ? 'N/A' : Number(value).toLocaleString('zh-CN', {maximumFractionDigits: 2});
    const metricLabel = key => ({
      pe_ratio:'市盈率', pe_ratio_ttm:'市盈率（TTM）', price_to_book:'市净率', price_to_sales:'市销率',
      price_to_sales_ttm:'市销率（TTM）', turnover_rate_pct:'换手率', total_market_value_10k_cny:'总市值',
      circulating_market_value_10k_cny:'流通市值', reported_total_revenue:'营业收入', reported_revenue:'营业收入',
      reported_net_income:'净利润', reported_operating_profit:'营业利润', reported_total_assets:'总资产',
      reported_total_liabilities:'总负债', reported_total_equity:'所有者权益', reported_operating_cashflow:'经营现金流',
      reported_free_cashflow:'自由现金流', return_on_equity_pct:'ROE', return_on_assets_pct:'ROA',
      gross_profit_margin_pct:'毛利率', debt_to_assets_pct:'资产负债率', current_ratio:'流动比率'
    }[key] || key.replaceAll('_', ' '));
    function metricValue(key, value) {
      if (typeof value !== 'number') return text(value);
      if (key.endsWith('_10k_cny')) return (value / 10000).toFixed(2) + ' 亿元';
      if (key.startsWith('reported_')) return compactAmount(value);
      if (key.endsWith('_pct')) return conciseNumber(value) + '%';
      return conciseNumber(value);
    }
    function setStatus(message, tone = 'neutral') {
      $('status').textContent = message;
      $('status').dataset.tone = tone;
    }
    function syncLocation() {
      const params = new URLSearchParams(window.location.search);
      const symbol = $('symbol').value;
      if (symbol) params.set('symbol', symbol); else params.delete('symbol');
      params.set('view', activeView);
      window.history.replaceState(null, '', window.location.pathname + '?' + params.toString());
    }
    function setActiveView(view, updateLocation = true) {
      activeView = validViews.has(view) ? view : 'overview';
      document.querySelectorAll('[data-view]').forEach(section => {
        const selected = section.dataset.view === activeView;
        section.classList.toggle('active', selected);
        section.hidden = !selected;
      });
      document.querySelectorAll('[data-view-target]').forEach(tab => {
        tab.setAttribute('aria-selected', String(tab.dataset.viewTarget === activeView));
      });
      if (updateLocation) syncLocation();
    }
    function handleTabKeydown(event) {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      const tabs = Array.from(document.querySelectorAll('[data-view-target]'));
      const current = tabs.indexOf(event.currentTarget);
      let next = current;
      if (event.key === 'ArrowLeft') next = (current - 1 + tabs.length) % tabs.length;
      if (event.key === 'ArrowRight') next = (current + 1) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      event.preventDefault();
      tabs[next].focus();
      setActiveView(tabs[next].dataset.viewTarget);
    }
    function closeWatchMenu() {
      const menu = document.querySelector('.watch-menu');
      if (menu) menu.open = false;
    }
    function opportunityDetail(factor) {
      const metrics = factor.metrics || {};
      if (factor.factor_id === 'approvals') return metrics.approvals_365d ? '近365天精确关联版号 ' + metrics.approvals_365d + ' 个，最近距今 ' + metrics.days_since_latest + ' 天。' : '本地缓存中暂无精确关联版号。';
      if (factor.factor_id === 'catalysts') return '即将发生 ' + (metrics.upcoming || 0) + ' 项，持续或待定档 ' + (metrics.ongoing_or_undated || 0) + ' 项。';
      if (factor.factor_id === 'financial') return '净利润同比 ' + (metrics.net_profit_yoy_pct == null ? 'N/A' : conciseNumber(metrics.net_profit_yoy_pct) + '%') + '，经营现金流 ' + compactAmount(metrics.operating_cashflow) + '。';
      if (factor.factor_id === 'market') return '20日 ' + pct(metrics.return_20d) + '，60日 ' + pct(metrics.return_60d) + '。';
      return factor.detail;
    }
    function renderMetrics(snapshot) {
      const market = snapshot.market;
      const latestRun = snapshot.latest_run;
      const decision = latestRun?.risk_review?.decision || latestRun?.signal?.direction;
      const cards = market ? [
        ['最新收盘', money(market.last_close, market.currency), market.last_date],
        ['区间涨跌', pct(market.period_return_pct), market.bar_count + ' 个交易日', market.period_return_pct >= 0 ? 'positive' : 'negative'],
        ['最新成交量', market.latest_volume == null ? 'N/A' : Number(market.latest_volume).toLocaleString('zh-CN'), '价格区间自 ' + market.first_date],
        ['最新决策', decision ? zh(decision) : '尚未形成', latestRun ? '研究日期 ' + latestRun.as_of_date.slice(0,10) : snapshot.artifact_counts.agent_outputs + ' 条结构化研究']
      ] : [
        ['最新收盘', 'N/A', '暂无价格数据'], ['区间涨跌', 'N/A', '暂无价格数据'], ['最新成交量', 'N/A', '暂无价格数据'], ['最新决策', decision ? zh(decision) : '尚未形成', latestRun ? '已有研究记录' : '暂无研究记录']
      ];
      $('metrics').innerHTML = cards.map(([label, value, detail, cls]) => '<div class="metric"><div class="metric-label">' + escape(label) + '</div><div class="metric-value ' + (cls || 'neutral') + '">' + escape(value) + '</div><div class="metric-detail">' + escape(detail) + '</div></div>').join('');
    }
    function renderDataHealth(health) {
      const items = health?.items || [];
      if (!items.length) { $('dataHealth').innerHTML = '<div class="empty">暂无缓存数据状态。</div>'; return; }
      const reference = health.reference_as_of_date ? '研究基准 ' + health.reference_as_of_date : '最近缓存';
      $('dataHealth').innerHTML = items.map(item => '<div class="health-item"><div class="health-title">' + escape(zh(item.label)) + '</div><div class="health-status ' + escape(item.status) + '">' + escape(zh(item.status)) + '</div><div class="health-detail">' + escape(item.detail) + (item.available_as_of_date ? ' · 可用日期 ' + escape(item.available_as_of_date) : '') + '</div></div>').join('');
      $('dataHealth').setAttribute('aria-label', '缓存数据状态：' + reference);
    }
    function renderReadiness(readiness) {
      if (!readiness) { $('readinessMeta').textContent = ''; $('readiness').innerHTML = '<li class="empty">暂无研究准备度信息。</li>'; return; }
      $('readinessMeta').textContent = zh(readiness.status) + ' · ' + readiness.required_ready + '/' + readiness.required_total + ' 必需项';
      $('readiness').innerHTML = readiness.items.map(item => '<li class="item"><div class="item-title">' + escape(zh(item.label)) + '</div><div class="item-meta">' + escape(zh(item.status)) + ' · ' + escape(item.required ? '必需' : '可选') + '</div><div class="item-summary">' + escape(item.detail) + '</div></li>').join('');
    }
    function renderWatchlistBoard(board) {
      const items = board?.items || [];
      $('watchlistMeta').textContent = board ? board.researched + '/' + board.total + ' 已完成研究' : '';
      $('watchlistBoard').innerHTML = items.length ? items.map(item => '<tr><td><button class="watch-symbol" type="button" data-watch-symbol="' + escape(item.symbol) + '">' + escape(item.symbol) + '</button></td><td>' + escape(item.last_close == null ? 'N/A' : money(item.last_close, item.currency)) + '</td><td>' + escape(item.last_price_date || 'N/A') + '</td><td><span class="board-status ' + escape(item.data_status) + '">' + escape(zh(item.data_status)) + '</span></td><td>' + escape(item.latest_research_at ? item.latest_research_at.slice(0,16).replace('T', ' ') : '暂无') + '</td><td>' + escape(zh(item.risk_decision || item.decision || '暂无')) + '</td></tr>').join('') : '<tr><td class="empty" colspan="6">自选股为空。</td></tr>';
      const watchHeader = $('watchlistBoard').closest('table').tHead.rows[0];
      if (watchHeader.cells.length === 6) { const th = document.createElement('th'); th.textContent = String.fromCharCode(26495,22359); watchHeader.insertBefore(th, watchHeader.cells[1]); }
      [...$('watchlistBoard').rows].forEach((row, index) => {
        if (!items[index]) { row.cells[0].colSpan = 7; return; }
        const sectorCell = row.insertCell(1);
        sectorCell.innerHTML = (items[index].sector_names || items[index].sectors || []).map(sector => '<span class="agent-role-badge">' + escape(sector) + '</span>').join(' ');
        if (items[index].name) row.cells[0].insertAdjacentHTML('beforeend', '<div class="item-meta">' + escape(items[index].name) + '</div>');
      });


    }
    function renderChart(market) {
      if (!market || market.series.length < 2) { $('chart').innerHTML = '<div class="empty">No cached price series available.</div>'; $('chartMeta').textContent = ''; return; }
      const values = market.series.map(point => point.close), min = Math.min(...values), max = Math.max(...values), span = Math.max(max - min, Math.max(max, 1) * .03), width = 720, height = 220, pad = 12;
      const points = market.series.map((point, index) => `${pad + index * ((width - pad * 2) / (market.series.length - 1))},${height - pad - ((point.close - min) / span) * (height - pad * 2)}`).join(' ');
      $('chart').innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Cached closing price history"><line x1="${pad}" y1="${height - pad}" x2="${width-pad}" y2="${height-pad}" stroke="#d5dfe3"/><line x1="${pad}" y1="${pad}" x2="${width-pad}" y2="${pad}" stroke="#e4ebed"/><polyline fill="none" stroke="#176f6c" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" points="${points}"/></svg>`;
      $('chartMeta').textContent = `${market.first_date} to ${market.last_date}`;
    }
    function renderCompanyProfile(profile) {
      const target = $('companyProfile');
      if (!profile || !profile.available) { target.innerHTML = '<div class="empty">暂无公司概况。</div>'; $('companyProfileMeta').textContent = ''; return; }
      const fields = [['公司名称', profile.name], ['行业', profile.industry], ['地区', profile.area], ['板块', profile.market], ['交易所', profile.exchange], ['上市日期', profile.list_date]].filter(([, value]) => value);
      target.innerHTML = fields.map(([label, value]) => '<div><span class="label">' + escape(label) + '</span><span class="value">' + escape(value) + '</span></div>').join('');
      $('companyProfileMeta').textContent = '可用日期 ' + profile.as_of_date;
    }
    let gameProductItems = [];
    let activeProductFilter = 'all';
    function renderGameProducts() {
      const filtered = gameProductItems.filter(item => activeProductFilter === 'all' || (activeProductFilter === 'live' ? item.status === 'live' || item.status === 'legacy_live' : item.status === 'pipeline'));
      $('gameProductsMeta').textContent = '显示 ' + filtered.length + ' / ' + gameProductItems.length;
      document.querySelectorAll('[data-product-filter]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.productFilter === activeProductFilter)));
      $('gameProducts').innerHTML = filtered.length ? filtered.map(item => '<tr><td><strong>' + escape(item.name) + '</strong>' + (item.aliases?.length ? '<div class="item-meta">' + escape(item.aliases.join(' / ')) + '</div>' : '') + '</td><td><span class="board-status">' + escape(zh(item.status)) + '</span></td><td>' + escape(item.genres.join(', ') || 'N/A') + '</td><td>' + escape(item.platforms.join(', ') || 'N/A') + '</td><td>' + escape(item.markets.join(', ') || 'N/A') + '</td></tr>').join('') : '<tr><td colspan="5" class="empty">当前筛选条件下没有产品。</td></tr>';
    }
    function renderGameResearch(research) {
      if (!research || !research.available) {
        $('gameBusinessMeta').textContent = '';
        $('gameBusiness').innerHTML = '<li class="empty">该股票暂无游戏行业覆盖。</li>';
        gameProductItems = [];
        renderGameProducts();
        $('gameCatalystsMeta').textContent = '';
        $('gameCatalysts').innerHTML = '<li class="empty">暂无产品催化。</li>';
        return;
      }
      const evidence = new Map((research.evidence || []).map(item => [item.evidence_id, item]));
      const sourceLinks = ids => (ids || []).map(id => evidence.get(id)).filter(Boolean).map(item => '<a href="' + escape(item.source_url) + '" target="_blank" rel="noreferrer">' + escape(item.title) + '</a>').join(' · ');
      $('gameBusinessMeta').textContent = research.company_name + ' · ' + research.as_of_date;
      const focus = research.research_focus?.length ? '<li class="item"><div class="item-title">研究重点</div><div class="tags">' + research.research_focus.map(item => '<span class="tag">' + escape(item) + '</span>').join('') + '</div></li>' : '';
      const entities = research.entities.map(item => '<li class="item"><div class="item-title">' + escape(item.name) + '</div><div class="item-meta">' + escape(zh(item.role)) + ' · 已知日期 ' + escape(item.known_as_of) + '</div><div class="item-summary">' + escape(item.relationship) + '</div><div class="item-meta">' + sourceLinks(item.evidence_ids) + '</div></li>').join('');
      $('gameBusiness').innerHTML = focus + entities;
      gameProductItems = research.products || [];
      renderGameProducts();
      $('gameCatalystsMeta').textContent = research.catalysts.length + ' 项';
      $('gameCatalysts').innerHTML = research.catalysts.length ? research.catalysts.map(view => { const item = view.catalyst; return '<li class="item"><div class="item-title">' + escape(item.title) + '</div><div class="item-meta">' + escape(zh(view.status)) + ' · ' + escape(item.category) + (item.event_date ? ' · ' + escape(item.event_date) : '') + '</div><div class="item-meta">' + sourceLinks(item.evidence_ids) + '</div></li>'; }).join('') : '<li class="empty">暂无产品催化。</li>';
    }
    function renderGameOpportunity(opportunity) {
      if (!opportunity || !opportunity.available) {
        $('gameOpportunityMeta').textContent = '数据不足';
        $('gameOpportunity').innerHTML = '<li class="empty">暂无游戏机会雷达。</li>';
        return;
      }
      $('gameOpportunityMeta').textContent = zh(opportunity.level) + ' · ' + opportunity.score + '/' + opportunity.max_score;
      $('gameOpportunity').innerHTML = opportunity.factors.map(factor => '<li class="item"><div class="item-title">' + escape(zh(factor.label)) + ' <span class="board-status ' + escape(factor.status) + '">' + escape(factor.score) + '/' + escape(factor.max_score) + '</span></div><div class="item-meta">' + escape(zh(factor.status)) + (factor.observed_as_of ? ' · ' + escape(factor.observed_as_of) : '') + '</div><div class="item-summary">' + escape(opportunityDetail(factor)) + '</div></li>').join('') + '<li class="empty">关注分数仅用于研究排序，不构成买卖或估值建议。</li>';
    }
    function renderGameOpportunityHistory(history) {
      const snapshots = history?.snapshots || [], events = history?.latest_events || [];
      $('gameOpportunityHistoryMeta').textContent = snapshots.length ? snapshots.length + ' 个日度快照' : '';
      const eventTitles = {baseline_created:'建立机会基线', level_changed:'关注等级变化', score_changed:'机会分数变化', factor_changed:'因子得分变化', new_approval:'新增关联版号'};
      const eventRows = events.map(event => '<li class="item"><div class="item-title">' + escape(eventTitles[event.event_type] || event.title) + '</div><div class="item-meta">' + escape(event.severity === 'notable' ? '重要' : '信息') + ' · ' + escape(event.as_of_date) + '</div><div class="item-summary">' + escape(event.detail) + '</div></li>').join('');
      const historyRows = snapshots.slice(0, 8).map(item => '<li class="item"><div class="item-title">' + escape(item.as_of_date) + ' <span class="board-status">' + escape(zh(item.level)) + '</span></div><div class="item-meta">分数 ' + escape(item.score) + '/' + escape(item.max_score) + '</div></li>').join('');
      $('gameOpportunityHistory').innerHTML = eventRows + historyRows || '<li class="empty">运行机会跟踪后会生成首个日度快照。</li>';
    }
    function renderGameApprovals(digest) {
      const approvals = digest?.approvals || [];
      $('gameApprovalsMeta').textContent = approvals.length ? approvals.length + ' 个精确匹配 · 最近 ' + digest.latest_approval_date : '';
      $('gameApprovals').innerHTML = approvals.length ? approvals.map(item => { const approval = item.approval; return '<tr><td>' + escape(approval.approval_date) + '</td><td><a href="' + escape(approval.source_url) + '" target="_blank" rel="noreferrer">' + escape(approval.game_name) + '</a></td><td>' + escape(zh(approval.kind)) + '</td><td>' + escape(approval.operating_entity) + '</td><td>' + escape(approval.approval_number) + '</td></tr>'; }).join('') : '<tr><td colspan="5" class="empty">本地缓存中暂无精确关联版号。</td></tr>';
    }
    function renderFundamentals(fundamentals) {
      if (!fundamentals) { $('fundamentals').innerHTML = '<div class="empty">暂无估值数据。</div>'; $('fundamentalsMeta').textContent = ''; return; }
      const excluded = new Set(['company_name','company_area','company_industry','company_market','company_exchange','company_list_date']);
      const entries = Object.entries(fundamentals.metrics || {}).filter(([key]) => !excluded.has(key)).slice(0, 12);
      $('fundamentals').innerHTML = entries.length ? entries.map(([key, value]) => '<div><span class="label">' + escape(metricLabel(key)) + '</span><span class="value">' + escape(metricValue(key, value)) + '</span></div>').join('') : '<div class="empty">最新快照没有估值指标。</div>';
      $('fundamentalsMeta').textContent = '数据日期 ' + fundamentals.provenance.as_of_date;
    }
    function renderValuationContext(context) {
      const target = $('valuationContext');
      if (!context || !context.available) {
        target.innerHTML = '<tr><td colspan="7" class="empty">有效估值样本少于20个交易日。</td></tr>';
        $('valuationContextMeta').textContent = '';
        return;
      }
      const rows = context.metrics.filter(item => item.available);
      target.innerHTML = rows.map(item => '<tr><td>' + escape(zh(item.label)) + '</td><td>' + escape(conciseNumber(item.latest)) + '</td><td>' + escape(Number(item.percentile).toFixed(1)) + '%</td><td>' + escape(conciseNumber(item.low)) + '</td><td>' + escape(conciseNumber(item.median)) + '</td><td>' + escape(conciseNumber(item.high)) + '</td><td>' + escape(item.observations) + '</td></tr>').join('');
      $('valuationContextMeta').textContent = context.daily_snapshot_count + ' 个交易日 · 截至 ' + context.as_of_date;
    }
    function renderFinancialQuality(snapshot) {
      if (!snapshot) { $('financialQuality').innerHTML = '<div class="empty">暂无财务质量数据。</div>'; $('financialQualityMeta').textContent = ''; return; }
      const preferred = ['reported_total_revenue','reported_net_income','reported_operating_cashflow','reported_free_cashflow','return_on_equity_pct','gross_profit_margin_pct','debt_to_assets_pct','current_ratio'];
      const entries = preferred.filter(key => snapshot.metrics?.[key] != null).map(key => [key, snapshot.metrics[key]]);
      $('financialQuality').innerHTML = entries.length ? entries.map(([key, value]) => '<div><span class="label">' + escape(metricLabel(key)) + '</span><span class="value">' + escape(metricValue(key, value)) + '</span></div>').join('') : '<div class="empty">财务快照没有可展示指标。</div>';
      $('financialQualityMeta').textContent = '报告期 ' + snapshot.period_end;
    }
    function renderFinancialHealth(assessment) {
      $('financialHealthMeta').textContent = zh(assessment.status) + ' · ' + assessment.score + '/4';
      $('financialHealth').innerHTML = assessment.checks.map(check => '<li class="item"><div class="item-title">' + escape(zh(check.name)) + '</div><div class="item-meta">' + escape(zh(check.status)) + ' · 当前 ' + escape(conciseNumber(check.observed)) + ' / 参考 ' + escape(conciseNumber(check.threshold)) + '</div><div class="item-summary">' + escape(check.message) + '</div></li>').join('');
    }
    function renderFinancialTrend(items) {
      $('financialTrendMeta').textContent = items.length + ' 个报告期';
      $('financialTrend').innerHTML = items.length ? items.map(item => {
        const metrics = item.metrics || {};
        return '<tr><td>' + escape(item.period_end) + '</td><td>' + escape(compactAmount(metrics.reported_total_revenue)) + '</td><td>' + escape(compactAmount(metrics.reported_net_income)) + '</td><td>' + escape(compactAmount(metrics.reported_operating_cashflow)) + '</td><td>' + escape(metrics.return_on_equity_pct == null ? 'N/A' : conciseNumber(metrics.return_on_equity_pct) + '%') + '</td></tr>';
      }).join('') : '<tr><td colspan="5" class="empty">财务报告期不足。</td></tr>';
    }
    function renderAgents(outputs) {
      const roleLabel = role => ({
        'Research Manager':'研究经理', 'Market Snapshot':'市场基线',
        'Fundamentals Snapshot':'基本面基线', 'News Snapshot':'新闻基线'
      }[role] || role);
      const confidenceLabel = value => ({high:'高置信', medium:'中等置信', low:'低置信'}[value] || value || '未标注');
      const stageRank = output => {
        const meta = output.metadata || {};
        if (meta.stage === 'manager') return 0;
        if (meta.failed) return 3;
        if (meta.provider) return 1;
        return 2;
      };
      const sectionHtml = section => {
        const bullets = (section.bullets || []).length ? '<ul>' + section.bullets.map(item => '<li>' + escape(item) + '</li>').join('') + '</ul>' : '';
        return '<section class="agent-section"><h4>' + escape(section.title) + '</h4>' + (section.summary ? '<p>' + escape(section.summary) + '</p>' : '') + bullets + '</section>';
      };
      const cardHtml = output => {
        const meta = output.metadata || {};
        const failed = Boolean(meta.failed);
        const manager = meta.stage === 'manager';
        let sections = [...(output.sections || [])];
        const thesis = output.payload && output.output_type === 'investment_thesis' ? output.payload : null;
        if (manager && thesis && !sections.length) sections = [
          {title:'基础情景', summary:thesis.base_case}, {title:'乐观情景', summary:thesis.bull_case},
          {title:'悲观情景', summary:thesis.bear_case}, {title:'潜在催化剂', bullets:thesis.catalysts || []},
          {title:'反证与失效条件', bullets:thesis.disconfirming_evidence || []}
        ];
        const risks = (output.risks || []).length ? '<section class="agent-section"><h4>风险与观察项</h4><ul>' + output.risks.map(item => '<li>' + escape(item) + '</li>').join('') + '</ul></section>' : '';
        const failureDetail = meta.validation_fields ? '未通过字段：' + meta.validation_fields : meta.failure_reason ? '失败类别：' + meta.failure_reason : '';
        const validation = failed && failureDetail ? '<section class="agent-section"><h4>结构化校验详情</h4><p>' + escape(failureDetail) + '</p></section>' : '';
        const evidence = (output.evidence || []).length ? '<div class="agent-evidence"><strong>证据：</strong>' + output.evidence.map(item => escape(item.description) + '（' + escape(item.source_id) + '）').join('；') + '</div>' : '';
        const audit = [meta.provider, meta.model, meta.latency_ms == null ? null : meta.latency_ms + 'ms'].filter(Boolean).join(' · ');
        return '<li class="item agent-card ' + (manager ? 'manager ' : '') + (failed ? 'failed' : '') + '"><details ' + (manager ? 'open' : '') + '><summary><div class="agent-card-title"><span class="agent-role-badge">' + escape(roleLabel(output.agent_role)) + '</span><span>' + escape(output.headline) + '</span><span class="agent-status-badge ' + (failed ? 'failed' : '') + '">' + escape(failed ? '已降级' : confidenceLabel(output.confidence)) + '</span></div><div class="item-meta">' + escape(output.as_of_date) + (audit ? ' · ' + escape(audit) : '') + '</div></summary><div class="agent-body"><p class="agent-lead">' + escape(output.summary) + '</p>' + sections.map(sectionHtml).join('') + validation + risks + evidence + '</div></details></li>';
      };
      const ordered = [...outputs].sort((a,b) => stageRank(a) - stageRank(b));
      const successful = outputs.filter(output => !(output.metadata || {}).failed).length;
      $('agentsMeta').textContent = outputs.length + ' 条 · ' + successful + ' 条有效';
      $('agents').innerHTML = ordered.length ? ordered.map(cardHtml).join('') : '<li class="empty">暂无结构化研究。</li>';
    }
    function renderNews(items) {
      $('newsMeta').textContent = items.length + ' 条最近事件';
      $('news').innerHTML = items.length ? items.map(item => '<li class="item"><div class="item-title">' + (item.url ? '<a href="' + escape(item.url) + '" target="_blank" rel="noreferrer">' + escape(item.title) + '</a>' : escape(item.title)) + '</div><div class="item-meta">' + escape(item.provider) + ' · ' + escape(item.published_at.slice(0,10)) + '</div>' + (item.summary ? '<div class="item-summary">' + escape(item.summary) + '</div>' : '') + '</li>').join('') : '<li class="empty">暂无公司事件。</li>';
    }
    function renderDecision(run) {
      if (!run || !run.signal) { $('decision').innerHTML = '<div class="empty">当前研究记录尚未形成手工决策。</div>'; $('decisionMeta').textContent = ''; return; }
      const signal = run.signal, review = run.risk_review;
      const rows = [
        ['方向', zh(signal.direction)], ['周期', zh(signal.horizon)], ['信心', pct(signal.confidence)], ['拟议仓位', pct(signal.proposed_position_pct)],
        ['风控结论', review ? zh(review.decision) : '尚未复核'], ['批准仓位', review ? pct(review.approved_position_pct) : 'N/A'],
        ['风险项', review ? review.breaches.length : 'N/A'], ['研究日期', run.as_of_date.slice(0, 10)]
      ];
      $('decision').innerHTML = rows.map(([label, value]) => '<div><span class="label">' + escape(label) + '</span><span class="value">' + escape(value) + '</span></div>').join('');
      $('decisionMeta').textContent = '生成时间 ' + run.generated_at.slice(0,16).replace('T', ' ');
    }
    function renderDecisionJournal(views, run) {
      const items = views || [];
      const canJournal = Boolean(run?.run_id && run?.signal);
      $('addJournalEntry').disabled = !canJournal;
      $('addJournalEntry').title = canJournal ? '' : '请选择包含手工决策的研究记录';
      $('decisionJournalEmpty').hidden = items.length > 0;
      if (!items.length) { $('decisionJournal').innerHTML = ''; return; }
      $('decisionJournal').innerHTML = items.map(view => {
        const entry = view.entry;
        const review = entry.review;
        const returnValue = review ? review.directional_return_pct : view.directional_return_pct;
        const price = review ? review.review_price : view.latest_available_price;
        const priceDate = review ? review.review_price_date : view.latest_available_price_date;
        const detail = review ? `Reviewed ${review.reviewed_on}` : `Due ${entry.review_due_date}`;
        const action = review ? '' : `<button type="button" data-journal-review="${escape(entry.entry_id)}">Record Review</button>`;
        return `<li class="item"><div class="item-title">${escape(entry.direction)} - ${escape(entry.horizon)} - ${escape(entry.symbol)}</div><div class="item-meta">${escape(view.status)} | ${escape(detail)} | Entry ${escape(money(entry.entry_price, entry.currency))} on ${escape(entry.entry_price_date)}</div><div class="item-summary">${escape(entry.rationale)}</div><div class="tags"><span class="tag">Directional return: ${escape(pct(returnValue))}</span><span class="tag">Reference: ${escape(price == null ? 'N/A' : money(price, entry.currency))}${priceDate ? ` on ${escape(priceDate)}` : ''}</span></div>${review?.note ? `<div class="item-summary">${escape(review.note)}</div>` : ''}<div class="report-actions">${action}</div></li>`;
      }).join('');
    }
    function clearReportWorkspace(message) {
      $('openReport').removeAttribute('href'); $('openReport').setAttribute('aria-disabled', 'true');
      $('exportReport').removeAttribute('href'); $('exportReport').setAttribute('aria-disabled', 'true');
      $('reportCoverage').className = 'empty'; $('reportCoverage').textContent = message;
      $('reportPreview').removeAttribute('data-report-url');
      $('reportPreview').textContent = '暂无研究报告。';
    }
    async function renderReportWorkspace(snapshot) {
      const run = snapshot.latest_run, workspace = snapshot.report_workspace;
      if (!run || !workspace?.available) { clearReportWorkspace('请选择一条研究记录。'); return; }
      const baseUrl = '/api/reports/' + encodeURIComponent(snapshot.symbol) + '/' + encodeURIComponent(run.run_id) + '.md';
      $('openReport').href = baseUrl; $('openReport').setAttribute('aria-disabled', 'false');
      $('exportReport').href = baseUrl + '?download=1'; $('exportReport').setAttribute('aria-disabled', 'false');
      $('exportReport').setAttribute('download', snapshot.symbol + '_' + run.run_id + '.md');
      const audit = workspace.run_audit;
      const adjustedCoverage = audit?.price_bar_count ? (audit.adjusted_price_bar_count / audit.price_bar_count * 100).toFixed(0) + '%' : 'N/A';
      const auditHtml = audit ? '<div class="coverage-summary">\u8fd0\u884c\u5ba1\u8ba1\uff1a' + escape(audit.narrative_mode) + ' ? ' + escape((audit.llm_provider && audit.llm_model) ? audit.llm_provider + '/' + audit.llm_model : '\u786e\u5b9a\u6027') + ' ? ' + escape(audit.price_basis) + ' ' + adjustedCoverage + ' ? ' + audit.successful_model_stages + '\u6210\u529f/' + audit.degraded_model_stages + '\u964d\u7ea7</div>' : '';
      $('reportCoverage').className = '';
      $('reportCoverage').innerHTML = '<div class="coverage-summary">核心数据覆盖：' + workspace.core_available + '/' + workspace.core_total + '</div><ul class="coverage-list">' + workspace.items.map(item => '<li class="coverage-item"><div><div class="coverage-label">' + escape(zh(item.label)) + '</div><div class="coverage-detail">' + escape(item.detail) + '</div></div><span class="coverage-status ' + (item.available ? '' : 'missing') + '">' + (item.available ? '可用' : item.optional ? '未使用' : '缺失') + '</span></li>').join('') + '</ul>';
      $('reportCoverage').innerHTML = auditHtml + $('reportCoverage').innerHTML;
      $('reportPreview').dataset.reportUrl = baseUrl;
      $('reportPreview').textContent = '展开后加载报告全文。';
      if ($('reportDisclosure').open) await loadReportPreview();
    }
    async function loadReportPreview() {
      const target = $('reportPreview');
      const url = target.dataset.reportUrl;
      if (!url || target.dataset.loadedUrl === url) return;
      target.textContent = '正在加载报告...';
      try {
        target.textContent = await fetch(url).then(response => response.ok ? response.text() : Promise.reject(response));
        target.dataset.loadedUrl = url;
      } catch (error) { target.textContent = '报告加载失败。'; }
    }
    function renderBacktest(run) {
      if (!run || !run.backtest) { $('backtest').innerHTML = '<div class="empty">当前研究记录暂无回测。</div>'; $('backtestMeta').textContent = ''; return; }
      const backtest = run.backtest, metrics = backtest.metrics;
      const rows = [
        ['总收益', pct(metrics.total_return_pct)], ['最大回撤', pct(metrics.max_drawdown_pct)], ['夏普比率', text(metrics.sharpe == null ? null : Number(metrics.sharpe).toFixed(2))], ['胜率', pct(metrics.win_rate_pct)],
        ['盈亏比', text(metrics.profit_factor == null ? null : Number(metrics.profit_factor).toFixed(2))], ['交易次数', backtest.trade_count], ['完整交易', backtest.round_trip_count], ['警告', backtest.warning_count]
      ];
      $('backtest').innerHTML = rows.map(([label, value]) => '<div><span class="label">' + escape(label) + '</span><span class="value">' + escape(value) + '</span></div>').join('');
      $('backtestMeta').textContent = '当前研究记录';
    }
    let activeSnapshot = null;
    let activeRunId = null;
    let activeJobId = null;
    let activeBatchJobIds = [];
    let watchlistSymbols = new Set();
    async function loadResearchSettings() {
      const payload = await fetch('/api/research-settings').then(response => response.ok ? response.json() : Promise.reject(response));
      const selector = $('lookbackPeriod');
      selector.replaceChildren(...payload.settings.period_presets.map(item => new Option(item.name + ' (' + item.days + ')', String(item.days))));
      selector.value = String(payload.default_lookback_days);
      $('dataProvider').value = payload.settings.preferred_data_provider;
    }


    function renderRunHistory(runs, selectedRunId) {
      const selector = $('runHistory');
      if (!runs.length) {
        selector.innerHTML = '<option value="">暂无研究记录</option>';
        selector.disabled = true;
        $('runHistoryDetail').textContent = '运行当前股票研究后会生成记录。';
        return;
      }
      selector.disabled = false;
      selector.innerHTML = '<option value="">最近一条研究记录</option>' + runs.map(run => '<option value="' + escape(run.run_id) + '">' + escape(run.as_of_date.slice(0,10)) + ' · ' + escape(run.generated_at.slice(0,16).replace('T', ' ')) + '</option>').join('');
      selector.value = selectedRunId || '';
      const selected = runs.find(run => run.run_id === selectedRunId) || runs[0];
      const scopes = [selected.has_signal ? '决策' : null, selected.has_risk_review ? '风控' : null, selected.has_backtest ? '回测' : null].filter(Boolean);
      $('runHistoryDetail').textContent = runs.length + ' 条研究记录 · ' + (scopes.join('、') || '数据快照');
    }
    function setResearchButton(isRunning) {
      $('runResearch').disabled = isRunning || !$('symbol').value;
      $('runResearch').setAttribute('aria-busy', String(isRunning && Boolean(activeJobId)));
      $('runResearch').textContent = activeJobId ? '研究进行中' : '研究当前股票';
      $('refreshWatchlistResearch').disabled = isRunning;
      $('refreshWatchlistResearch').setAttribute('aria-busy', String(Boolean(activeBatchJobIds.length)));
      $('refreshWatchlistResearch').textContent = activeBatchJobIds.length ? '正在更新自选股' : '更新全部自选股';
    }
    async function pollWatchlistRefresh() {
      if (!activeBatchJobIds.length) return;
      try {
        const payloads = await Promise.all(activeBatchJobIds.map(jobId => fetch('/api/research-jobs/' + encodeURIComponent(jobId)).then(response => response.ok ? response.json() : Promise.reject(response))));
        const jobs = payloads.map(payload => payload.job);
        const pending = jobs.filter(job => job.status === 'queued' || job.status === 'running');
        const completed = jobs.length - pending.length;
        setStatus('正在更新自选股：' + completed + '/' + jobs.length, 'busy');
        if (pending.length) { window.setTimeout(pollWatchlistRefresh, 800); return; }
        const failed = jobs.filter(job => job.status === 'failed');
        activeBatchJobIds = [];
        setResearchButton(false);
        setStatus(failed.length ? '自选股更新完成，' + failed.length + ' 个任务失败。' : '已更新 ' + jobs.length + ' 只自选股。', failed.length ? 'warning' : 'success');
        await refreshSymbols();
        await loadSnapshot({preserveStatus:true});
      } catch (error) {
        activeBatchJobIds = [];
        setResearchButton(false);
        setStatus('自选股更新失败。', 'error');
      }
    }
    async function startWatchlistRefresh() {
      if (activeJobId || activeBatchJobIds.length) return;
      setResearchButton(true);
      setStatus('正在启动自选股更新...', 'busy');
      try {
        const payload = await fetch('/api/watchlist-refresh', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({lookback_days: Number($('lookbackPeriod').value), data_provider: $('dataProvider').value, narrative_mode: $('narrativeMode').value})}).then(response => response.ok ? response.json() : Promise.reject(response));
        activeBatchJobIds = payload.jobs.map(job => job.job_id);
        if (!activeBatchJobIds.length) { setResearchButton(false); setStatus('自选股为空。', 'warning'); return; }
        setResearchButton(true);
        await pollWatchlistRefresh();
      } catch (error) {
        activeBatchJobIds = [];
        setResearchButton(false);
        setStatus('无法启动自选股更新。', 'error');
      }
    }
    async function pollResearchJob() {
      if (!activeJobId) return;
      const payload = await fetch('/api/research-jobs/' + encodeURIComponent(activeJobId)).then(response => response.ok ? response.json() : Promise.reject(response));
      const job = payload.job;
      if (job.status === 'queued' || job.status === 'running') {
        const phases = {
          queued: '排队中', collecting_normalized_evidence: '收集标准化证据',
          configuring_llm_research: '检查模型配置', running_research_workflow: '运行确定性研究',
          'multi_agent:fundamentals': '基本面分析师', 'multi_agent:market': '技术与市场分析师',
          'multi_agent:game_news': '新闻、游戏产品与版号分析师', 'multi_agent:valuation': '估值分析师',
          'multi_agent:bull': 'Bull 研究员', 'multi_agent:bear': 'Bear 研究员',
          'multi_agent:manager': 'Research Manager 综合', 'multi_agent:complete': '整理多智能体结果'
        };
        setStatus('正在研究 ' + job.request.symbol + ' · ' + (phases[job.phase] || '运行中'), 'busy');
        window.setTimeout(pollResearchJob, 800);
        return;
      }
      activeJobId = null;
      setResearchButton(false);
      if (job.status === 'succeeded') {
        setStatus(job.request.symbol + ' 研究完成。', 'success');
        await refreshSymbols(job.request.symbol);
        await loadSnapshot({preserveStatus:true});
      } else {
        setStatus('研究失败：' + (job.error || '数据源不可用'), 'error');
      }
    }
    function updateDecisionFields() {
      const hasDecision = Boolean($('decisionDirection').value);
      document.querySelectorAll('.decision-conditional').forEach(field => { field.hidden = !hasDecision; });
      $('decisionDirection').setAttribute('aria-expanded', String(hasDecision));
    }
    function manualSignalPayload() {
      const direction = $('decisionDirection').value;
      if (!direction) return null;
      const confidence = Number($('decisionConfidence').value) / 100;
      const position = Number($('decisionPosition').value) / 100;
      if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1 || !Number.isFinite(position) || position < 0 || position > 1) {
        throw new Error('信心和仓位必须在0到100之间。');
      }
      const rationale = $('decisionRationale').value.trim();
      if (!rationale) throw new Error('请填写判断依据。');
      return {
        direction,
        horizon: $('decisionHorizon').value,
        confidence,
        proposed_position_pct: position,
        rationale
      };
    }
    async function startResearch() {
      const symbol = $('symbol').value;
      if (!symbol || activeJobId) return;
      setResearchButton(true);
      setStatus('正在启动 ' + symbol + ' 研究...', 'busy');
      try {
        const payload = await fetch('/api/research-jobs', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({symbol, lookback_days: Number($('lookbackPeriod').value), data_provider: $('dataProvider').value, narrative_mode: $('narrativeMode').value, manual_signal: manualSignalPayload()})}).then(response => response.ok ? response.json() : Promise.reject(response));
        activeJobId = payload.job.job_id;
        setResearchButton(true);
        await pollResearchJob();
      } catch (error) {
        activeJobId = null;
        setResearchButton(false);
        setStatus(error?.message || '无法启动当前股票研究。', 'error');
      }
    }
    async function addJournalEntry() {
      const run = activeSnapshot?.latest_run;
      const reviewDueDate = $('journalReviewDue').value;
      if (!run?.run_id || !run?.signal || !reviewDueDate) {
        $('status').textContent = '请选择包含手工决策的研究记录并设置复盘日期。';
        return;
      }
      $('addJournalEntry').disabled = true;
      try {
        const payload = await fetch('/api/decision-journal', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({symbol: activeSnapshot.symbol, run_id: run.run_id, review_due_date: reviewDueDate})}).then(response => response.ok ? response.json() : response.json().then(body => Promise.reject(new Error(body.error || 'Unable to journal decision'))));
        $('status').textContent = `Decision journaled for ${payload.entry.symbol}.`;
        await loadSnapshot();
      } catch (error) {
        $('status').textContent = error.message || 'Unable to journal the selected decision.';
        renderDecisionJournal(activeSnapshot?.decision_journal, activeSnapshot?.latest_run);
      }
    }
    async function recordJournalReview(entryId) {
      const reviewedOn = $('journalReviewedOn').value;
      if (!reviewedOn) { $('status').textContent = '请先选择实际复盘日期。'; return; }
      try {
        const payload = await fetch(`/api/decision-journal/${encodeURIComponent(entryId)}/review`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({reviewed_on: reviewedOn, note: $('journalReviewNote').value.trim()})}).then(response => response.ok ? response.json() : response.json().then(body => Promise.reject(new Error(body.error || 'Unable to record review'))));
        $('journalReviewNote').value = '';
        $('status').textContent = `Review recorded for ${payload.entry.symbol}.`;
        await loadSnapshot();
      } catch (error) { $('status').textContent = error.message || 'Unable to record the review.'; }
    }
    async function refreshSymbols(preferredSymbol) {
      const payload = await fetch('/api/symbols').then(response => response.json());
      const current = preferredSymbol || $('symbol').value || requestedSymbol;
      $('symbol').innerHTML = payload.symbols.length ? payload.symbols.map(symbol => `<option value="${escape(symbol)}">${escape(symbol)}</option>`).join('') : '<option value="">No symbols</option>';
      if (payload.symbols.includes(current)) $('symbol').value = current;
      syncLocation();
    }
    async function refreshWatchlistBoard() {
      const payload = await fetch('/api/watchlist-board').then(response => response.json());
      renderWatchlistBoard(payload);
    }
    async function refreshWatchlist() {
      const payload = await fetch('/api/watchlist').then(response => response.json());
      watchlistSymbols = new Set(payload.entries.map(entry => entry.symbol));
      $('removeSymbol').disabled = !watchlistSymbols.has($('symbol').value);
    }
    async function loadSnapshot(options = {}) {
      const symbol = $('symbol').value;
      if (!symbol) {
        setStatus('暂无可用股票，请先添加自选股。', 'warning');
        $('headerAsOf').textContent = '数据日期：--';
        renderMetrics({artifact_counts:{}});
        renderDataHealth(null); renderReadiness(null); renderChart(null); renderCompanyProfile(null); renderGameResearch(null);
        renderGameOpportunity(null); renderGameOpportunityHistory(null); renderGameApprovals(null); renderFundamentals(null);
        renderValuationContext(null); renderFinancialQuality(null); renderFinancialHealth({status:'missing',score:0,checks:[]});
        renderFinancialTrend([]); renderAgents([]); renderNews([]); renderDecision(null); renderDecisionJournal([], null);
        renderBacktest(null); renderRunHistory([], null); clearReportWorkspace('请选择一条研究记录。');
        await refreshWatchlistBoard();
        return;
      }
      if (!options.preserveStatus) setStatus('正在读取 ' + symbol + ' 的本地研究数据...', 'busy');
      try {
        const runQuery = activeRunId ? '&run_id=' + encodeURIComponent(activeRunId) : '';
        const snapshot = await fetch('/api/snapshot?symbol=' + encodeURIComponent(symbol) + runQuery).then(response => response.ok ? response.json() : Promise.reject(response));
        const companyName = snapshot.company_profile?.name || snapshot.game_research?.company_name || snapshot.symbol;
        $('title').textContent = companyName + ' · ' + snapshot.symbol;
        document.title = companyName + ' · 个人股票投研';
        $('headerAsOf').textContent = '数据日期：' + (snapshot.market?.last_date || snapshot.game_opportunity?.as_of_date || '--');
        $('overviewMeta').textContent = zh(snapshot.game_opportunity?.level || 'insufficient_data') + ' · ' + (snapshot.game_opportunity?.score || 0) + '/' + (snapshot.game_opportunity?.max_score || 12) + ' · 准备度 ' + (snapshot.research_readiness?.required_ready || 0) + '/' + (snapshot.research_readiness?.required_total || 0);
        if (!options.preserveStatus) setStatus(snapshot.has_data ? '已读取 ' + snapshot.symbol + ' 的本地研究数据。' : '未找到 ' + snapshot.symbol + ' 的研究数据。', snapshot.has_data ? 'success' : 'warning');
        renderMetrics(snapshot); renderDataHealth(snapshot.data_health); renderReadiness(snapshot.research_readiness); renderChart(snapshot.market); renderCompanyProfile(snapshot.company_profile); renderGameResearch(snapshot.game_research); renderGameOpportunity(snapshot.game_opportunity); renderGameOpportunityHistory(snapshot.game_opportunity_history); renderGameApprovals(snapshot.game_approvals); renderFundamentals(snapshot.fundamentals); renderValuationContext(snapshot.valuation_context); renderFinancialQuality(snapshot.financial_quality); renderFinancialHealth(snapshot.financial_health); renderFinancialTrend(snapshot.financial_quality_history); renderAgents(snapshot.agent_outputs); renderNews(snapshot.news); activeSnapshot = snapshot; renderDecision(snapshot.latest_run); renderDecisionJournal(snapshot.decision_journal, snapshot.latest_run); renderBacktest(snapshot.latest_run); renderRunHistory(snapshot.runs, activeRunId); await renderReportWorkspace(snapshot);
        await refreshWatchlist();
        await refreshWatchlistBoard();
        setResearchButton(Boolean(activeJobId || activeBatchJobIds.length));
        syncLocation();
      } catch (error) {
        setStatus('本地研究数据读取失败。', 'error');
      }
    }
    async function addToWatchlist() {
      const symbol = $('watchSymbol').value.trim().toUpperCase();
      if (!symbol) { setStatus('请输入股票代码。', 'warning'); return; }
      setStatus('正在添加 ' + symbol + '...', 'busy');
      try {
        const response = await fetch('/api/watchlist', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({symbol})});
        if (!response.ok) throw new Error('添加失败');
        $('watchSymbol').value = '';
        activeRunId = null;
        await refreshSymbols(symbol);
        await loadSnapshot({preserveStatus:true});
        setStatus(symbol + ' 已加入自选股。', 'success');
      } catch (error) {
        setStatus(symbol + ' 添加失败。', 'error');
      }
    }
    async function removeFromWatchlist() {
      const symbol = $('symbol').value;
      if (!symbol || !window.confirm('从自选股移除 ' + symbol + '？')) return;
      setStatus('正在移除 ' + symbol + '...', 'busy');
      try {
        const response = await fetch('/api/watchlist?symbol=' + encodeURIComponent(symbol), {method:'DELETE'});
        if (!response.ok) throw new Error('移除失败');
        activeRunId = null;
        await refreshSymbols();
        await loadSnapshot({preserveStatus:true});
        setStatus(symbol + ' 已从自选股移除。', 'success');
      } catch (error) {
        setStatus(symbol + ' 移除失败。', 'error');
      }
    }
    function initializeJournalDates() {
      const now = new Date();
      const reviewDue = new Date(now);
      reviewDue.setDate(reviewDue.getDate() + 90);
      const toIsoDate = value => value.toISOString().slice(0, 10);
      $('journalReviewDue').value = toIsoDate(reviewDue);
      $('journalReviewedOn').value = toIsoDate(now);
    }
    async function start() {
      try {
        await refreshSymbols();
        await refreshWatchlist();
        await refreshWatchlistBoard();
        setResearchButton(Boolean(activeJobId));
      } catch (error) { $('symbol').innerHTML = '<option value="">本地存储不可用</option>'; }
      await loadSnapshot();
    }
    $('addJournalEntry').addEventListener('click', addJournalEntry);
    $('decisionJournal').addEventListener('click', async event => { const button = event.target.closest('[data-journal-review]'); if (!button) return; await recordJournalReview(button.dataset.journalReview); });
    $('runResearch').addEventListener('click', startResearch);
    $('refresh').addEventListener('click', async () => { closeWatchMenu(); await loadSnapshot(); });
    $('symbol').addEventListener('change', async () => { activeRunId = null; syncLocation(); await loadSnapshot(); });
    $('runHistory').addEventListener('change', async () => { activeRunId = $('runHistory').value || null; await loadSnapshot(); });
    $('addSymbol').addEventListener('click', async () => { await addToWatchlist(); closeWatchMenu(); });
    $('removeSymbol').addEventListener('click', async () => { await removeFromWatchlist(); closeWatchMenu(); });
    $('watchlistBoard').addEventListener('click', async event => { const button = event.target.closest('[data-watch-symbol]'); if (!button) return; activeRunId = null; await refreshSymbols(button.dataset.watchSymbol); syncLocation(); await loadSnapshot(); });
    $('watchSymbol').addEventListener('keydown', async event => { if (event.key === 'Enter') await addToWatchlist(); });
    $('refreshWatchlistResearch').addEventListener('click', startWatchlistRefresh);
    $('reportDisclosure').addEventListener('toggle', async () => { if ($('reportDisclosure').open) await loadReportPreview(); });
    document.querySelectorAll('[data-view-target]').forEach(tab => {
      tab.addEventListener('click', () => setActiveView(tab.dataset.viewTarget));
      tab.addEventListener('keydown', handleTabKeydown);
    });
    document.querySelectorAll('[data-product-filter]').forEach(button => button.addEventListener('click', () => {
      activeProductFilter = button.dataset.productFilter;
      renderGameProducts();
    }));
    $('decisionDirection').addEventListener('change', updateDecisionFields);
    document.addEventListener('click', event => {
      const menu = document.querySelector('.watch-menu');
      if (menu?.open && !menu.contains(event.target)) closeWatchMenu();
    });
    document.addEventListener('keydown', event => { if (event.key === 'Escape') closeWatchMenu(); });
    setActiveView(activeView, false);
    updateDecisionFields();
    initializeJournalDates();
    loadResearchSettings().catch(() => {}).finally(start);
  </script>
</body>
</html>"""


if __name__ == "__main__":
    raise SystemExit(main())
