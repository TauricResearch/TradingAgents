"""ProMemory: the facade the pipeline talks to.

Responsibilities:
- record trades, outcomes, regimes, reflections (append-only store + index)
- derive lesson records (mistake / winning pattern) when trades close
- semantic retrieval and historical-analog construction for debates
- win statistics for the Kelly agent (Phase 3 left it dormant until now)

The base framework's TradingMemoryLog is untouched; this is the Pro
layer's memory, persisted separately (ADR-0021).
"""

from __future__ import annotations

import logging
from pathlib import Path

from tradingagents.contracts import (
    HistoricalAnalog,
    MarketRegime,
    MarketSnapshot,
    TradeRecommendation,
    utc_now,
)
from tradingagents.pro.memory.embedding import EmbeddingFn, HashingEmbedder
from tradingagents.pro.memory.graph import KnowledgeGraph, default_graph_for
from tradingagents.pro.memory.index import InMemoryVectorIndex, SearchHit, VectorIndex
from tradingagents.pro.memory.records import MemoryKind, MemoryRecord
from tradingagents.pro.memory.store import JsonlStore

logger = logging.getLogger(__name__)

MIN_TRADES_FOR_STATS = 5


def describe_snapshot(snapshot: MarketSnapshot, regime: MarketRegime) -> str:
    """Deterministic text sketch of current conditions, used as the analog query."""
    parts = [snapshot.symbol, snapshot.asset.value, f"regime {regime.value}"]
    if snapshot.session:
        parts.append(f"session {snapshot.session.value}")
    for reading in snapshot.indicators:
        for key, value in reading.value.items():
            label = reading.name if key == "value" else f"{reading.name} {key}"
            parts.append(f"{label} {value:.2f}")
    for metric in [*snapshot.macro, *snapshot.onchain]:
        parts.append(f"{metric.name} {metric.value:.4g}")
    return " ".join(parts)


