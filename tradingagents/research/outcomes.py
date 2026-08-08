"""Outcome-provider port and a research-only adjusted-open adapter."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Protocol, runtime_checkable

from tradingagents.domain.contracts import canonical_json
from tradingagents.research.contracts import OutcomeObservation
from tradingagents.research.errors import OutcomeUnavailableError
from tradingagents.research.timeline import outcome_sessions
from tradingagents.research_protocol import GLOBAL_EVENT_V2_PROTOCOL

_POLICY = GLOBAL_EVENT_V2_PROTOCOL["portfolio"]["price_capture"][
    "exploratory_history_adapter"
]


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
        return str(_POLICY["provider_id"])

    @staticmethod
    def _endpoints(symbol: str, decision_date: date) -> list[dict] | None:
        import pandas as pd
        import yfinance as yf
        from curl_cffi.requests.exceptions import RequestException as CurlRequestError
        from requests.exceptions import RequestException as RequestsError
        from yfinance.exceptions import YFException

        try:
            frame = yf.Ticker(symbol).history(
                start=(decision_date - timedelta(days=2)).isoformat(),
                end=(decision_date + timedelta(days=15)).isoformat(),
                auto_adjust=True,
            )
        except (CurlRequestError, RequestsError, YFException):
            raise OutcomeUnavailableError("outcome provider unavailable") from None
        if frame.empty or "Open" not in frame:
            return None
        expected = outcome_sessions(decision_date)
        rows: dict[date, float] = {}
        for index, row in frame.sort_index().iterrows():
            session = pd.Timestamp(index).date()
            if session not in expected:
                continue
            value = float(row["Open"])
            if session in rows or not math.isfinite(value) or value <= 0.0:
                return None
            rows[session] = value
        if set(rows) != set(expected):
            return None
        return [
            {"date": session.isoformat(), "adjusted_open": rows[session]}
            for session in expected
        ]

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
                "schema_version": _POLICY["provenance_schema_version"],
                "provider": self.provider_name,
                "endpoints": endpoints,
                "price_semantics": _POLICY["price_semantics"],
            },
        )
