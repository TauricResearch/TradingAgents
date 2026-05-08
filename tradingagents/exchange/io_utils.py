"""Shared I/O helpers for Polymarket scripts.

Three CLI scripts (run_polymarket.py, score_fills.py, backtest.py) used to
duplicate this constant and the JSONL-append helper. Centralised here so
custom `TRADINGAGENTS_RESULTS_DIR` overrides apply consistently if we ever
honor that env var, and so the output path doesn't drift across scripts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

POLYMARKET_OUTPUT_DIR = Path.home() / ".tradingagents" / "polymarket"


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    """Append one JSONL line. Atomic-enough for single-process polling."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, separators=(",", ":")) + "\n")
