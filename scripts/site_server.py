#!/usr/bin/env python3
"""TradingAgents site for https://tradingagents.quiltyapp.com (ROBIN-1685 / 1686).

Local bind 127.0.0.1:8794; nginx terminates TLS. Auth mirrors agents.quiltyapp.com:
webbit Spina SSO → /sso/callback (shared agentRobin state/agent_ops/sso_secret).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(os.environ.get("TRADINGAGENTS_ROOT", Path(__file__).resolve().parents[1]))
AGENTROBIN_ROOT = Path(
    os.environ.get("AGENTROBIN_ROOT", "/home/marckoby/dev/agentRobin")
)
PORT = int(os.environ.get("TRADINGAGENTS_SITE_PORT", "8794"))
BIND = os.environ.get("TRADINGAGENTS_SITE_BIND", "127.0.0.1")
PUBLIC_URL = os.environ.get(
    "TRADINGAGENTS_PUBLIC_URL", "https://TradingAgents.quiltyapp.com"
).rstrip("/")
# Prefer branded casing; DNS/TLS treat hostnames case-insensitively.
ALLOWED_PUBLIC_HOSTS = {
    "tradingagents.quiltyapp.com",
    "TradingAgents.quiltyapp.com",
}
SSO_URL = os.environ.get(
    "TRADINGAGENTS_SSO_URL",
    "https://webbit.quiltyapp.com/agentrobin/internal/agents_sso",
)
AUTH = os.environ.get("TRADINGAGENTS_SITE_AUTH", "sso")  # sso | disabled
COOKIE = "tradingagents_session"
SESSION_HOURS = 12
RUNS_DIR = ROOT / "data" / "site_runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)
WEB_HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def canonical_public_host(host: str | None) -> str:
    """Always brand as TradingAgents.quiltyapp.com (DNS/TLS are case-insensitive).

    Clients and HTTP/2 usually lowercase the Host header, so we must not echo
    that casing back into SSO return_to / redirects.
    """
    h = (host or "").split(":")[0].strip()
    if h.lower() == "tradingagents.quiltyapp.com" or h in ALLOWED_PUBLIC_HOSTS:
        return "TradingAgents.quiltyapp.com"
    return urllib.parse.urlparse(PUBLIC_URL).hostname or "TradingAgents.quiltyapp.com"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def sso_secret() -> str:
    path = AGENTROBIN_ROOT / "state" / "agent_ops" / "sso_secret"
    if not path.is_file() or path.stat().st_size < 32:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32), encoding="utf-8")
        path.chmod(0o600)
    return path.read_text(encoding="utf-8").strip()


def sso_sign(payload: dict) -> str:
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    mac = _b64url(
        hmac.new(sso_secret().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
    )
    return f"{body}.{mac}"


def sso_verify(token: str) -> dict | None:
    try:
        body, mac = token.split(".", 1)
    except ValueError:
        return None
    expected = _b64url(
        hmac.new(sso_secret().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected, mac):
        return None
    try:
        payload = json.loads(_b64url_decode(body))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict) or int(payload.get("exp", 0)) <= int(time.time()):
        return None
    return payload


def bridge_cli(*args: str) -> dict | list:
    cmd = ["ruby", str(AGENTROBIN_ROOT / "scripts" / "tradingagents_bridge.rb"), *args]
    env = os.environ.copy()
    env["AGENTROBIN_ROOT"] = str(AGENTROBIN_ROOT)
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}")
    return json.loads(proc.stdout)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Handler(BaseHTTPRequestHandler):
    server_version = "TradingAgentsSite/1.0"

    def log_message(self, fmt: str, *args) -> None:  # quieter
        (LOG_DIR / "site.log").open("a", encoding="utf-8").write(
            f"{iso_now()} {self.address_string()} {fmt % args}\n"
        )

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text: str, status: int = 200) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str, status: int = 302) -> None:
        self.send_response(status)
        self.send_header("Location", location)
        self.end_headers()

    def _public_base(self) -> str:
        host = canonical_public_host(self.headers.get("Host"))
        return f"https://{host}"

    def _session_user(self) -> dict | None:
        if AUTH == "disabled":
            return {"email": "local-dev"}
        raw = self.headers.get("Cookie", "")
        cookie = SimpleCookie()
        cookie.load(raw)
        morsel = cookie.get(COOKIE)
        if not morsel:
            return None
        return sso_verify(urllib.parse.unquote(morsel.value))

    def _require_session(self, api: bool = False) -> dict | None:
        user = self._session_user()
        if user:
            return user
        base = self._public_base()
        path = self.path if self.path.startswith("/") else "/"
        login = f"{SSO_URL}?return_to={urllib.parse.quote(base + path, safe='')}"
        if api:
            self._json({"error": "login required", "login": login}, status=401)
        else:
            self._redirect(login)
        return None

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8") or "{}")

    def do_HEAD(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            return
        base = self._public_base()
        self.send_response(302)
        self.send_header(
            "Location",
            f"{SSO_URL}?return_to={urllib.parse.quote(base + '/', safe='')}",
        )
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/healthz":
            self._json({"ok": True, "service": "tradingagents-site", "at": iso_now()})
            return

        if path == "/sso/callback":
            token = (qs.get("token") or [""])[0]
            payload = sso_verify(token)
            if not payload:
                self._html("SSO token invalid or expired. Reload to sign in again.", status=403)
                return
            session = sso_sign(
                {
                    "email": payload.get("email", "user"),
                    "exp": int(time.time()) + SESSION_HOURS * 3600,
                }
            )
            self.send_response(302)
            self.send_header(
                "Set-Cookie",
                f"{COOKIE}={urllib.parse.quote(session)}; Path=/; Max-Age={SESSION_HOURS * 3600}; "
                "Secure; HttpOnly; SameSite=Lax",
            )
            ret = (qs.get("return_to") or ["/"])[0]
            if not ret.startswith("/") or ret.startswith("//"):
                ret = "/"
            self.send_header("Location", self._public_base() + ret)
            self.end_headers()
            return

        if path == "/logout":
            self.send_response(200)
            self.send_header(
                "Set-Cookie",
                f"{COOKIE}=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax",
            )
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Signed out.")
            return

        if path == "/api/accounts":
            if not self._require_session(api=True):
                return
            try:
                accounts = bridge_cli("accounts")
                self._json({"accounts": accounts, "viewer": self._session_user()})
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, status=500)
            return

        if path == "/api/portfolio":
            if not self._require_session(api=True):
                return
            account = (qs.get("account") or [""])[0]
            if not account:
                self._json({"error": "account required"}, status=422)
                return
            try:
                book = bridge_cli("portfolio", "--account", account, "--strict")
                self._json({"account": account, "portfolio": book})
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, status=500)
            return

        if path == "/api/runs":
            if not self._require_session(api=True):
                return
            runs = sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:50]
            items = []
            for path_run in runs:
                try:
                    items.append(json.loads(path_run.read_text(encoding="utf-8")))
                except json.JSONDecodeError:
                    continue
            self._json({"runs": items})
            return

        if path.startswith("/api/runs/"):
            if not self._require_session(api=True):
                return
            run_id = path.rsplit("/", 1)[-1]
            file = RUNS_DIR / f"{run_id}.json"
            if not file.is_file():
                self._json({"error": "not found"}, status=404)
                return
            self._json(json.loads(file.read_text(encoding="utf-8")))
            return

        if path in ("/", "/index.html"):
            if not self._require_session(api=False):
                return
            self._html(WEB_HTML)
            return

        self._json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path != "/api/analyze":
            self._json({"error": "not found"}, status=404)
            return
        if not self._require_session(api=True):
            return
        try:
            body = self._read_json()
        except json.JSONDecodeError as exc:
            self._json({"error": f"invalid JSON: {exc}"}, status=422)
            return

        ticker = str(body.get("ticker") or "").strip().upper()
        account = str(body.get("account") or "").strip()
        analysts = str(body.get("analysts") or "market,news,fundamentals").strip()
        if not ticker:
            self._json({"error": "ticker required"}, status=422)
            return

        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
        run = {
            "id": run_id,
            "status": "queued",
            "ticker": ticker,
            "account": account or None,
            "analysts": analysts,
            "created_at": iso_now(),
            "viewer": (self._session_user() or {}).get("email"),
            "log": "",
            "error": None,
        }
        run_path = RUNS_DIR / f"{run_id}.json"
        run_path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")

        def worker() -> None:
            run["status"] = "running"
            run["started_at"] = iso_now()
            run_path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
            cmd = [
                str(ROOT / ".venv" / "bin" / "tradingagents")
                if (ROOT / ".venv" / "bin" / "tradingagents").is_file()
                else "tradingagents",
                "--ticker",
                ticker,
                "--analysts",
                analysts,
                "--no-checkpoint",
                "--save",
                "--no-show",
            ]
            if account:
                cmd.extend(["--account", account])
            env = os.environ.copy()
            env["AGENTROBIN_ROOT"] = str(AGENTROBIN_ROOT)
            env["TRADINGAGENTS_ROOT"] = str(ROOT)
            # Non-interactive: prefer env provider already in .env
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=int(os.environ.get("TRADINGAGENTS_ANALYZE_TIMEOUT", "1800")),
                    check=False,
                )
                run["log"] = (proc.stdout or "")[-20000:]
                run["stderr"] = (proc.stderr or "")[-8000:]
                run["exit_code"] = proc.returncode
                run["status"] = "ok" if proc.returncode == 0 else "failed"
                if proc.returncode != 0:
                    run["error"] = (proc.stderr or proc.stdout or "failed")[-2000:]
            except Exception as exc:  # noqa: BLE001
                run["status"] = "failed"
                run["error"] = str(exc)
            run["finished_at"] = iso_now()
            run_path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")

        threading.Thread(target=worker, daemon=True).start()
        self._json({"ok": True, "run": run})


def main() -> None:
    sso_secret()  # ensure shared secret exists for webbit
    httpd = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"TradingAgents site http://{BIND}:{PORT}/ → {PUBLIC_URL} auth={AUTH}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
