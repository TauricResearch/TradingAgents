from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Set, Tuple

import pandas as pd

from .models import BacktestResult, derive_direction
from tradingagents.graph.trading_graph import TradingAgentsGraph

logger = logging.getLogger(__name__)

FREQ_MAP: dict[str, str] = {
    "monthly": "MS",
    "weekly": "W-MON",
    "biweekly": "2W-MON",
}


def generate_dates(start_date: str, end_date: str, freq: str) -> list[str]:
    """Return ISO date strings for the backtest range; weekend dates are bumped to Monday."""
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
                if obj.get("error") is None and "ticker" in obj and "trade_date" in obj:
                    completed.add((obj["ticker"], obj["trade_date"]))
            except json.JSONDecodeError:
                continue
    return completed


def append_result(output_file: str, result: BacktestResult) -> None:
    """Append one BacktestResult as a newline-delimited JSON record."""
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(result)) + "\n")


class BacktestEngine:
    def __init__(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
        freq: str = "monthly",
        config: Optional[dict] = None,
        analysts: Optional[list[str]] = None,
        max_workers: int = 2,
        output_file: Optional[str] = None,
    ) -> None:
        self.tickers = tickers
        self.start_date = start_date
        self.end_date = end_date
        self.freq = freq
        self.config = config or {}
        self.analysts = analysts or ["market", "social", "news", "fundamentals"]
        self.max_workers = max_workers

        if output_file is None:
            key = f"{sorted(tickers)}-{start_date}-{end_date}-{freq}"
            h = hashlib.md5(key.encode()).hexdigest()[:8]
            home = os.path.expanduser("~")
            output_file = os.path.join(
                home, ".tradingagents", "backtests", f"{h}.jsonl"
            )
        self.output_file = output_file
        self._write_lock = threading.Lock()

    def run(self, resume: bool = False) -> list[BacktestResult]:
        all_dates = generate_dates(self.start_date, self.end_date, self.freq)
        completed = load_completed_pairs(self.output_file) if resume else set()

        # Group remaining (ticker, date) pairs by ticker to preserve date order
        ticker_dates: dict[str, list[str]] = {t: [] for t in self.tickers}
        for ticker in self.tickers:
            for d in all_dates:
                if (ticker, d) not in completed:
                    ticker_dates[ticker].append(d)

        results: list[BacktestResult] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(self._run_ticker, ticker, dates): ticker
                for ticker, dates in ticker_dates.items()
                if dates
            }
            for future in as_completed(futures):
                results.extend(future.result())
        return results

    def _run_ticker(self, ticker: str, dates: list[str]) -> list[BacktestResult]:
        graph = TradingAgentsGraph(
            selected_analysts=self.analysts,
            config=self.config,
        )
        results = []
        for trade_date in dates:
            result = self._run_one(graph, ticker, trade_date)
            with self._write_lock:
                append_result(self.output_file, result)
            results.append(result)
        return results

    def _run_one(
        self, graph: "TradingAgentsGraph", ticker: str, trade_date: str
    ) -> BacktestResult:
        max_retries = 5
        backoff = 1.0
        start = time.monotonic()

        for attempt in range(max_retries):
            try:
                state, rating = graph.propagate(ticker, trade_date)
                duration = time.monotonic() - start
                return BacktestResult(
                    ticker=ticker,
                    trade_date=trade_date,
                    rating=rating,
                    direction=derive_direction(rating),
                    raw_output=state.get("final_trade_decision", ""),
                    run_duration_seconds=round(duration, 2),
                )
            except Exception as exc:
                err_str = str(exc)
                if "429" in err_str and attempt < max_retries - 1:
                    time.sleep(min(backoff, 60.0))
                    backoff *= 2
                    continue
                duration = time.monotonic() - start
                return BacktestResult(
                    ticker=ticker,
                    trade_date=trade_date,
                    error=err_str,
                    run_duration_seconds=round(duration, 2),
                )
