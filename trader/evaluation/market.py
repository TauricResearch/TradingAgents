"""OKX as it looked at a past moment, served from the history store.

The engines (``Paper``, ``IntradayPaper``) ask the market for closed candles, the
last price, settled funding and contract specs. ``HistoricalOKX`` answers from the
store as of ``now_ms``: no candle that had not closed yet, no funding that had not
settled, and the last price is the close of the last minute candle closed by then,
which is what the live job would have seen a few seconds into the minute.
"""

from __future__ import annotations

from trader.evaluation.history import MINUTE_MS, HistoryStore, bar_ms
from trader.okx import Bar, ContractSpec, FundingEvent, OKXError


class HistoricalOKX:
    def __init__(self, store: HistoryStore, now_ms: int = 0):
        self.store = store
        self.now_ms = now_ms

    def at(self, now_ms: int) -> None:
        """Move the clock; every answer from now on is as of ``now_ms``."""
        self.now_ms = now_ms

    def bars(self, inst_id: str, bar: str, start_ms: int, end_ms: int) -> list[Bar]:
        """Candles with ``start_ms <= ts < end_ms`` that had closed by ``now_ms``."""
        last_open = self.now_ms - bar_ms(bar)  # a candle opened here has just closed
        return self.store.bars(inst_id, bar, start_ms, min(end_ms, last_open + 1))

    def last_price(self, inst_id: str) -> float:
        """Close of the last minute candle closed by ``now_ms``; OKXError when the store
        has no candle for the instrument before then."""
        close = self.store.last_close(inst_id, "1m", self.now_ms - MINUTE_MS + 1)
        if close is None:
            raise OKXError(f"no 1m candle of {inst_id} before {self.now_ms} in the history store")
        return close

    def funding(self, inst_id: str, start_ms: int, end_ms: int) -> list[FundingEvent]:
        return self.store.funding(inst_id, start_ms, min(end_ms, self.now_ms + 1))

    def contract_spec(self, inst_id: str) -> ContractSpec:
        spec = self.store.spec(inst_id)
        if spec is None:
            raise OKXError(f"no contract spec of {inst_id} in the history store")
        return spec
