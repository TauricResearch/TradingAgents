"""Append-only decision log with deferred outcome resolution.

Records trading decisions in a JSONL file and resolves actual outcomes
on subsequent runs by fetching market returns after the holding period.
Provides cross-ticker learning by surfacing lessons from resolved decisions
on other tickers.

Coexists with BM25_Memory and Historical_Context without modification.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


@dataclass
class DecisionRecord:
    """A single trading decision entry in the log."""

    ticker: str
    trade_date: str
    rating: str  # Canonical 5-tier vocabulary
    rationale_summary: str
    status: Literal["pending", "resolved"]
    recorded_at: str  # ISO timestamp
    # Populated on resolution:
    actual_return: float | None = None
    benchmark_return: float | None = None
    alpha: float | None = None
    resolved_at: str | None = None

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> DecisionRecord:
        """Deserialize from a dictionary, tolerating missing optional fields."""
        return cls(
            ticker=data["ticker"],
            trade_date=data["trade_date"],
            rating=data["rating"],
            rationale_summary=data["rationale_summary"],
            status=data["status"],
            recorded_at=data["recorded_at"],
            actual_return=data.get("actual_return"),
            benchmark_return=data.get("benchmark_return"),
            alpha=data.get("alpha"),
            resolved_at=data.get("resolved_at"),
        )


def _default_price_fetcher(ticker: str, start_date: str, end_date: str) -> float | None:
    """Fetch the return for a ticker over a date range using yfinance.

    Returns the percentage return (e.g., 0.05 for 5%) or None if data
    is unavailable.
    """
    try:
        import yfinance as yf

        data = yf.Ticker(ticker).history(start=start_date, end=end_date)
        if data.empty or len(data) < 2:
            return None
        start_price = data["Close"].iloc[0]
        end_price = data["Close"].iloc[-1]
        if start_price == 0:
            return None
        return (end_price - start_price) / start_price
    except Exception:
        logger.info(
            "Price data unavailable for %s (%s to %s), leaving as pending",
            ticker,
            start_date,
            end_date,
        )
        return None


class DecisionOutcomeTracker:
    """Tracks trading decisions and resolves outcomes after holding period.

    Coexists with BM25_Memory and Historical_Context without modification.
    Uses JSONL format for append-only durability.
    """

    def __init__(self, data_cache_dir: str, holding_period_days: int = 5):
        """Initialize tracker.

        Args:
            data_cache_dir: Base directory for data caches.
            holding_period_days: Days to wait before resolving outcomes.
        """
        self._data_cache_dir = data_cache_dir
        self._holding_period_days = holding_period_days

    @property
    def log_path(self) -> Path:
        """Path to the JSONL decision log file."""
        return Path(self._data_cache_dir) / "decision_log.jsonl"

    def record_decision(
        self,
        ticker: str,
        trade_date: str,
        rating: str,
        rationale_summary: str,
    ) -> None:
        """Append a pending decision record to the log.

        No-op if rating is empty or None.
        Does not modify existing records (append-only).

        Args:
            ticker: Stock ticker symbol.
            trade_date: Date of the trading decision (YYYY-MM-DD).
            rating: Canonical rating (Buy/Overweight/Hold/Underweight/Sell).
            rationale_summary: One-paragraph summary of the decision rationale.
        """
        if not rating or not rating.strip():
            return

        record = DecisionRecord(
            ticker=ticker,
            trade_date=trade_date,
            rating=rating.strip(),
            rationale_summary=rationale_summary.strip() if rationale_summary else "",
            status="pending",
            recorded_at=datetime.now(tz=UTC).isoformat(),
        )
        self._write_record(record)

    def resolve_pending(
        self,
        ticker: str,
        current_date: str,
        price_fetcher: Callable[[str, str, str], float | None] | None = None,
    ) -> list[DecisionRecord]:
        """Resolve pending decisions older than holding_period_days.

        Called at the start of propagate(), before graph execution.
        Fetches actual returns and SPY benchmark for the holding period.

        Args:
            ticker: Current ticker being analyzed (resolves only this ticker's pending).
            current_date: Today's date for determining which decisions are resolvable.
            price_fetcher: Optional callable(ticker, start_date, end_date) -> float | None.
                          Defaults to yfinance-based fetcher.

        Returns:
            List of newly resolved DecisionRecord objects.
        """
        if price_fetcher is None:
            price_fetcher = _default_price_fetcher

        records = self._read_all_records()
        current_dt = datetime.strptime(current_date, "%Y-%m-%d")
        resolved: list[DecisionRecord] = []

        for record in records:
            if record.status != "pending":
                continue
            if record.ticker != ticker:
                continue

            trade_dt = datetime.strptime(record.trade_date, "%Y-%m-%d")
            resolution_date = trade_dt + timedelta(days=self._holding_period_days)

            # Only resolve if holding period has elapsed
            if current_dt < resolution_date:
                continue

            # Fetch actual return for the holding period
            start_date = record.trade_date
            end_date = resolution_date.strftime("%Y-%m-%d")

            actual_return = price_fetcher(ticker, start_date, end_date)
            if actual_return is None:
                # Price data unavailable — leave as pending
                continue

            benchmark_return = price_fetcher("SPY", start_date, end_date)
            if benchmark_return is None:
                benchmark_return = 0.0  # Default benchmark to 0 if unavailable

            alpha = actual_return - benchmark_return

            new_record = DecisionRecord(
                ticker=record.ticker,
                trade_date=record.trade_date,
                rating=record.rating,
                rationale_summary=record.rationale_summary,
                status="resolved",
                recorded_at=record.recorded_at,
                actual_return=round(actual_return, 6),
                benchmark_return=round(benchmark_return, 6),
                alpha=round(alpha, 6),
                resolved_at=datetime.now(tz=UTC).isoformat(),
            )
            self._update_record(record, new_record)
            resolved.append(new_record)

        return resolved

    def get_cross_ticker_lessons(
        self,
        exclude_ticker: str,
        n: int = 3,
    ) -> str:
        """Get formatted lessons from other tickers' resolved decisions.

        Prioritizes recent decisions with the largest absolute alpha.

        Args:
            exclude_ticker: Ticker to exclude (the current analysis target).
            n: Maximum number of lessons to return.

        Returns:
            Formatted context string for prompt injection, or empty string if none.
        """
        records = self._read_all_records()

        # Filter to resolved records from other tickers
        resolved = [
            r
            for r in records
            if r.status == "resolved" and r.ticker != exclude_ticker and r.alpha is not None
        ]

        if not resolved:
            return ""

        # Sort by abs(alpha) descending, then by trade_date descending for recency tie-break
        resolved.sort(
            key=lambda r: (-abs(r.alpha if r.alpha is not None else 0), -_date_ordinal(r.trade_date))
        )
        top_n = resolved[:n]

        if not top_n:
            return ""

        lines = ["## Cross-Ticker Decision Lessons\n"]
        for record in top_n:
            outcome = "gain" if (record.actual_return or 0) > 0 else "loss"
            alpha_pct = (record.alpha or 0) * 100
            actual_pct = (record.actual_return or 0) * 100
            lesson = (
                f"- **{record.ticker}** ({record.trade_date}): Rated {record.rating}, "
                f"actual {outcome} of {actual_pct:+.1f}% (alpha {alpha_pct:+.1f}% vs SPY). "
                f"Rationale: {record.rationale_summary[:100]}"
            )
            lines.append(lesson)

        return "\n".join(lines)

    def _read_all_records(self) -> list[DecisionRecord]:
        """Read all records from the JSONL log."""
        if not self.log_path.exists():
            return []

        records: list[DecisionRecord] = []
        with open(self.log_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    records.append(DecisionRecord.from_dict(data))
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logger.warning(
                        "Skipping malformed JSONL line %d in %s: %s",
                        line_num,
                        self.log_path,
                        e,
                    )
        return records

    def _write_record(self, record: DecisionRecord) -> None:
        """Append a single record to the JSONL log (atomic write)."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict()) + "\n")

    def _update_record(self, old_record: DecisionRecord, new_record: DecisionRecord) -> None:
        """Update a record in-place by rewriting the log.

        Matches on (ticker, trade_date, recorded_at) as a composite key.
        For the expected log sizes (hundreds of records), full rewrite is acceptable.
        """
        records = self._read_all_records()
        updated = False

        for i, r in enumerate(records):
            if (
                r.ticker == old_record.ticker
                and r.trade_date == old_record.trade_date
                and r.recorded_at == old_record.recorded_at
            ):
                records[i] = new_record
                updated = True
                break

        if not updated:
            logger.warning(
                "Could not find record to update: %s %s %s",
                old_record.ticker,
                old_record.trade_date,
                old_record.recorded_at,
            )
            return

        # Rewrite the entire file atomically
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record.to_dict()) + "\n")


def _date_ordinal(date_str: str) -> int:
    """Convert YYYY-MM-DD to an ordinal for sorting."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").toordinal()
    except (ValueError, TypeError):
        return 0
