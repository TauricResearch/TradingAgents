"""Koral Equities: loopback-only dashboard for the existing paper trading ledger.

This module NEVER connects to a brokerage and NEVER fabricates trading data.
The scan action delegates to the existing paper CLI and cannot place real orders.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytz

from .cli import DEFAULT_PATH, DEFAULT_TICKERS, last_safe_session, read_book
from .engine import Book
from .discovery_web import DiscoveryRuntime, latest as discovery_latest, safe_report as safe_discovery_report

STATIC = Path(__file__).with_name("web")
_REPORT_RE = re.compile(r"^[a-zA-Z0-9_./-]+$")
_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,16}$")


def snapshot(book: Book, state_path: Path) -> dict:
    """Return only ledger-backed data. Preserve zero-history as an empty series."""
    r = book.settings
    equity = book.equity()
    positions = []
    invested = 0.0
    open_cost = 0.0
    for p in sorted(book.positions.values(), key=lambda p: p["ticker"]):
        value = p["shares"] * p["mark_usd"] * p["mark_gbp_per_usd"]
        invested += value
        open_cost += p["cost_gbp"]
        positions.append({
            "ticker": p["ticker"],
            "shares": p["shares"],
            "entry_date": p["entry_date"],
            "entry_usd": p["entry_usd"],
            "mark_usd": p["mark_usd"],
            "stop_usd": p["stop_usd"],
            "value_gbp": round(value, 2),
            "cost_gbp": round(p["cost_gbp"], 2),
            "unrealized_gbp": round(value - p["cost_gbp"], 2),
            "held_sessions": p["held_sessions"],
            "planned_risk_gbp": round(p.get("planned_risk_gbp", 0), 2),
        })
    ratings = {}
    for event in book.events:
        if event.get("type") == "AGENT_RATING" and event.get("ticker"):
            ratings[event["ticker"]] = {
                "ticker": event["ticker"],
                "rating": event.get("rating", "REVIEW"),
                "date": event["date"],
                "reference_close_usd": event.get("reference_close_usd"),
            }
    session = last_safe_session()
    history = list(book.equity_history)
    prior_equity = (history[-2]["equity_gbp"] if len(history) >= 2 else r.initial_gbp)
    today_gbp = history[-1]["equity_gbp"] - prior_equity if history else 0.0
    report_dir = state_path.parent / "reports"
    reports = []
    if report_dir.is_dir():
        for path in sorted(report_dir.rglob("complete_report.html"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
            relative = path.relative_to(report_dir).as_posix()
            if _REPORT_RE.fullmatch(relative):
                reports.append({"name": path.parent.name, "url": "/reports/" + relative})
    return {
        "account": {
            "name": "Koral Equities",
            "mode": "PAPER ONLY",
            "base_currency": "GBP",
            "started": book.started,
            "last_session": book.last_session,
            "equity_gbp": round(equity, 2),
            "cash_gbp": round(book.cash_gbp, 2),
            "invested_gbp": round(invested, 2),
            "open_cost_gbp": round(open_cost, 2),
            "unrealized_gbp": round(invested - open_cost, 2),
            "return_gbp": round(equity - r.initial_gbp, 2),
            "return_pct": (equity / r.initial_gbp - 1) * 100,
            "session_pnl_gbp": round(today_gbp, 2),
            "drawdown_pct": (1 - equity / book.peak_gbp) * 100,
            "peak_gbp": round(book.peak_gbp, 2),
            "halted": book.halted,
            "positions_count": len(positions),
            "pending_count": len(book.orders),
            "closed_count": len(book.completed),
            "risk_per_trade_pct": 100 * r.risk_fraction,
            "max_combined_risk_pct": 100 * r.combined_risk_fraction,
            "max_drawdown_pct": 100 * r.drawdown_halt_fraction,
            "max_positions": r.max_positions,
            "max_name_pct": 100 * r.max_name_fraction,
            "stop_pct": 8,
            "analysis_available": session >= book.started,
            "safe_session": session,
        },
        "positions": positions,
        "orders": list(book.orders),
        "closed": list(book.completed),
        "history": history,
        "events": list(reversed(book.events[-100:])),
        "ratings": sorted(ratings.values(), key=lambda t: t["ticker"]),
        "watchlist": DEFAULT_TICKERS,
        "reports": reports,
    }


def _csv_bytes(records: list[dict], fields: list[str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        # Prevent spreadsheet formula injection when importing exported journals.
        safe = {k: "'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@"))
                else v for k, v in record.items()}
        writer.writerow(safe)
    return output.getvalue().encode("utf-8-sig")


def _check_ai_provider() -> None:
    """Fail early when default API mode has no key; never read/print credentials."""
    from tradingagents.default_config import DEFAULT_CONFIG

    provider = str(DEFAULT_CONFIG.get("llm_provider", "openai")).strip().lower()
    if provider == "openai" and not os.environ.get("OPENAI_API_KEY", "").strip():
        raise ValueError(
            "OpenAI API mode is selected but OPENAI_API_KEY is missing. "
            "If you already signed in with ChatGPT, save "
            "TRADINGAGENTS_LLM_PROVIDER=chatgpt in your project .env file, "
            "restart the Koral Equities dashboard, and retry. "
            "Otherwise configure a separate OpenAI API key."
        )


class ScanRuntime:
    """Own the paper CLI child process without exposing any brokerage endpoint."""

    def __init__(self, state_path: Path, working_dir: Path | None = None):
        self.state_path = state_path
        self.working_dir = working_dir or Path.cwd()
        self.lock = threading.Lock()
        self.process: subprocess.Popen | None = None
        self.started_at: str | None = None
        self.log_path = state_path.parent / "dashboard_scan.log"
        self.last_error: str | None = None

    def start(self, tickers: list[str]) -> None:
        if not tickers or len(tickers) > 25 or len(set(tickers)) != len(tickers):
            raise ValueError("Select between 1 and 25 unique tickers")
        if any(not _TICKER_RE.fullmatch(ticker) for ticker in tickers):
            raise ValueError("Invalid ticker")
        if not self.state_path.exists():
            raise FileNotFoundError("Initialize the £10,000 paper account first")
        book = read_book(self.state_path)
        if last_safe_session() < book.started:
            raise ValueError("No completed trading session yet; wait until after 17:30 New York")
        _check_ai_provider()
        with self.lock:
            if self.process and self.process.poll() is None:
                raise RuntimeError("An analysis is already running")
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            # Overwrite the previous scan log, not the persistent paper ledger.
            with self.log_path.open("w", encoding="utf-8") as log:
                command = [sys.executable, "-m", "tradingagents.paper.cli", "--state",
                           str(self.state_path), "run", "--tickers", *tickers]
                self.process = subprocess.Popen(
                    command, cwd=str(self.working_dir), stdout=log,
                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                )
            self.started_at = datetime.now(tz=pytz.UTC).isoformat()
            self.last_error = None

    def status(self) -> dict:
        with self.lock:
            process = self.process
            running = process is not None and process.poll() is None
            rc = None if process is None or running else process.returncode
            log = ""
            if self.log_path.exists() and process is not None:
                # Recent output only. Avoid loading arbitrarily large model logs.
                with self.log_path.open("rb") as file:
                    file.seek(max(0, file.seek(0, 2) - 12000))
                    log = file.read().decode("utf-8", errors="replace")
            return {"running": running, "finished": process is not None and not running,
                    "returncode": rc, "started_at": self.started_at,
                    "log": log, "error": self.last_error}


def make_handler(state_path: Path, runtime: ScanRuntime, discovery: DiscoveryRuntime | None = None):
    # A separate research sandbox: never references the paper-account book.
    discovery = discovery or DiscoveryRuntime()
    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "KoralEquities/1.0"

        def log_message(self, message: str, *args):
            # No credentials, request body or model outputs in access logs.
            return

        def respond(self, payload: bytes, code: int = 200, content_type: str = "application/json",
                    disposition: str | None = None, report: bool = False):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            if report:
                self.send_header("Content-Security-Policy", "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:")
            else:
                self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            if disposition:
                self.send_header("Content-Disposition", disposition)
            self.end_headers()
            self.wfile.write(payload)

        def respond_json(self, obj, code: int = 200):
            self.respond(json.dumps(obj, allow_nan=False).encode("utf-8"), code)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ("/", "/index.html", "/styles.css", "/app.js"):
                key = "index.html" if path == "/" else path.removeprefix("/")
                data = (STATIC / key).read_bytes()
                mimetype = mimetypes.guess_type(key)[0] or "application/octet-stream"
                self.respond(data, content_type=mimetype + ("; charset=utf-8" if "text" in mimetype or key.endswith(".js") else ""))
                return
            if path == "/api/state":
                try:
                    self.respond_json(snapshot(read_book(state_path), state_path))
                except (FileNotFoundError, ValueError) as exc:
                    self.respond_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            if path == "/api/scan-status":
                self.respond_json(runtime.status())
                return
            if path == "/api/discovery/state":
                self.respond_json(discovery_latest(discovery.home))
                return
            if path == "/api/discovery/status":
                self.respond_json(discovery.status())
                return
            if path.startswith("/discovery/reports/"):
                parts=path.split("/")
                file=safe_discovery_report(discovery.home,parts[3],parts[4]) if len(parts)==6 and parts[5]=="complete_report.html" else None
                if file is None:
                    self.respond_json({"error":"Research report not found"},HTTPStatus.NOT_FOUND)
                else:
                    self.respond(file.read_bytes(),content_type="text/html; charset=utf-8",report=True)
                return
            if path in ("/api/export/closed", "/api/export/positions"):
                try:
                    view = snapshot(read_book(state_path), state_path)
                except (FileNotFoundError, ValueError) as exc:
                    self.respond_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
                    return
                if path.endswith("closed"):
                    data, cols, filename = view["closed"], ["ticker", "shares", "entry_date", "exit_date", "reason", "entry_usd", "exit_usd", "pnl_gbp", "return_fraction"], "koral_closed_trades.csv"
                else:
                    data, cols, filename = view["positions"], ["ticker", "shares", "entry_date", "entry_usd", "mark_usd", "stop_usd", "value_gbp", "unrealized_gbp", "held_sessions"], "koral_positions.csv"
                self.respond(_csv_bytes(data, cols), content_type="text/csv; charset=utf-8",
                             disposition=f'attachment; filename="{filename}"')
                return
            if path.startswith("/reports/"):
                relative = unquote(path.removeprefix("/reports/"))
                directory = (state_path.parent / "reports").resolve()
                file = (directory / relative).resolve()
                if not _REPORT_RE.fullmatch(relative) or file.name != "complete_report.html" or not file.is_relative_to(directory) or not file.is_file():
                    self.respond_json({"error": "Report not found"}, HTTPStatus.NOT_FOUND)
                    return
                self.respond(file.read_bytes(), content_type="text/html; charset=utf-8", report=True)
                return
            self.respond_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self):
            if self.path == "/api/discovery/start":
                host = self.headers.get("Host","")
                origin = self.headers.get("Origin","")
                hosts={f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
                if host not in hosts or origin not in {"http://"+h for h in hosts} or self.headers.get("X-Koral-Action")!="discovery":
                    self.respond_json({"error":"Forbidden"},HTTPStatus.FORBIDDEN)
                    return
                if self.headers.get("Content-Type","").split(";")[0].strip()!="application/json":
                    self.respond_json({"error":"JSON required"},HTTPStatus.BAD_REQUEST)
                    return
                try:
                    size=int(self.headers.get("Content-Length","0"))
                    if not 1<=size<=200:
                        raise ValueError("Invalid discovery request")
                    config=json.loads(self.rfile.read(size))
                    if type(config) is not dict or set(config)!={"max_symbols","ai"}:
                        raise ValueError("Expected scan size and AI report count")
                    discovery.start(config["max_symbols"],config["ai"])
                    self.respond_json({"ok":True,"mode":"RESEARCH_ONLY","message":"Independent stock discovery started"},HTTPStatus.ACCEPTED)
                except (ValueError,RuntimeError,TypeError,KeyError,json.JSONDecodeError,OSError) as exc:
                    self.respond_json({"error":str(exc)},HTTPStatus.CONFLICT)
                return
            if self.path != "/api/scan":
                self.respond_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin", "")
            good_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            good_origins = {"http://" + h for h in good_hosts}
            if host not in good_hosts or origin not in good_origins or self.headers.get("X-Koral-Action") != "scan":
                self.respond_json({"error": "Forbidden"}, HTTPStatus.FORBIDDEN)
                return
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                self.respond_json({"error": "JSON required"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 1 <= size <= 2048:
                    raise ValueError("Invalid payload size")
                payload = json.loads(self.rfile.read(size))
                tickers = payload.get("tickers", DEFAULT_TICKERS)
                if not isinstance(tickers, list) or not all(isinstance(x, str) for x in tickers):
                    raise ValueError("Invalid tickers")
                runtime.start(tickers)
                self.respond_json({"ok": True, "message": "Paper analysis started"}, HTTPStatus.ACCEPTED)
            except (ValueError, FileNotFoundError, RuntimeError, json.JSONDecodeError) as exc:
                self.respond_json({"error": str(exc)}, HTTPStatus.CONFLICT)

    return DashboardHandler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Koral Equities | premium local paper desk")
    parser.add_argument("--state", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("--port must be between 1024 and 65535")
    state_path = args.state.expanduser().resolve()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(state_path, ScanRuntime(state_path), DiscoveryRuntime()))
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Koral Equities paper dashboard: {url}")
    print("Local only. No real broker connection. Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
