"""A small browser interface for running and reading TradingAgents reports."""

from __future__ import annotations

import argparse
import base64
import binascii
import hmac
import ipaddress
import json
import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path

from cli.prompts import detect_asset_type, parse_analysis_date, parse_analysts, parse_ticker
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

logger = logging.getLogger(__name__)
_MAX_REQUEST_BYTES = 16_384
_MAX_SAVED_JOBS = 25
_STATIC_ASSETS = {
    "/static/web.css": ("web.css", "text/css; charset=utf-8"),
    "/static/web.js": ("web.js", "text/javascript; charset=utf-8"),
}
_ANALYST_CHOICES = ("market", "sentiment", "news", "fundamentals")
_AUTH_REALM = "TradingAgents"


@dataclass(frozen=True)
class WebCredentials:
    username: str
    password: str


def _web_credentials() -> WebCredentials | None:
    username = os.environ.get("TRADINGAGENTS_WEB_USERNAME", "")
    password = os.environ.get("TRADINGAGENTS_WEB_PASSWORD", "")
    if not username and not password:
        return None
    if not username or not password:
        raise ValueError("Set both TRADINGAGENTS_WEB_USERNAME and TRADINGAGENTS_WEB_PASSWORD.")
    if ":" in username or any(ord(char) < 32 for char in username):
        raise ValueError("TRADINGAGENTS_WEB_USERNAME cannot contain a colon or control characters.")
    if len(password) < 20:
        raise ValueError("TRADINGAGENTS_WEB_PASSWORD must be at least 20 characters.")
    return WebCredentials(username, password)


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def parse_run_request(payload: object) -> dict:
    """Validate the browser's run options using the same parsers as the CLI."""
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")

    ticker = payload.get("ticker")
    trade_date = payload.get("date")
    analysts = payload.get("analysts")
    if not isinstance(ticker, str):
        raise ValueError("Ticker must be text.")
    if not isinstance(trade_date, str):
        raise ValueError("Date must be text.")
    if not isinstance(analysts, list) or not all(isinstance(item, str) for item in analysts):
        raise ValueError("Analysts must be a list of names.")
    if len(analysts) > len(_ANALYST_CHOICES):
        raise ValueError("Too many analysts selected.")
    if len(set(analysts)) != len(analysts):
        raise ValueError("Each analyst can only be selected once.")

    ticker = parse_ticker(ticker)
    trade_date = parse_analysis_date(trade_date)
    asset_type = detect_asset_type(ticker)
    selected = parse_analysts(",".join(analysts), asset_type)
    return {
        "ticker": ticker,
        "date": trade_date,
        "asset_type": asset_type,
        "analysts": selected,
    }


class AnalysisService:
    """Runs one analysis at a time and retains a bounded set of job results."""

    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._active_job: str | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tradingagents-web")

    def start(self, request: dict) -> dict:
        with self._lock:
            if self._active_job is not None:
                raise RuntimeError("An analysis is already running.")
            self._prune_jobs()
            job_id = uuid.uuid4().hex
            self._jobs[job_id] = {
                "id": job_id,
                "ticker": request["ticker"],
                "date": request["date"],
                "status": "queued",
                "error": None,
                "report_path": None,
            }
            self._active_job = job_id
            try:
                self._executor.submit(self._run, job_id, request)
            except Exception:
                self._active_job = None
                del self._jobs[job_id]
                raise
            return self._public_job(self._jobs[job_id])

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return self._public_job(job) if job else None

    def report(self, job_id: str) -> Path | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job["status"] != "complete":
                return None
            return job["report_path"]

    def _run(self, job_id: str, request: dict) -> None:
        with self._lock:
            self._jobs[job_id]["status"] = "running"
        try:
            graph = TradingAgentsGraph(
                selected_analysts=request["analysts"],
                config=DEFAULT_CONFIG.copy(),
                debug=False,
            )
            final_state, _rating = graph.propagate(
                request["ticker"], request["date"], asset_type=request["asset_type"].value
            )
            report_dir = graph.default_report_path(request["ticker"])
            graph.save_reports(final_state, request["ticker"], save_path=report_dir, html=True)
            with self._lock:
                job = self._jobs[job_id]
                job["status"] = "complete"
                job["report_path"] = report_dir / "complete_report.html"
        except Exception:
            logger.exception(
                "Browser analysis failed for %s on %s", request["ticker"], request["date"]
            )
            with self._lock:
                job = self._jobs[job_id]
                job["status"] = "failed"
                job["error"] = "Analysis failed. Check the web server logs for details."
        finally:
            with self._lock:
                self._active_job = None

    def _prune_jobs(self) -> None:
        completed = [
            job_id
            for job_id, job in self._jobs.items()
            if job_id != self._active_job and job["status"] in ("complete", "failed")
        ]
        for job_id in completed[: -_MAX_SAVED_JOBS + 1]:
            del self._jobs[job_id]

    @staticmethod
    def _public_job(job: dict) -> dict:
        result = {key: value for key, value in job.items() if key != "report_path"}
        if job["status"] == "complete":
            result["report_url"] = f"/api/runs/{job['id']}/report"
        return result


class TradingAgentsHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self, address, service: AnalysisService, credentials: WebCredentials | None = None
    ):
        super().__init__(address, TradingAgentsRequestHandler)
        self.service = service
        self.credentials = credentials


class TradingAgentsRequestHandler(BaseHTTPRequestHandler):
    server: TradingAgentsHTTPServer
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path == "/healthz":
            self._send_json({"status": "ok"})
            return
        if not self._authorized():
            return
        if self.path == "/":
            self._send_asset("index.html", "text/html; charset=utf-8")
        elif self.path in _STATIC_ASSETS:
            name, content_type = _STATIC_ASSETS[self.path]
            self._send_asset(name, content_type)
        elif self.path == "/api/config":
            cfg = DEFAULT_CONFIG
            self._send_json(
                {
                    "provider": cfg.get("quick_think_provider") or cfg["llm_provider"],
                    "model": cfg["quick_think_llm"],
                }
            )
        elif self.path.startswith("/api/runs/"):
            self._get_run(self.path.removeprefix("/api/runs/"))
        else:
            self.send_error(404)

    def do_POST(self):
        if not self._authorized():
            return
        if self.path != "/api/runs":
            self.send_error(404)
            return
        if self.headers.get_content_type() != "application/json":
            self.close_connection = True
            self._send_json({"error": "Content-Type must be application/json."}, status=415)
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.close_connection = True
            self._send_json({"error": "A valid Content-Length header is required."}, status=400)
            return
        if length < 0 or length > _MAX_REQUEST_BYTES:
            self.close_connection = True
            self._send_json({"error": "Request body is too large."}, status=413)
            return
        try:
            payload = json.loads(self.rfile.read(length))
            request = parse_run_request(payload)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=400)
            return
        try:
            job = self.server.service.start(request)
        except RuntimeError as exc:
            self._send_json({"error": str(exc)}, status=409)
            return
        self._send_json(job, status=202)

    def _authorized(self) -> bool:
        credentials = self.server.credentials
        if credentials is None:
            return True
        authorization = self.headers.get("Authorization", "")
        scheme, _, encoded = authorization.partition(" ")
        if scheme.lower() == "basic" and len(encoded) <= 4096:
            try:
                decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError):
                decoded = ""
            username, separator, password = decoded.partition(":")
            valid = (
                bool(separator)
                and hmac.compare_digest(
                    username.encode("utf-8"), credentials.username.encode("utf-8")
                )
                and hmac.compare_digest(
                    password.encode("utf-8"), credentials.password.encode("utf-8")
                )
            )
            if valid:
                return True
        self._send(
            b'{"error":"Authentication required."}',
            "application/json; charset=utf-8",
            status=401,
            headers={
                "WWW-Authenticate": f'Basic realm="{_AUTH_REALM}", charset="UTF-8"',
                "X-Content-Type-Options": "nosniff",
            },
        )
        return False

    def _get_run(self, path: str) -> None:
        job_id, separator, suffix = path.partition("/")
        if not job_id or (separator and suffix != "report"):
            self.send_error(404)
            return
        if separator:
            report = self.server.service.report(job_id)
            if report is None:
                self.send_error(404)
                return
            try:
                content = report.read_bytes()
            except OSError:
                logger.exception("Could not read generated report %s", report)
                self.send_error(500)
                return
            self._send(
                content,
                "text/html; charset=utf-8",
                headers={
                    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
                    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
                    "X-Content-Type-Options": "nosniff",
                    "Referrer-Policy": "no-referrer",
                },
            )
            return
        job = self.server.service.get(job_id)
        if job is None:
            self.send_error(404)
            return
        self._send_json(job)

    def _send_asset(self, name: str, content_type: str) -> None:
        content = files("cli").joinpath("static", name).read_bytes()
        self._send(
            content,
            content_type,
            headers={
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; "
                "style-src 'self'; connect-src 'self'; base-uri 'none'; "
                "form-action 'self'; frame-ancestors 'none'",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            },
        )

    def _send_json(self, payload: dict, status: int = 200) -> None:
        self._send(json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", status)

    def _send(self, body: bytes, content_type: str, status: int = 200, headers: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        logger.info("%s - %s", self.address_string(), format % args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TradingAgents browser interface.")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default: 127.0.0.1; use behind an authenticated proxy)",
    )
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        credentials = _web_credentials()
    except ValueError as exc:
        parser.error(str(exc))
    if not _is_loopback_host(args.host) and credentials is None:
        parser.error(
            "Non-loopback access requires TRADINGAGENTS_WEB_USERNAME and "
            "TRADINGAGENTS_WEB_PASSWORD (at least 20 characters)."
        )
    server = TradingAgentsHTTPServer((args.host, args.port), AnalysisService(), credentials)
    print(f"TradingAgents web UI listening at http://{args.host}:{args.port}/")
    if args.host not in ("127.0.0.1", "::1", "localhost"):
        print("Warning: protect remote access with an authenticated HTTPS reverse proxy.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TradingAgents web UI.")
    finally:
        server.server_close()
        server.service._executor.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
