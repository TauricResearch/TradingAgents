"""Environment + config preparation for an adapter subprocess.

Everything here runs BEFORE ``tradingagents`` is imported, because the engine
reads its directory env vars and loads ``.env`` at import time
(``tradingagents/default_config.py`` and ``tradingagents/__init__.py``).
Dependency-free (stdlib only).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def prepare_environment(base_dir: str | None) -> None:
    """Pin engine I/O into the app's domain and disable the engine's dotenv load.

    - ``TRADINGAGENTS_NO_DOTENV=1`` stops the bundled engine from auto-loading a
      stray ``.env`` (honored by the ``tradingagents/__init__.py`` guard).
    - Redirect results / cache / memory under ``base_dir`` (the app passes a
      per-run results dir and a shared memory/cache dir). When ``base_dir`` is
      None the engine defaults (``~/.tradingagents``) stand.
    """
    os.environ.setdefault("TRADINGAGENTS_NO_DOTENV", "1")
    if not base_dir:
        return
    base = Path(base_dir).expanduser()
    results = base / "results"
    cache = base / "cache"
    memory = base / "memory" / "trading_memory.md"
    for p in (results, cache, memory.parent):
        p.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TRADINGAGENTS_RESULTS_DIR", str(results))
    os.environ.setdefault("TRADINGAGENTS_CACHE_DIR", str(cache))
    os.environ.setdefault("TRADINGAGENTS_MEMORY_LOG_PATH", str(memory))


def load_run_config(path: str) -> dict[str, Any]:
    """Load the resolved Profile->config JSON the app wrote for this run.

    Secrets are NOT in this file — they arrive as provider key env vars injected
    into the subprocess environment by the coordinator.
    """
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_engine_config(run_config: dict[str, Any]) -> dict[str, Any]:
    """Merge a run config onto ``DEFAULT_CONFIG`` (imported lazily, 3.10+ only).

    Mirrors the CLI's assignment (``cli/main.py:1027``) and ``set_config``'s
    one-level-deep merge for the nested ``data_vendors`` dict.
    """
    from tradingagents.default_config import DEFAULT_CONFIG

    cfg = DEFAULT_CONFIG.copy()
    nested = run_config.get("data_vendors")
    tool_nested = run_config.get("tool_vendors")
    skip = {"data_vendors", "tool_vendors", "analysts", "ticker", "trade_date", "asset_type", "profile_name", "keys"}
    for key, value in run_config.items():
        if key in skip:
            continue
        cfg[key] = value
    if isinstance(nested, dict):
        cfg["data_vendors"] = {**cfg.get("data_vendors", {}), **nested}
    if isinstance(tool_nested, dict):
        cfg["tool_vendors"] = {**cfg.get("tool_vendors", {}), **tool_nested}
    return cfg
