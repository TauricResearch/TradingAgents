"""
confluence_publisher.py

Publishes TauricTradingAgents analysis reports to Confluence under:

  Reports (1376579)
  └── 2026
      └── 2026-05
          └── 2026-05-19 14:32:07 ET · NVDA · Buy
          └── 2026-05-19 16:05:41 ET · NVDA · Buy   # re-run -> new page

Every call to publish_report() ALWAYS creates a new page. Re-runs produce
separate timestamped pages for a full intraday audit trail.

Configuration comes from DEFAULT_CONFIG (confluence_* keys). Works whether
TauricTradingAgents is run via universe_dispatcher.py or standalone.

Required env vars (franklin.env):
  CONFLUENCE_USER_EMAIL   e.g. sal.cobian@franklinfinancial.ai
  CONFLUENCE_API_TOKEN    Atlassian API token
"""

import os
import json
import urllib.request
import urllib.error
import base64
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

log = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

# Year/month container page IDs cached per process.
# Report pages are never cached -- always created fresh.
_page_id_cache: dict[str, str] = {}


def _auth_header() -> str:
    email = os.environ.get("CONFLUENCE_USER_EMAIL", "")
    token = os.environ.get("CONFLUENCE_API_TOKEN", "")
    if not email or not token:
        raise EnvironmentError(
            "CONFLUENCE_USER_EMAIL and CONFLUENCE_API_TOKEN must be set in franklin.env"
        )
    return "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode()


