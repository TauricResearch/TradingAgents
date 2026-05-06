"""Collect the historical inputs needed to replay an agent run.

For each historical Kalshi contract we want:
- Contract metadata + final settlement outcome (Kalshi).
- Coinbase OHLCV candles up to the decision time (Coinbase API supports
  arbitrary historical windows on its public endpoint).
- News snapshots: RSS feeds don't expose historical archives reliably,
  so for serious backtest fidelity you'll want a paid news archive
  (NewsAPI archive, GDELT, or your own scraped corpus). The collector
  here writes a JSON-per-contract file you can later hand-author or
  populate via your preferred archive.

This module is intentionally a thin set of file IO helpers — the
expensive parts (paid news archives, on-chain history) are pluggable.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class HistoricalContract:
    contract_id: str
    decision_date: str  # YYYY-MM-DD — when the agent would have run
    settlement_outcome: str  # "YES" or "NO"
    kalshi_p_yes_at_decision: Optional[float]  # YES mid-price at decision time
    candles_to_decision: List[Dict[str, Any]]  # Coinbase OHLCV up to decision time
    news_snapshot_path: Optional[str] = None  # JSON file with frozen RSS/headline corpus
    onchain_snapshot_path: Optional[str] = None  # JSON file with frozen on-chain metrics


def fixtures_dir() -> Path:
    root = Path(__file__).parent / "fixtures"
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_contract(contract: HistoricalContract, name: Optional[str] = None) -> Path:
    name = name or f"{contract.contract_id}.json"
    path = fixtures_dir() / name
    path.write_text(json.dumps(asdict(contract), indent=2, default=str), encoding="utf-8")
    return path


def load_contract(name: str) -> HistoricalContract:
    path = fixtures_dir() / name
    payload = json.loads(path.read_text(encoding="utf-8"))
    return HistoricalContract(**payload)


def list_fixtures() -> List[str]:
    return sorted(p.name for p in fixtures_dir().glob("*.json"))
