"""FMP client — Postgres-bulk fast path with live API fallback.

TradingAgents' FMP data layer. Mirrors the pattern used by
stock-screener/backend/app/services/fmp_data_service.py but lives inside
TradingAgents so this submodule doesn't depend on the parent repo's code.

Preference order:
  1. Postgres ``fmp_bulk`` table (nightly ETL drops bulk endpoints as JSONB).
  2. FMP live API (``https://financialmodelingprep.com/stable/...``).

Environment:
  FMP_API_KEY             — required for live API calls
  FMP_BULK_DATABASE_URL   — Postgres connection string (falls back to POSTGRES_URL)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Iterable, List, Optional

import requests

logger = logging.getLogger(__name__)

FMP_BASE_URL = "https://financialmodelingprep.com/stable"
DEFAULT_TIMEOUT_S = 30


class FMPClient:
    """Singleton FMP client. Use :func:`get_client` to access."""

    _instance: Optional["FMPClient"] = None

    def __init__(self, api_key: Optional[str] = None, session: Optional[requests.Session] = None):
        self.api_key = api_key or os.environ.get("FMP_API_KEY") or ""
        if not self.api_key:
            logger.debug("FMP_API_KEY not set — live FMP calls will fail")
        self._session = session or requests.Session()
        self._pg_conn = None

    # ──────────────────────────────────────────────────────────────────
    # Postgres bulk lookups
    # ──────────────────────────────────────────────────────────────────

    def bulk_lookup(self, bulk_name: str, primary_key: str) -> Optional[Dict[str, Any]]:
        conn = self._get_pg()
        if conn is None:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT data FROM fmp_bulk
                    WHERE bulk_name = %s AND primary_key = %s
                    ORDER BY captured_date DESC
                    LIMIT 1
                    """,
                    (bulk_name, primary_key),
                )
                row = cur.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.debug("fmp_bulk lookup %s/%s failed: %s", bulk_name, primary_key, e)
            return None

    def bulk_list(self, bulk_name: str) -> Optional[List[Dict[str, Any]]]:
        conn = self._get_pg()
        if conn is None:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (primary_key) data FROM fmp_bulk
                    WHERE bulk_name = %s
                    ORDER BY primary_key, captured_date DESC
                    """,
                    (bulk_name,),
                )
                return [r[0] for r in cur.fetchall()]
        except Exception as e:
            logger.debug("fmp_bulk list %s failed: %s", bulk_name, e)
            return None

    # ──────────────────────────────────────────────────────────────────
    # Live API
    # ──────────────────────────────────────────────────────────────────

    def live_get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        unwrap_single: bool = True,
    ) -> Any:
        """Call an FMP /stable/* endpoint. Returns parsed JSON or None on error.

        If ``unwrap_single`` is True (default), a list result is unwrapped to
        its first element (or None if empty) — matches the common pattern
        of single-symbol endpoints wrapping their response in a 1-element list.
        """
        params = dict(params or {})
        params["apikey"] = self.api_key
        url = f"{FMP_BASE_URL}{path}"
        try:
            resp = self._session.get(url, params=params, timeout=DEFAULT_TIMEOUT_S)
            resp.raise_for_status()
            body = resp.json()
        except requests.RequestException as e:
            logger.debug("FMP %s failed: %s", path, e)
            return None
        if unwrap_single and isinstance(body, list):
            return body[0] if body else None
        return body

    def live_get_list(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Call an FMP endpoint that returns a JSON array. Empty list on error."""
        result = self.live_get(path, params=params, unwrap_single=False)
        return result if isinstance(result, list) else []

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

    def _get_pg(self):
        if self._pg_conn is not None:
            try:
                # Detect stale connection
                if getattr(self._pg_conn, "closed", 0):
                    self._pg_conn = None
                else:
                    return self._pg_conn
            except Exception:
                self._pg_conn = None
        url = os.environ.get("FMP_BULK_DATABASE_URL") or os.environ.get("POSTGRES_URL")
        if not url:
            return None
        try:
            import psycopg2
            self._pg_conn = psycopg2.connect(url)
            self._pg_conn.autocommit = True
            return self._pg_conn
        except Exception as e:
            logger.debug("psycopg2 connect failed: %s", e)
            return None


def get_client() -> FMPClient:
    if FMPClient._instance is None:
        FMPClient._instance = FMPClient()
    return FMPClient._instance
