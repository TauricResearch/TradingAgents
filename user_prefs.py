"""Per-user preferences for the daily-schedule feature.

Stored as JSON at ``~/.tradingagents/users/<sha256(email)[:12]>/preferences.json``.
The slug computation matches ``webui._user_home_for`` so all per-user state
lives under one root.

Keep this module zero-dependency on Streamlit so ``scheduler.py`` (a
non-Streamlit subprocess) can use it too.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PREFS_FILENAME = "preferences.json"

# Default values applied when reading a missing or partial preferences file.
# Keep in sync with the webui defaults.
DEFAULT_PREFS: dict[str, Any] = {
    "daily_schedule_enabled": False,
    "tickers": [],                       # list[str], free-form (resolver-handled)
    "telegram_chat_id": "",
    "selected_analysts": ["market"],
    "provider": "google",
    "deep_model": "gemini-2.5-flash",
    "quick_model": "gemini-2.5-flash",
    "output_language": "中文",
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
}


def user_home(email: str) -> Path:
    """Same hashing as webui._user_home_for — reuse it in non-Streamlit code."""
    slug = hashlib.sha256(email.strip().lower().encode()).hexdigest()[:12]
    home = Path.home() / ".tradingagents" / "users" / slug
    home.mkdir(parents=True, exist_ok=True)
    return home


def prefs_path(email: str) -> Path:
    return user_home(email) / PREFS_FILENAME


def load(email: str) -> dict[str, Any]:
    """Read prefs, merging missing keys from DEFAULT_PREFS."""
    p = prefs_path(email)
    if not p.exists():
        return dict(DEFAULT_PREFS)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_PREFS)
    out = dict(DEFAULT_PREFS)
    out.update({k: v for k, v in raw.items() if k in DEFAULT_PREFS})
    return out


def save(email: str, prefs: dict[str, Any]) -> Path:
    """Write prefs atomically. Returns the file path."""
    p = prefs_path(email)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Whitelist fields so callers can't accidentally persist garbage.
    clean = {k: prefs[k] for k in DEFAULT_PREFS if k in prefs}
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    return p


def all_users_with_prefs() -> list[tuple[str, dict[str, Any]]]:
    """Walk the per-user dir tree and yield (slug, prefs) for every user that
    has saved preferences. Used by the scheduler.

    Note: returns slug, not email — emails are intentionally hashed and cannot
    be recovered from the slug. The scheduler doesn't need the email for
    anything except logging; the slug is enough for filesystem ops.
    """
    root = Path.home() / ".tradingagents" / "users"
    if not root.exists():
        return []
    out: list[tuple[str, dict[str, Any]]] = []
    for user_dir in sorted(root.iterdir()):
        pref_file = user_dir / PREFS_FILENAME
        if not pref_file.exists():
            continue
        try:
            data = json.loads(pref_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        merged = dict(DEFAULT_PREFS)
        merged.update({k: v for k, v in data.items() if k in DEFAULT_PREFS})
        out.append((user_dir.name, merged))
    return out
