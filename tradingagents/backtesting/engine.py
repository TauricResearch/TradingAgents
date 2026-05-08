from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Set, Tuple

import pandas as pd

from .models import BacktestResult

logger = logging.getLogger(__name__)

FREQ_MAP: dict[str, str] = {
    "monthly": "MS",
    "weekly": "W-MON",
    "biweekly": "2W-MON",
}


def generate_dates(start_date: str, end_date: str, freq: str) -> list[str]:
    """Return business-day-aligned ISO date strings for the backtest range."""
    pd_freq = FREQ_MAP.get(freq)
    if pd_freq is None:
        raise ValueError(f"Unsupported freq {freq!r}. Use: {list(FREQ_MAP)}")
    dates = pd.date_range(start=start_date, end=end_date, freq=pd_freq)
    aligned = []
    for d in dates:
        if d.dayofweek >= 5:  # Saturday=5, Sunday=6
            d = d + pd.offsets.BDay(1)
        aligned.append(d.strftime("%Y-%m-%d"))
    return aligned


def load_completed_pairs(output_file: str) -> Set[Tuple[str, str]]:
    """Return (ticker, trade_date) pairs that completed without error."""
    path = Path(output_file)
    if not path.exists():
        return set()
    completed: Set[Tuple[str, str]] = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("error") is None:
                    completed.add((obj["ticker"], obj["trade_date"]))
            except json.JSONDecodeError:
                continue
    return completed


def append_result(output_file: str, result: BacktestResult) -> None:
    """Append one BacktestResult as a newline-delimited JSON record."""
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(result)) + "\n")
