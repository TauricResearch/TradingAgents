"""The dashboard's overrides of the LLM settings: ``TRADER_HOME/settings.json`` (ADR 0007).

The file names the models of the two research tiers and their prices. The web API writes
it; ``Settings.from_env`` reads it at every run of either account, where it takes
precedence over .env. It looks like::

    {"version": 1,
     "llm": {"deep_think_llm": "...", "quick_think_llm": "...",
             "deep_think_provider": "anthropic", "quick_think_provider": "anthropic"},
     "prices": {"<model id>": [input, output]},      # USD per million tokens
     "updated_at": "2026-11-07T05:00:00Z",
     "history": [{"at": "...", "deep": "...", "quick": "...", "note": "web"}]}

Switching a model changes the research fingerprint, so the accounts restart their
validation period at the next run; the history keeps every switch.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

FILE_NAME = "settings.json"
VERSION = 1
HISTORY_LIMIT = 50
# The config keys the file may set; ``build_config`` applies no others.
LLM_KEYS = ("deep_think_llm", "quick_think_llm", "deep_think_provider", "quick_think_provider")


def path(home: Path) -> Path:
    return home / FILE_NAME


def load(home: Path) -> dict | None:
    """The file's contents, or None when there is no file.

    A file that is not a JSON object or has no ``llm`` object raises ValueError naming
    the path: a run must fail and alert rather than fall back to the .env models unnoticed.
    """
    file = path(home)
    try:
        text = file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"{file} is not valid JSON: {exc}") from None
    if not isinstance(data, dict) or not isinstance(data.get("llm"), dict):
        raise ValueError(f'{file} has no "llm" object')
    return data


def save(
    home: Path, llm: dict, prices: dict[str, tuple[float, float]], note: str, now: datetime
) -> dict:
    """Write the file and return what it holds now.

    ``llm`` replaces the models; ``prices`` is merged over the saved prices, a model's
    new price winning; a history entry ``{at, deep, quick, note}`` is prepended, the
    history kept to HISTORY_LIMIT entries. The file is written whole (a temporary file
    replaces it), so a reader never sees a partial one.
    """
    previous = load(home) or {}
    at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = {"at": at, "deep": llm["deep_think_llm"], "quick": llm["quick_think_llm"], "note": note}
    data = {
        "version": VERSION,
        "llm": dict(llm),
        "prices": {**previous.get("prices", {}), **{m: list(p) for m, p in prices.items()}},
        "updated_at": at,
        "history": [entry, *previous.get("history", [])][:HISTORY_LIMIT],
    }
    file = path(home)
    file.parent.mkdir(parents=True, exist_ok=True)
    temporary = file.with_name(file.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, file)
    return data


def tier_models(data: dict | None) -> dict:
    """The LLM_KEYS a loaded file sets, from its ``llm``; empty without a file."""
    if data is None:
        return {}
    return {key: data["llm"][key] for key in LLM_KEYS if key in data["llm"]}
