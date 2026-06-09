"""Runtime settings for the FastAPI backend, read from environment.

Mirrors the env conventions used by the existing Streamlit deployment so the
same systemd env block works for both services.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


class Settings:
    # uvicorn bind
    port = int(os.getenv("TRADINGAGENTS_API_PORT", "8502"))
    bind = os.getenv("TRADINGAGENTS_BIND", "127.0.0.1")

    # session cookie carrying the auth.py HMAC token.
    # Default OFF so plain-HTTP access (LAN / localhost) keeps the session — a
    # Secure cookie is silently dropped by the browser over HTTP, which breaks
    # login. The HTTPS production deploy (behind the tunnel) sets this to 1.
    cookie_name = "ta_session"
    cookie_secure = os.getenv("TRADINGAGENTS_COOKIE_SECURE", "0") == "1"

    # built Vue SPA; served at "/" when present
    frontend_dist = os.getenv(
        "TRADINGAGENTS_FRONTEND_DIST", str(_ROOT / "frontend" / "dist")
    )

    # max concurrent analysis worker subprocesses (matches webui semaphore)
    max_concurrent_runs = int(os.getenv("MAX_CONCURRENT_RUNS", "4"))

    # python used to spawn worker.py (matches scheduler/webui convention)
    python_bin = os.getenv("TRADINGAGENTS_PYTHON_BIN") or sys.executable

    # override for tests: a stub worker script
    worker_path = os.getenv("TRADINGAGENTS_WORKER_PATH", str(_ROOT / "worker.py"))

    root = _ROOT


settings = Settings()
