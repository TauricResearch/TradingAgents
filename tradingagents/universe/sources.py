"""S&P 500 membership source — a seed file shipped in the repo.

Deterministic, offline, no extra dependency. The packaged seed
(``tradingagents/data/sp500.csv``) is a starter list; replace/refresh it with
the full official constituents. Lines starting with ``#`` are comments.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

_DEFAULT_SEED = Path(__file__).resolve().parent.parent / "data" / "sp500.csv"


def load_sp500_seed(path: Optional[str | Path] = None) -> dict[str, Optional[str]]:
    """Return {symbol: sector} from the seed CSV (symbol[,sector] rows)."""
    p = Path(path) if path else _DEFAULT_SEED
    out: dict[str, Optional[str]] = {}
    if not p.exists():
        return out
    with open(p, newline="") as fh:
        for row in csv.reader(fh):
            if not row:
                continue
            symbol = row[0].strip()
            if not symbol or symbol.startswith("#") or symbol.lower() == "symbol":
                continue
            sector = row[1].strip() if len(row) > 1 and row[1].strip() else None
            out[symbol] = sector
    return out


class Sp500Source:
    """Pluggable S&P 500 source (seed-backed by default)."""

    def __init__(self, path: Optional[str | Path] = None):
        self.path = path

    def constituents(self) -> dict[str, Optional[str]]:
        return load_sp500_seed(self.path)
