#!/usr/bin/env python3
"""TradingAgents site for https://TradingAgents.quiltyapp.com (ROBIN-1685 / 1686).

Local bind 127.0.0.1:8794; nginx terminates TLS. Auth mirrors agents.quiltyapp.com:
webbit Spina SSO → /sso/callback (shared agentRobin state/agent_ops/sso_secret).

Deep-link autolaunch (from webbit quote pages):
  GET /start?ticker=VOO&account=FakeAcct.01  → queues research, redirects to /runs/<id>
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tradingagents.market_time import market_today_iso

ROOT = Path(os.environ.get("TRADINGAGENTS_ROOT", Path(__file__).resolve().parents[1]))
AGENTROBIN_ROOT = Path(
    os.environ.get("AGENTROBIN_ROOT", "/home/marckoby/dev/agentRobin")
)
PORT = int(os.environ.get("TRADINGAGENTS_SITE_PORT", "8794"))
BIND = os.environ.get("TRADINGAGENTS_SITE_BIND", "127.0.0.1")
PUBLIC_URL = os.environ.get(
    "TRADINGAGENTS_PUBLIC_URL", "https://TradingAgents.quiltyapp.com"
).rstrip("/")
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
ACCOUNT_COOKIE = "tradingagents_account"
SESSION_HOURS = 12
RUNS_DIR = ROOT / "data" / "site_runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)
WEB_DIR = ROOT / "web"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR = Path(
    os.environ.get(
        "TRADINGAGENTS_RESULTS_DIR",
        Path.home() / ".tradingagents" / "logs",
    )
)

_RATING_RE = re.compile(
    r"(?<![a-z])rating\b[^:\-\u2010-\u2015]*[:\-\u2010-\u2015][\s*]*(\w+)",
    re.IGNORECASE,
)
_RATINGS = {"buy", "overweight", "hold", "underweight", "sell"}


def canonical_public_host(host: str | None) -> str:
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


def analysis_date_today() -> str:
    """US equity calendar date (not host-local) so CLI accepts site --date near midnight ET."""
    return market_today_iso()


def web_text(name: str) -> str:
    return (WEB_DIR / name).read_text(encoding="utf-8")


def run_path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def load_run(run_id: str) -> dict | None:
    path = run_path(run_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def save_run(run: dict) -> None:
    run_path(run["id"]).write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")


def list_runs(*, ticker: str | None = None, limit: int = 80) -> list[dict]:
    items: list[dict] = []
    for path in sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if ticker and str(row.get("ticker") or "").upper() != ticker.upper():
            continue
        items.append(summarize_run(row))
        if len(items) >= limit:
            break
    return items


def summarize_run(run: dict) -> dict:
    """Compact fields for tables / API lists."""
    return {
        "id": run.get("id"),
        "status": run.get("status"),
        "ticker": run.get("ticker"),
        "account": run.get("account"),
        "created_at": run.get("created_at"),
        "finished_at": run.get("finished_at"),
        "viewer": run.get("viewer"),
        "rating": run.get("rating"),
        "conclusion": (run.get("conclusion") or "")[:280],
        "date": run.get("date"),
        "error": (run.get("error") or "")[:200] or None,
        "has_report": bool(run.get("report_html") or run.get("report_md")),
    }


def _extract_rating(text: str) -> str | None:
    if not text:
        return None
    found = [m.group(1).capitalize() for m in _RATING_RE.finditer(text) if m.group(1).lower() in _RATINGS]
    if found and len(set(found)) == 1:
        return found[0]
    return found[0] if found else None


def _latest_report_dir(ticker: str, after_ts: float | None = None) -> Path | None:
    reports = RESULTS_DIR / "reports"
    if not reports.is_dir():
        # Also check per-ticker date folders for complete_report.*
        ticker_dir = RESULTS_DIR / ticker.upper()
        if ticker_dir.is_dir():
            candidates = sorted(
                ticker_dir.rglob("complete_report.md"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for md in candidates:
                if after_ts and md.stat().st_mtime < after_ts - 5:
                    continue
                return md.parent
        return None
    prefix = f"{ticker.upper()}_"
    dirs = [
        p
        for p in reports.iterdir()
        if p.is_dir() and p.name.upper().startswith(prefix)
    ]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for d in dirs:
        if after_ts and d.stat().st_mtime < after_ts - 5:
            continue
        if (d / "complete_report.md").is_file() or (d / "complete_report.html").is_file():
            return d
    return dirs[0] if dirs else None


def enrich_run_artifacts(run: dict, *, started_monotonic: float | None = None) -> None:
    """Attach rating / conclusion / report paths from on-disk CLI output."""
    ticker = str(run.get("ticker") or "").upper()
    if not ticker:
        return
    after = None
    if started_monotonic is not None:
        # Convert approx wall time: started_at ISO is better when present.
        pass
    started_at = run.get("started_at")
    after_ts = None
    if started_at:
        try:
            after_ts = datetime.fromisoformat(started_at.replace("Z", "+00:00")).timestamp()
        except ValueError:
            after_ts = None

    report_dir = _latest_report_dir(ticker, after_ts=after_ts)
    decision_text = ""
    if report_dir:
        md = report_dir / "complete_report.md"
        html = report_dir / "complete_report.html"
        decision = report_dir / "5_portfolio" / "decision.md"
        if decision.is_file():
            decision_text = decision.read_text(encoding="utf-8", errors="replace")
        elif md.is_file():
            decision_text = md.read_text(encoding="utf-8", errors="replace")
        run["report_dir"] = str(report_dir)
        if md.is_file():
            run["report_md"] = str(md)
        if html.is_file():
            run["report_html"] = str(html)
            run["report_url"] = f"/runs/{run['id']}/report"

    blob = "\n".join(
        [
            decision_text,
            run.get("log") or "",
            run.get("stderr") or "",
        ]
    )
    rating = _extract_rating(decision_text) or _extract_rating(blob)
    if rating:
        run["rating"] = rating
    if decision_text.strip():
        # First meaningful paragraph as conclusion teaser.
        paras = [p.strip() for p in re.split(r"\n\s*\n", decision_text) if p.strip()]
        run["conclusion"] = (paras[0] if paras else decision_text.strip())[:1200]
        run["decision"] = decision_text[-20000:]
    elif run.get("error"):
        run["conclusion"] = str(run["error"])[:500]


def _env_blank(env: dict[str, str], key: str) -> bool:
    return not str(env.get(key, "")).strip()


def load_site_env() -> dict[str, str]:
    """Process env + .env, filling blank unattended CLI knobs the site requires."""
    env = os.environ.copy()
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            # Fill missing or empty keys from .env (empty systemd values used to
            # block setdefault and trip unattended_gaps).
            if k and _env_blank(env, k):
                env[k] = v
    env["AGENTROBIN_ROOT"] = str(AGENTROBIN_ROOT)
    env["TRADINGAGENTS_ROOT"] = str(ROOT)
    for key, value in (
        ("TRADINGAGENTS_OUTPUT_LANGUAGE", "English"),
        ("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "1"),
        ("TRADINGAGENTS_MAX_RISK_ROUNDS", "1"),
        ("TRADINGAGENTS_LLM_PROVIDER", "openai"),
        ("TRADINGAGENTS_DEEP_THINK_LLM", "gpt-4o"),
        ("TRADINGAGENTS_QUICK_THINK_LLM", "gpt-4o-mini"),
        ("TRADINGAGENTS_NO_UPDATE_CHECK", "1"),
    ):
        if _env_blank(env, key):
            env[key] = value
    return env


def queue_analyze(
    *,
    ticker: str,
    account: str | None,
    analysts: str,
    viewer: str | None,
    analysis_date: str | None = None,
) -> dict:
    ticker = ticker.strip().upper()
    account = (account or "").strip() or None
    analysts = (analysts or "market,news,fundamentals").strip()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
    analysis_date = analysis_date or analysis_date_today()
    run = {
        "id": run_id,
        "status": "queued",
        "ticker": ticker,
        "account": account,
        "analysts": analysts,
        "date": analysis_date,
        "created_at": iso_now(),
        "viewer": viewer,
        "log": "",
        "error": None,
        "rating": None,
        "conclusion": None,
    }
    save_run(run)

    def worker() -> None:
        run["status"] = "running"
        run["started_at"] = iso_now()
        save_run(run)
        cmd = [
            str(ROOT / ".venv" / "bin" / "tradingagents")
            if (ROOT / ".venv" / "bin" / "tradingagents").is_file()
            else "tradingagents",
            "--ticker",
            ticker,
            "--date",
            analysis_date,
            "--analysts",
            analysts,
            "--no-checkpoint",
            "--save",
            "--no-show",
            "--html",
        ]
        if account:
            cmd.extend(["--account", account])
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                env=load_site_env(),
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
        enrich_run_artifacts(run)
        save_run(run)

    threading.Thread(target=worker, daemon=True).start()
    return run


class Handler(BaseHTTPRequestHandler):
    server_version = "TradingAgentsSite/1.1"

    def log_message(self, fmt: str, *args) -> None:
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
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str, status: int = 302, extra_cookies: list[str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Location", location)
        for c in extra_cookies or []:
            self.send_header("Set-Cookie", c)
        self.end_headers()

    def _public_base(self) -> str:
        host = canonical_public_host(self.headers.get("Host"))
        return f"https://{host}"

    def _cookies(self) -> SimpleCookie:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:  # noqa: BLE001
            pass
        return cookie

    def _session_user(self) -> dict | None:
        if AUTH == "disabled":
            return {"email": "local-dev"}
        morsel = self._cookies().get(COOKIE)
        if not morsel:
            return None
        return sso_verify(urllib.parse.unquote(morsel.value))

    def _sticky_account(self) -> str | None:
        morsel = self._cookies().get(ACCOUNT_COOKIE)
        if not morsel:
            return None
        val = urllib.parse.unquote(morsel.value).strip()
        return val or None

    def _account_cookie(self, account: str) -> str:
        return (
            f"{ACCOUNT_COOKIE}={urllib.parse.quote(account)}; Path=/; "
            f"Max-Age={30 * 24 * 3600}; Secure; SameSite=Lax"
        )

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

    def _render_run_page(self, run: dict) -> str:
        tpl = web_text("run.html")
        past = list_runs(ticker=str(run.get("ticker") or ""), limit=40)
        past = [r for r in past if r.get("id") != run.get("id")]
        payload = {
            "run": run,
            "past": past,
            "viewer": self._session_user() or {},
        }
        return tpl.replace("__BOOTSTRAP__", json.dumps(payload))

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
                    "uid": payload.get("uid") or payload.get("user_id"),
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

        # Autolaunch: queue research immediately, land on the run page.
        if path == "/start":
            user = self._require_session(api=False)
            if not user:
                return
            ticker = (qs.get("ticker") or qs.get("symbol") or [""])[0].strip().upper()
            if not ticker:
                self._redirect("/")
                return
            account = (qs.get("account") or [""])[0].strip() or self._sticky_account()
            analysts = (qs.get("analysts") or ["market,news,fundamentals"])[0]
            run = queue_analyze(
                ticker=ticker,
                account=account,
                analysts=analysts,
                viewer=user.get("email"),
            )
            cookies = []
            if account:
                cookies.append(self._account_cookie(account))
            self._redirect(f"/runs/{run['id']}", extra_cookies=cookies)
            return

        if path == "/api/accounts":
            if not self._require_session(api=True):
                return
            try:
                accounts = bridge_cli("accounts")
                self._json(
                    {
                        "accounts": accounts,
                        "viewer": self._session_user(),
                        "sticky_account": self._sticky_account(),
                    }
                )
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
            ticker = (qs.get("ticker") or [""])[0].strip().upper() or None
            self._json({"runs": list_runs(ticker=ticker)})
            return

        if path.startswith("/api/runs/"):
            if not self._require_session(api=True):
                return
            run_id = path.rsplit("/", 1)[-1]
            run = load_run(run_id)
            if not run:
                self._json({"error": "not found"}, status=404)
                return
            self._json(run)
            return

        m = re.fullmatch(r"/runs/([^/]+)/report", path)
        if m:
            if not self._require_session(api=False):
                return
            run = load_run(m.group(1))
            if not run or not run.get("report_html"):
                self._json({"error": "report not found"}, status=404)
                return
            html_path = Path(run["report_html"])
            if not html_path.is_file():
                self._json({"error": "report missing on disk"}, status=404)
                return
            self._html(html_path.read_text(encoding="utf-8", errors="replace"))
            return

        m = re.fullmatch(r"/runs/([^/]+)/?", path)
        if m:
            if not self._require_session(api=False):
                return
            run = load_run(m.group(1))
            if not run:
                self._html("Run not found.", status=404)
                return
            self._html(self._render_run_page(run))
            return

        if path in ("/", "/index.html"):
            if not self._require_session(api=False):
                return
            # Legacy deep-link: ?ticker=&analyze=1 → /start (no waiting for form).
            ticker = (qs.get("ticker") or qs.get("symbol") or [""])[0].strip()
            analyze = (qs.get("analyze") or qs.get("run") or [""])[0] in ("1", "true", "yes")
            if ticker and analyze:
                q = urllib.parse.urlencode(
                    {
                        k: (qs.get(k) or [""])[0]
                        for k in ("ticker", "symbol", "account", "analysts")
                        if (qs.get(k) or [""])[0]
                    }
                )
                self._redirect(f"/start?{q}")
                return
            self._html(web_text("index.html"))
            return

        self._json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path != "/api/analyze":
            self._json({"error": "not found"}, status=404)
            return
        user = self._require_session(api=True)
        if not user:
            return
        try:
            body = self._read_json()
        except json.JSONDecodeError as exc:
            self._json({"error": f"invalid JSON: {exc}"}, status=422)
            return

        ticker = str(body.get("ticker") or "").strip().upper()
        account = str(body.get("account") or "").strip() or self._sticky_account()
        analysts = str(body.get("analysts") or "market,news,fundamentals").strip()
        if not ticker:
            self._json({"error": "ticker required"}, status=422)
            return
        date = str(body.get("date") or "").strip() or None
        run = queue_analyze(
            ticker=ticker,
            account=account,
            analysts=analysts,
            viewer=user.get("email"),
            analysis_date=date,
        )
        if account:
            # Mirror sticky account for subsequent visits.
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Set-Cookie", self._account_cookie(account))
            body_bytes = json.dumps({"ok": True, "run": run, "redirect": f"/runs/{run['id']}"}).encode(
                "utf-8"
            )
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)
            return
        self._json({"ok": True, "run": run, "redirect": f"/runs/{run['id']}"})


def main() -> None:
    sso_secret()
    httpd = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"TradingAgents site http://{BIND}:{PORT}/ → {PUBLIC_URL} auth={AUTH}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