class ProMemory:
    def __init__(
        self,
        store_path: str | Path | None = None,
        index: VectorIndex | None = None,
        embedder: EmbeddingFn | None = None,
        graph: KnowledgeGraph | None = None,
    ):
        self._store = JsonlStore(store_path) if store_path else None
        self._index = index if index is not None else InMemoryVectorIndex()
        self._embed = embedder if embedder is not None else HashingEmbedder()
        self._graph = graph
        self._records: dict[str, MemoryRecord] = {}
        if self._store:
            for record in self._store.load():
                self._records[record.id] = record
                self._index.add(record, self._embed(record.text))

    # --- write path -----------------------------------------------------------

    def _add(self, record: MemoryRecord) -> MemoryRecord:
        self._records[record.id] = record
        self._index.add(record, self._embed(record.text))
        if self._store:
            self._store.append(record)
        return record

    def record_trade(
        self, recommendation: TradeRecommendation, regime: MarketRegime | None = None
    ) -> MemoryRecord:
        regime = regime or recommendation.market_regime
        claims = "; ".join(e.claim for e in recommendation.evidence[:5])
        text = (
            f"{recommendation.action.value} {recommendation.symbol} in regime "
            f"{regime.value} confidence {recommendation.confidence}. Basis: {claims}"
        )
        return self._add(MemoryRecord(
            kind=MemoryKind.TRADE,
            text=text,
            symbol=recommendation.symbol,
            payload={
                "recommendation_id": recommendation.id,
                "action": recommendation.action.value,
                "confidence": recommendation.confidence,
                "regime": regime.value,
                "entry_price": recommendation.entry_price,
                "stop_loss": recommendation.stop_loss,
                "risk_reward": recommendation.risk_reward,
            },
        ))

    def close_trade(
        self, trade_record_id: str, pnl: float, lesson: str = ""
    ) -> list[MemoryRecord]:
        """Record a trade outcome; derive a lesson record from the result."""
        trade = self._records.get(trade_record_id)
        if trade is None or trade.kind is not MemoryKind.TRADE:
            raise KeyError(f"no trade record {trade_record_id}")
        won = pnl > 0
        added = [self._add(MemoryRecord(
            kind=MemoryKind.OUTCOME,
            text=f"outcome of {trade.text}: pnl {pnl:+.4f} ({'win' if won else 'loss'})",
            symbol=trade.symbol,
            ref_id=trade.id,
            payload={"pnl": pnl, "won": won, "closed_at": utc_now().isoformat()},
        ))]
        lesson_kind = MemoryKind.WINNING_PATTERN if won else MemoryKind.MISTAKE
        lesson_text = lesson or (
            f"{trade.payload.get('action')} {trade.symbol} in regime "
            f"{trade.payload.get('regime')} {'worked' if won else 'failed'} "
            f"(pnl {pnl:+.4f})"
        )
        added.append(self._add(MemoryRecord(
            kind=lesson_kind, text=lesson_text, symbol=trade.symbol, ref_id=trade.id,
            payload={"pnl": pnl},
        )))
        return added

    def find_trade_by_recommendation(self, recommendation_id: str) -> MemoryRecord | None:
        """The trade record the pipeline wrote for a given recommendation —
        the handle the backtester/execution layer uses to close the loop."""
        for record in self._records.values():
            if (
                record.kind is MemoryKind.TRADE
                and record.payload.get("recommendation_id") == recommendation_id
            ):
                return record
        return None

    def record_regime(self, symbol: str, regime: MarketRegime, features: dict) -> MemoryRecord:
        feature_text = " ".join(f"{k} {v:.4g}" for k, v in features.items())
        return self._add(MemoryRecord(
            kind=MemoryKind.REGIME,
            text=f"{symbol} regime {regime.value}: {feature_text}",
            symbol=symbol,
            payload={"regime": regime.value, **features},
        ))

    def record_reflection(self, symbol: str, weaknesses: str, invalidation: str) -> MemoryRecord:
        return self._add(MemoryRecord(
            kind=MemoryKind.REFLECTION,
            text=f"{symbol} reflection. Weaknesses: {weaknesses} Invalidation: {invalidation}",
            symbol=symbol,
            payload={"weaknesses": weaknesses, "invalidation": invalidation},
        ))

    def record_strategy(self, symbol: str, description: str, payload: dict | None = None):
        return self._add(MemoryRecord(
            kind=MemoryKind.STRATEGY, text=description, symbol=symbol,
            payload=payload or {},
        ))

    # --- read path -------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        k: int = 5,
        kinds: tuple[MemoryKind, ...] | None = None,
        symbol: str | None = None,
    ) -> list[SearchHit]:
        return self._index.search(self._embed(query), k=k, kinds=kinds, symbol=symbol)

    def historical_analogs(
        self, query: str, k: int = 3, symbol: str | None = None
    ) -> list[HistoricalAnalog]:
        """Closed trades resembling the query, as contract HistoricalAnalogs."""
        outcomes_by_trade = {
            r.ref_id: r for r in self._records.values() if r.kind is MemoryKind.OUTCOME
        }
        hits = self.retrieve(query, k=k * 3, kinds=(MemoryKind.TRADE,), symbol=symbol)
        analogs = []
        for hit in hits:
            outcome = outcomes_by_trade.get(hit.record.id)
            if outcome is None:
                continue  # open trades have no outcome; not an analog yet
            analogs.append(HistoricalAnalog(
                description=hit.record.text,
                period_start=hit.record.created_at,
                period_end=outcome.created_at,
                similarity=max(0.0, min(1.0, hit.score)),
                outcome=outcome.text,
                memory_ref=hit.record.id,
            ))
            if len(analogs) == k:
                break
        return analogs

    def lessons(self, query: str, k: int = 3, symbol: str | None = None) -> list[SearchHit]:
        return self.retrieve(
            query, k=k, symbol=symbol,
            kinds=(MemoryKind.MISTAKE, MemoryKind.WINNING_PATTERN,
                   MemoryKind.REFLECTION, MemoryKind.STRATEGY),
        )

    def win_stats(self, symbol: str | None = None) -> tuple[float, float, float] | None:
        """(win_rate, avg_win, avg_loss) from closed trades; None below the
        minimum sample (fabricating a Kelly from 2 trades is worse than none)."""
        pnls = [
            r.payload["pnl"]
            for r in self._records.values()
            if r.kind is MemoryKind.OUTCOME and (symbol is None or r.symbol == symbol)
        ]
        if len(pnls) < MIN_TRADES_FOR_STATS:
            return None
        wins = [p for p in pnls if p > 0]
        losses = [-p for p in pnls if p < 0]
        if not wins or not losses:
            return None  # degenerate history; Kelly undefined
        return len(wins) / len(pnls), sum(wins) / len(wins), sum(losses) / len(losses)

    # --- knowledge graph ---------------------------------------------------------

    def relations_block(self, symbol: str) -> str:
        graph = self._graph or default_graph_for(symbol)
        return graph.to_prompt_block(symbol)
