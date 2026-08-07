"""Outcome-provider port and a research-only adjusted-open adapter."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Protocol, runtime_checkable

from tradingagents.domain.contracts import canonical_json
from tradingagents.research.contracts import OutcomeObservation


@runtime_checkable
class OutcomeProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    def observe(
        self,
        *,
        decision_date: date,
        universe: Sequence[str],
        benchmark: str,
    ) -> OutcomeObservation: ...


class YFinanceAdjustedOpenOutcomeProvider:
    """Attach next-open-to-following-open labels after decisions are committed."""

    @property
    def provider_name(self) -> str:
        return "yfinance-adjusted-daily-open"

    @staticmethod
    def _endpoints(symbol: str, decision_date: date) -> list[dict] | None:
        import pandas as pd
        import yfinance as yf

        frame = yf.Ticker(symbol).history(
            start=(decision_date - timedelta(days=2)).isoformat(),
            end=(decision_date + timedelta(days=15)).isoformat(),
            auto_adjust=True,
        )
        if frame.empty or "Open" not in frame:
            return None
        rows = []
        for index, row in frame.sort_index().iterrows():
            session = pd.Timestamp(index).date()
            if session <= decision_date:
                continue
            value = float(row["Open"])
            if value > 0:
                rows.append({"date": session.isoformat(), "adjusted_open": value})
            if len(rows) == 2:
                return rows
        return None

    def observe(
        self,
        *,
        decision_date: date,
        universe: Sequence[str],
        benchmark: str,
    ) -> OutcomeObservation:
        endpoints = {
            symbol: self._endpoints(symbol, decision_date)
            for symbol in (*universe, benchmark)
        }
        benchmark_rows = endpoints[benchmark]
        if benchmark_rows is None:
            entry_date = exit_date = None
            benchmark_return = None
        else:
            entry_date = date.fromisoformat(benchmark_rows[0]["date"])
            exit_date = date.fromisoformat(benchmark_rows[1]["date"])
            benchmark_return = (
                benchmark_rows[1]["adjusted_open"] / benchmark_rows[0]["adjusted_open"] - 1.0
            )
        asset_returns = {}
        for symbol in universe:
            rows = endpoints[symbol]
            if (
                rows is None
                or entry_date is None
                or rows[0]["date"] != entry_date.isoformat()
                or rows[1]["date"] != exit_date.isoformat()
            ):
                asset_returns[symbol] = None
            else:
                asset_returns[symbol] = (
                    rows[1]["adjusted_open"] / rows[0]["adjusted_open"] - 1.0
                )
        captured = datetime.now(timezone.utc).isoformat()
        raw_hash = hashlib.sha256(canonical_json(endpoints).encode("utf-8")).hexdigest()
        return OutcomeObservation(
            provider=self.provider_name,
            observed_at=datetime.fromisoformat(captured),
            vintage_id=f"yfinance:{captured}:{raw_hash[:16]}",
            raw_payload_sha256=raw_hash,
            entry_date=entry_date,
            exit_date=exit_date,
            asset_returns=asset_returns,
            benchmark_return=benchmark_return,
            cash_return=0.0,
            provenance={
                "endpoints": endpoints,
                "price_semantics": "provider adjusted regular-session daily Open",
            },
        )