def _request(method: str, url: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url, data=body,
        headers={
            "Authorization": _auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Atlassian-Token": "no-check",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"Confluence {method} {url} -> HTTP {e.code}: {detail}") from e


def _find_child_page(base_url: str, parent_id: str, title: str) -> str | None:
    """Find a child page by exact title. Used only for year/month containers."""
    url = f"{base_url}/rest/api/content/{parent_id}/child/page?limit=100"
    req = urllib.request.Request(
        url, headers={"Authorization": _auth_header(), "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            for page in json.loads(resp.read()).get("results", []):
                if page["title"] == title:
                    return page["id"]
    except Exception:
        pass
    return None


def _ensure_page(base_url: str, space_key: str, parent_id: str,
                 title: str, body_html: str) -> str:
    """Return page ID of child with this title under parent_id, creating if needed."""
    cache_key = f"{parent_id}::{title}"
    if cache_key in _page_id_cache:
        return _page_id_cache[cache_key]
    existing = _find_child_page(base_url, parent_id, title)
    if existing:
        _page_id_cache[cache_key] = existing
        return existing
    result = _request("POST", f"{base_url}/rest/api/content", {
        "type": "page", "title": title,
        "space": {"key": space_key},
        "ancestors": [{"id": parent_id}],
        "body": {"storage": {"value": body_html, "representation": "storage"}},
    })
    page_id = result["id"]
    log.info(f"Confluence: created container '{title}' (id={page_id})")
    _page_id_cache[cache_key] = page_id
    return page_id


def _ensure_year_month(base_url: str, space_key: str,
                       reports_root_id: str, run_dt: datetime) -> str:
    """Ensure Reports/yyyy/yyyy-mm containers exist. Returns month page ID."""
    year_id = _ensure_page(base_url, space_key, reports_root_id,
                           run_dt.strftime("%Y"),
                           f"<p>Trading reports for {run_dt.strftime('%Y')}.</p>")
    month_id = _ensure_page(base_url, space_key, year_id,
                            run_dt.strftime("%Y-%m"),
                            f"<p>Trading reports for {run_dt.strftime('%Y-%m')}.</p>")
    return month_id


def _badge(signal: str) -> str:
    styles = {
        "Buy": ("color:#00875a", "⬆"), "Overweight": ("color:#00875a", "⬆"),
        "Hold": ("color:#505f79", "→"),
        "Underweight": ("color:#de350b", "⬇"), "Sell": ("color:#de350b", "⬇"),
    }
    style, arrow = styles.get(signal, ("color:#172b4d", "·"))
    return f'<strong style="{style}">{arrow} {signal}</strong>'


def _confidence_bar(confidence: float) -> str:
    pct = int(confidence * 100)
    color = "#00875a" if confidence >= 0.75 else "#ff991f" if confidence >= 0.5 else "#de350b"
    return (f'<div style="background:#f4f5f7;border-radius:3px;height:8px;'
            f'width:200px;display:inline-block;vertical-align:middle;">'
            f'<div style="background:{color};border-radius:3px;height:8px;'
            f'width:{pct * 2}px;"></div></div><small> {pct}%</small>')


def _esc(text: str, limit: int = 4000) -> str:
    if not text:
        return "<em>No content recorded.</em>"
    text = text[:limit] + ("…" if len(text) > limit else "")
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\n", "<br/>"))


def _build_html(symbol: str, signal: str, final_state: dict[str, Any],
                run_ts: datetime) -> str:
    confidence_map = {"Buy": 1.0, "Overweight": 0.75, "Hold": 0.5,
                      "Underweight": 0.25, "Sell": 0.0}
    confidence = confidence_map.get(signal, 0.5)
    debate = final_state.get("investment_debate_state", {})
    risk_debate = final_state.get("risk_debate_state", {})
    ts_display = run_ts.strftime("%Y-%m-%d %H:%M:%S %Z")
    ts_iso = run_ts.isoformat()
    return (
        f"<p><strong>Symbol:</strong> {symbol} &nbsp;|&nbsp;"
        f"<strong>Generated:</strong> {ts_display} &nbsp;|&nbsp;"
        f"<strong>Rating:</strong> {_badge(signal)} &nbsp;|&nbsp;"
        f"<strong>Confidence:</strong> {_confidence_bar(confidence)}</p><hr/>"
        f"<h2>Investment Decision</h2><p>{_esc(final_state.get('final_trade_decision', ''), 6000)}</p>"
        f"<h2>Bull Case</h2><p>{_esc(debate.get('bull_history', ''))}</p>"
        f"<h2>Bear Case</h2><p>{_esc(debate.get('bear_history', ''))}</p>"
        f"<h2>Investment Judge Decision</h2><p>{_esc(debate.get('judge_decision', ''), 3000)}</p>"
        f"<h2>Risk Assessment</h2><p>{_esc(risk_debate.get('judge_decision', ''), 3000)}</p>"
        f"<hr/><p><small>Generated by TauricTradingAgents"
        f" &middot; <time datetime=\"{ts_iso}\">{ts_display}</time></small></p>"
    )


def _page_title(symbol: str, signal: str, run_ts: datetime) -> str:
    return f"{run_ts.strftime('%Y-%m-%d %H:%M:%S %Z')} · {symbol} · {signal}"


def publish_report(symbol: str, signal: str, final_state: dict[str, Any],
                   config: dict[str, Any] | None = None) -> str:
    """
    Publish a TauricTradingAgents report to Confluence. Always creates a NEW page.

    Reports hierarchy:
      Reports -> yyyy -> yyyy-mm -> yyyy-mm-dd HH:MM:SS ET · SYMBOL · Signal

    Returns the page URL, or "" if confluence_publish=False in config.
    Raises RuntimeError on API failure (caller should catch as non-fatal).
    """
    cfg = config or {}
    if not cfg.get("confluence_publish", True):
        log.debug("Confluence publishing disabled -- skipping")
        return ""

    base_url       = cfg.get("confluence_base_url",       "https://franklindigitalcorp.atlassian.net/wiki")
    space_key      = cfg.get("confluence_space_key",      "trading")
    parent_page_id = cfg.get("confluence_parent_page_id", "1376579")
    run_ts         = datetime.now(tz=ET)

    month_id = _ensure_year_month(base_url, space_key, parent_page_id, run_ts)
    title    = _page_title(symbol, signal, run_ts)
    content  = _build_html(symbol, signal, final_state, run_ts)

    result   = _request("POST", f"{base_url}/rest/api/content", {
        "type": "page", "title": title,
        "space": {"key": space_key},
        "ancestors": [{"id": month_id}],
        "body": {"storage": {"value": content, "representation": "storage"}},
    })
    page_id  = result["id"]
    page_url = f"{base_url}/spaces/{space_key}/pages/{page_id}"
    log.info(f"Confluence: published '{title}' -> {page_url}")
    return page_url
