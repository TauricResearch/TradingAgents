"""Standalone JSON API backing the Next.js web app (stdlib only).

Endpoints (all JSON):
  GET  /api/options            providers/analysts/depths/languages/tickers
  GET  /api/models?provider=&mode=   live model list (or static catalog)
  GET  /api/settings/keys      provider key status (masked, never values)
  POST /api/settings/keys      {"env": ..., "value": ...} -> saved to .env live
  POST /api/settings/test      {"provider": ..., "key"?} -> connectivity check
  GET  /api/sessions           previous runs + saved reports
  GET  /api/session?id=        files of one session (capped)
  GET  /api/state              live run snapshot, or {"active": false}

Started via ``tradingagents web`` or automatically in browser mode.
Port: TRADINGAGENTS_API_PORT (default 8787).
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# LLM/agent output is full of unicode (⏱, arrows, md). On Windows the console
# defaults to cp1252, which turns any such print into a UnicodeEncodeError
# that kills the run thread — force UTF-8 for server processes.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests
from dotenv import find_dotenv, set_key

API_DEFAULT_PORT = 8787
_FILE_CHAR_CAP = 100_000
_LOG_TAIL_LINES = 500


def _json(handler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler):
    try:
        length = int(handler.headers.get("Content-Length", 0))
    except ValueError:
        return {}
    if not length:
        return {}
    try:
        return json.loads(handler.rfile.read(length).decode("utf-8") or "{}")
    except Exception:
        return {}


def _provider_options():
    from cli.utils import _llm_provider_table
    from tradingagents.llm_clients.api_key_env import get_api_key_env
    from tradingagents.llm_clients.openai_client import OPENAI_COMPATIBLE_PROVIDERS

    out = []
    for display, key, url in _llm_provider_table():
        env_var = get_api_key_env(key)
        spec = OPENAI_COMPATIBLE_PROVIDERS.get(key.lower())
        key_optional = bool(spec is not None and spec.key_optional)
        out.append(
            {
                "display": display,
                "key": key,
                "url": url,
                "keyEnv": env_var,
                "keyOptional": key_optional or env_var is None,
                "keySet": bool(env_var and os.environ.get(env_var)),
            }
        )
    return out


def _model_list(provider, mode="quick"):
    from cli.utils import _fetch_live_models, provider_default_url
    from tradingagents.llm_clients.api_key_env import get_api_key_env
    from tradingagents.llm_clients.model_catalog import get_model_options

    env_var = get_api_key_env(provider)
    api_key = os.environ.get(env_var) if env_var else None
    live = _fetch_live_models(provider.lower(), provider_default_url(provider), api_key)
    if live:
        return {"models": [{"name": n, "id": m} for n, m in live], "source": "live"}
    try:
        static = get_model_options(provider, mode if mode in ("quick", "deep") else "quick")
    except KeyError:
        static = [("Custom model ID", "custom")]
    return {"models": [{"name": n, "id": m} for n, m in static], "source": "catalog"}


def _test_key(provider, api_key):
    """Check a key against the provider's list endpoint.

    Returns (ok, message, count). Never raises.
    """
    from cli.utils import provider_default_url

    pk = provider.lower()
    if pk == "ollama":
        base = (provider_default_url("ollama") or "").rstrip("/v1").rstrip("/")
        try:
            resp = requests.get(base + "/api/tags", timeout=10)
            resp.raise_for_status()
            n = len(resp.json().get("models", []))
            return True, f"Connected — {n} local model(s) listed.", n
        except Exception as exc:
            return False, f"Ollama unreachable: {exc}", 0
    if pk in ("anthropic", "google", "bedrock", "azure"):
        env_note = "saved" if api_key else "missing"
        return (
            False,
            f"{provider} exposes no key-check endpoint; API key is {env_note}. "
            "Connectivity is verified on the first real call.",
            0,
        )
    url = provider_default_url(provider)
    if not url:
        return False, f"No endpoint known for provider '{provider}'.", 0
    if not api_key:
        return False, "No API key provided or saved.", 0
    try:
        resp = requests.get(
            url.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
    except Exception as exc:
        return False, f"Request failed: {exc}", 0
    if resp.status_code == 401:
        return False, "Invalid key (HTTP 401 from /models).", 0
    if resp.status_code >= 400:
        snippet = resp.text[:300].replace("\n", " ")
        return False, f"HTTP {resp.status_code} from /models: {snippet}", 0
    try:
        models = resp.json().get("data", [])
    except Exception as exc:
        return False, f"Unexpected /models response: {exc}", 0
    return True, f"Connected — {len(models)} model(s) listed.", len(models)


def _read_text_capped(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"<unreadable: {exc}>"
    if len(text) > _FILE_CHAR_CAP:
        text = text[:_FILE_CHAR_CAP] + "\n\n… (truncated)"
    return text


def _session_roots():
    from tradingagents.default_config import DEFAULT_CONFIG

    roots = []
    results = Path(DEFAULT_CONFIG["results_dir"])
    if results.is_dir():
        roots.append((results, "run"))
    saved = Path.cwd() / "reports"
    if saved.is_dir():
        roots.append((saved, "saved"))
    return roots


def _list_sessions():
    sessions = []
    for root, kind in _session_roots():
        if kind == "run":
            # <results>/<ticker>/<date>/ with message_tool.log or reports/
            for ticker_dir in sorted(root.iterdir()):
                if not ticker_dir.is_dir():
                    continue
                for date_dir in sorted(ticker_dir.iterdir()):
                    if not date_dir.is_dir():
                        continue
                    log = date_dir / "message_tool.log"
                    rep = date_dir / "reports"
                    if not log.exists() and not rep.is_dir():
                        continue
                    sessions.append(
                        {
                            "id": f"run|{ticker_dir.name}|{date_dir.name}",
                            "kind": kind,
                            "ticker": ticker_dir.name,
                            "date": date_dir.name,
                            "mtime": date_dir.stat().st_mtime,
                        }
                    )
        else:
            for run_dir in sorted(root.iterdir()):
                if not run_dir.is_dir():
                    continue
                if not (run_dir / "complete_report.md").exists():
                    continue
                sessions.append(
                    {
                        "id": f"saved|{run_dir.name}",
                        "kind": kind,
                        "ticker": run_dir.name.split("_")[0],
                        "date": run_dir.name,
                        "mtime": run_dir.stat().st_mtime,
                    }
                )
    sessions.sort(key=lambda s: s["mtime"], reverse=True)
    return sessions


def _resolve_session(session_id):
    """Map a session id back to a directory, contained in a known root."""
    parts = session_id.split("|")
    for root, kind in _session_roots():
        if kind == "run" and len(parts) == 3 and parts[0] == "run":
            candidate = root / parts[1] / parts[2]
        elif kind == "saved" and len(parts) == 2 and parts[0] == "saved":
            candidate = root / parts[1]
        else:
            continue
        try:
            resolved = candidate.resolve()
            if resolved.is_dir() and str(resolved).startswith(str(root.resolve())):
                return resolved, kind
        except Exception:
            continue
    return None, None


def _session_files(session_dir: Path, kind: str):
    files = []
    if kind == "saved":
        for md in sorted(session_dir.rglob("*.md")):
            files.append(
                {"path": str(md.relative_to(session_dir)), "content": _read_text_capped(md)}
            )
        return files
    for md in sorted((session_dir / "reports").glob("*.md")) if (session_dir / "reports").is_dir() else []:
        files.append(
            {"path": f"reports/{md.name}", "content": _read_text_capped(md)}
        )
    log = session_dir / "message_tool.log"
    if log.exists():
        try:
            lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = "\n".join(lines[-_LOG_TAIL_LINES:])
            files.append({"path": "message_tool.log", "content": tail, "truncated": len(lines) > _LOG_TAIL_LINES})
        except Exception as exc:
            files.append({"path": "message_tool.log", "content": f"<unreadable: {exc}>"})
    return files


class _Handler(BaseHTTPRequestHandler):
    server_version = "TradingAgentsAPI/1"

    def log_message(self, *args):
        pass

    def _cors(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._cors()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        if path == "/api/options":
            from cli.utils import POPULAR_TICKERS

            return _json(
                self,
                {
                    "providers": _provider_options(),
                    "analysts": [
                        ("Market Analyst", "market"),
                        ("Sentiment Analyst", "social"),
                        ("News Analyst", "news"),
                        ("Fundamentals Analyst", "fundamentals"),
                    ],
                    "depths": [
                        {"label": "Shallow", "value": 1},
                        {"label": "Medium", "value": 3},
                        {"label": "Deep", "value": 5},
                    ],
                    "languages": [
                        "English", "Chinese", "Japanese", "Korean", "Hindi",
                        "Spanish", "Portuguese", "French", "German", "Arabic",
                        "Russian",
                    ],
                    "popularTickers": POPULAR_TICKERS,
                    "opencode": {
                        "fullUrl": "https://opencode.ai/zen/v1",
                        "legacyUrl": "https://opencode.ai/zen/go/v1",
                        "current": os.environ.get("OPENCODE_BASE_URL")
                        or "https://opencode.ai/zen/v1",
                    },
                },
            )
        if path == "/api/models":
            provider = query.get("provider", ["openai"])[0]
            mode = query.get("mode", ["quick"])[0]
            try:
                return _json(self, _model_list(provider, mode))
            except Exception as exc:
                return _json(self, {"models": [{"name": "Custom model ID", "id": "custom"}], "source": "custom-only", "error": str(exc)})
        if path == "/api/settings/keys":
            return _json(self, {"keys": _provider_options()})
        if path == "/api/sessions":
            try:
                return _json(self, {"sessions": _list_sessions()})
            except Exception as exc:
                return _json(self, {"sessions": [], "error": str(exc)})
        if path == "/api/session":
            session_id = query.get("id", [""])[0]
            session_dir, kind = _resolve_session(session_id)
            if session_dir is None:
                return _json(self, {"error": "unknown session"}, status=404)
            return _json(
                self,
                {"id": session_id, "kind": kind, "files": _session_files(session_dir, kind)},
            )
        if path == "/api/runs":
            from cli.runs import MANAGER

            return _json(self, {"runs": [r.summary() for r in MANAGER.all()]})
        if path.startswith("/api/runs/"):
            from cli.runs import MANAGER

            parts = path[len("/api/runs/"):].split("/")
            rec = MANAGER.get(parts[0]) if parts and parts[0] else None
            if rec is None:
                return _json(self, {"error": "unknown run"}, status=404)
            if len(parts) == 2 and parts[1] == "state":
                try:
                    from cli.dashboard import build_snapshot
                    from cli.main import message_buffer

                    snap = build_snapshot(
                        message_buffer,
                        rec.stats_handler,
                        rec.start_time or rec.created,
                        {
                            "ticker": rec.selections.get("ticker"),
                            "analysis_date": rec.selections.get("analysis_date"),
                            "llm_provider": rec.selections.get("llm_provider"),
                        },
                    )
                    snap["active"] = rec.status in ("starting", "running")
                    snap["status"] = rec.status
                    snap["pending_prompt"] = rec.pending_prompt
                    snap["error"] = rec.error
                    return _json(self, snap)
                except Exception as exc:
                    return _json(self, {"active": False, "error": str(exc)})
            if len(parts) == 2 and parts[1] == "report":
                try:
                    from cli.dashboard import SECTION_TITLES
                    from cli.main import message_buffer

                    return _json(
                        self,
                        {
                            "status": rec.status,
                            "sections": dict(message_buffer.report_sections),
                            "section_titles": SECTION_TITLES,
                            "final_report": message_buffer.final_report,
                            "error": rec.error,
                        },
                    )
                except Exception as exc:
                    return _json(self, {"error": str(exc)}, status=500)
            return _json(self, {"error": "not found"}, status=404)
        if path == "/api/state":
            live = getattr(self.server, "live", None)
            if not live or not live.get("message_buffer"):
                return _json(self, {"active": False})
            try:
                from cli.dashboard import build_snapshot

                snap = build_snapshot(
                    live["message_buffer"],
                    live.get("stats_handler"),
                    live.get("start_time"),
                    live.get("meta"),
                )
                snap["active"] = True
                return _json(self, snap)
            except Exception as exc:
                return _json(self, {"active": False, "error": str(exc)})
        return _json(self, {"error": "not found"}, status=404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/settings/keys":
            payload = _read_json(self)
            env_var, value = payload.get("env", ""), payload.get("value", "")
            if not env_var or not value:
                return _json(self, {"ok": False, "error": "env and value are required"})
            try:
                env_path = find_dotenv(usecwd=True) or str(Path.cwd() / ".env")
                Path(env_path).touch(exist_ok=True)
                set_key(env_path, env_var, value)
                os.environ[env_var] = value  # live: no restart needed
            except Exception as exc:
                return _json(self, {"ok": False, "error": str(exc)})
            return _json(self, {"ok": True, "message": f"Saved {env_var} to {env_path}"})
        if parsed.path == "/api/runs":
            from cli.runs import MANAGER, BusyError

            payload = _read_json(self)
            if not isinstance(payload, dict) or not payload:
                return _json(self, {"ok": False, "error": "selections object required"})
            try:
                rec = MANAGER.start(payload)
            except BusyError as exc:
                return _json(self, {"ok": False, "error": str(exc), "id": exc.run_id}, status=409)
            except ValueError as exc:
                return _json(self, {"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                return _json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)
            return _json(self, {"ok": True, "id": rec.id}, status=201)
        if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/answer"):
            from cli.runs import MANAGER

            parts = parsed.path[len("/api/runs/"):].split("/")
            rec = MANAGER.get(parts[0]) if parts else None
            if rec is None:
                return _json(self, {"ok": False, "error": "unknown run"}, status=404)
            payload = _read_json(self)
            answer = payload.get("answer")
            if not isinstance(answer, str) or not rec.pending_prompt.get("question"):
                return _json(self, {"ok": False, "error": "no pending prompt"})
            rec.pending_prompt["answer"] = answer
            return _json(self, {"ok": True})
        if parsed.path == "/api/settings/test":
            payload = _read_json(self)
            provider = payload.get("provider", "")
            if not provider:
                return _json(self, {"ok": False, "error": "provider is required"})
            from tradingagents.llm_clients.api_key_env import get_api_key_env

            key = payload.get("key") or None
            if key is None:
                env_var = get_api_key_env(provider)
                key = os.environ.get(env_var) if env_var else None
            ok, message, count = _test_key(provider, key)
            return _json(self, {"ok": ok, "message": message, "count": count})
        return _json(self, {"error": "not found"}, status=404)


def _warm():
    """Pre-import heavy modules (langchain stacks take ~20s) so the first
    API request doesn't pay import cost inside its handler thread."""
    import cli.dashboard  # noqa: F401
    import cli.utils  # noqa: F401
    import tradingagents.default_config  # noqa: F401
    import tradingagents.llm_clients.api_key_env  # noqa: F401
    import tradingagents.llm_clients.model_catalog  # noqa: F401
    import tradingagents.llm_clients.openai_client  # noqa: F401


def create_server(host="127.0.0.1", port=API_DEFAULT_PORT):
    from cli.dashboard import find_free_port

    _warm()

    try:
        port = int(os.environ.get("TRADINGAGENTS_API_PORT", port))
    except ValueError:
        port = API_DEFAULT_PORT
    port = find_free_port(host, port)
    if port is None:
        return None, None
    server = ThreadingHTTPServer((host, port), _Handler)
    server.daemon_threads = True
    server.live = None
    return server, f"http://{host}:{port}"


def start_background(host="127.0.0.1", port=API_DEFAULT_PORT):
    """Start the API in a daemon thread. Returns ``(server, url)``."""
    server, url = create_server(host, port)
    if server is None:
        return None, None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, url


def serve_forever(host="127.0.0.1", port=API_DEFAULT_PORT):
    """Blocking entry point for ``tradingagents web``."""
    server, url = create_server(host, port)
    if server is None:
        raise SystemExit("Could not bind the API port.")
    print(f"TradingAgents API: {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
