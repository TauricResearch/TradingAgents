"""What the last run chose, offered back as the next run's defaults.

The interactive flow asks the same questions every time, and only some of them
have an environment variable to skip them (the analyst set has none). Remembered
answers prefill the prompts so Enter accepts them; they never skip a step, so a
run always starts on choices the user has seen.

Only answers that are stable between runs are kept. The ticker and the analysis
date are not: they change every run, and a remembered date would quietly offer a
stale one.

Every value is checked against the current choices on the way out, because
models and providers are added and retired between versions. A remembered model
that is no longer offered is dropped rather than shown.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from cli.models import AnalystType, AssetType
from cli.prompts import _llm_provider_table, filter_analysts_for_asset_type
from tradingagents.llm_clients.model_catalog import get_model_options

_PREFS_PATH = Path(os.path.expanduser("~")) / ".tradingagents" / "cli_prefs.json"

REMEMBERED = (
    "output_language", "analysts", "research_depth", "llm_provider",
    "quick_think_llm", "deep_think_llm", "backend_url",
)


def load_last_run() -> dict:
    """The previous run's answers, or an empty dict when there is nothing usable.

    Convenience state: an unreadable or corrupt file means no defaults, never an
    error in the user's way.
    """
    try:
        data = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_last_run(selections: dict) -> None:
    """Record the answers worth offering next time; failure is never fatal."""
    kept = {k: v for k, v in selections.items() if k in REMEMBERED and v not in (None, "", [])}
    kept["analysts"] = [getattr(a, "value", a) for a in kept.get("analysts", [])] or None
    kept = {k: v for k, v in kept.items() if v is not None}
    try:
        _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp = _PREFS_PATH.with_suffix(".tmp")
        temp.write_text(json.dumps(kept, indent=2), encoding="utf-8")
        os.replace(temp, _PREFS_PATH)  # a concurrent run reads one file or the other
    except OSError:
        return


def sanitize(prefs: dict, asset_type) -> dict:
    """Keep only the remembered answers that are still choosable now."""
    kept: dict = {}
    if isinstance(prefs.get("output_language"), str):
        kept["output_language"] = prefs["output_language"]
    if prefs.get("research_depth") in (1, 3, 5):
        kept["research_depth"] = prefs["research_depth"]

    known = {a.value for a in AnalystType}
    analysts = [a for a in prefs.get("analysts") or [] if a in known]
    allowed = filter_analysts_for_asset_type([AnalystType(a) for a in analysts], AssetType(asset_type))
    if allowed:
        kept["analysts"] = [a.value for a in allowed]

    provider = prefs.get("llm_provider")
    # Region-specific providers (qwen-cn) are picked in a second prompt, so the
    # base key is what the provider menu matches.
    base = (provider or "").split("-cn")[0]
    if base and base in {key for _, key, _ in _llm_provider_table()}:
        kept["llm_provider"] = provider
        if isinstance(prefs.get("backend_url"), str) and prefs["backend_url"]:
            kept["backend_url"] = prefs["backend_url"]
        for field, mode in (("quick_think_llm", "quick"), ("deep_think_llm", "deep")):
            try:
                offered = {model for _, model in get_model_options(base, mode)}
            except KeyError:
                continue
            if prefs.get(field) in offered:
                kept[field] = prefs[field]
    return kept
