"""Environment-driven settings for the dashboard server."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _default_db_path() -> str:
    home = Path.home() / ".tradingagents"
    home.mkdir(parents=True, exist_ok=True)
    return str(home / "dashboard.db")


@dataclass(frozen=True)
class Settings:
    db_path: str = os.environ.get("TRADINGAGENTS_DASHBOARD_DB", _default_db_path())
    host: str = os.environ.get("TRADINGAGENTS_DASHBOARD_HOST", "127.0.0.1")
    port: int = int(os.environ.get("TRADINGAGENTS_DASHBOARD_PORT", "8000"))
    max_concurrent: int = int(os.environ.get("TRADINGAGENTS_DASHBOARD_MAX_CONCURRENT", "3"))
    price_poll_s: int = int(os.environ.get("TRADINGAGENTS_DASHBOARD_PRICE_POLL_S", "15"))
    log_level: str = os.environ.get("TRADINGAGENTS_DASHBOARD_LOG_LEVEL", "INFO")
    frontend_dist: str = os.environ.get("TRADINGAGENTS_FRONTEND_DIST", "web/frontend/dist")


def get_settings() -> Settings:
    return Settings()
