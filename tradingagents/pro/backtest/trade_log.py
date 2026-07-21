"""Enriched trade log: join each closed backtest trade to the full pipeline
decision that produced it.

A ``ClosedTrade`` from the sim broker carries only execution facts (entry,
exit, pnl, reason, ``recommendation_id``). The *why* — agent votes, evidence,
counterarguments, the chief-quant (critic) verdict, the risk-engine decision,
confidence, regime, R:R — lives in the pipeline ``state`` captured at decision
time. This module joins the two by ``recommendation_id`` into one row per trade
with every field an institutional trade blotter expects, and writes CSV + JSON.

Every value is copied from the recorded run; nothing is recomputed except the
exact commission split (gross price-move minus the broker's net pnl) and the
percentage return on entry notional.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from tradingagents.pro.backtest.broker import ClosedTrade


@dataclass
class EnrichedTrade:
    trade_id: str
    recommendation_id: str
    symbol: str
    direction: str  # BUY | SELL
    opened_at: str
    closed_at: str
    holding_hours: float
    entry_price: float
    exit_price: float
    stop_loss: float | None
    take_profits: list[float]
    position_size: float
    exit_reason: str
    gross_pnl: float  # price-move pnl on filled prices, before commission
    net_pnl: float  # broker-authoritative (net of commission + slippage)
    commission: float  # gross_pnl - net_pnl
    pct_return: float  # net_pnl / entry notional
    risk_reward: float | None
    confidence: int | None
    market_regime: str | None
    strategy: str | None  # the system runs one regime-adaptive strategy
    portfolio_pct_equity: float | None
    outcome: str  # Win | Loss | Breakeven
    chief_quant: str  # critic gate verdict
    risk_engine: str  # risk gate verdict
    vote_breakdown: list[dict] = field(default_factory=list)
    key_evidence: list[str] = field(default_factory=list)
    counterarguments: list[str] = field(default_factory=list)


def _pass_default(verdict: str) -> str:
    """An executed trade cleared every gate; an unrecorded (passing) gate
    reports 'pass' rather than 'n/a'."""
    return "pass" if verdict == "n/a" else verdict


def _gate_verdict(gate_results: dict, name: str) -> str:
    g = (gate_results or {}).get(name)
    if not isinstance(g, dict):
        return "n/a"
    passed = g.get("passed")
    issues = g.get("issues") or g.get("reasons") or []
    tag = "pass" if passed else "fail"
    return f"{tag}: {'; '.join(str(i) for i in issues)}" if issues else tag


def enrich_trades(
    trades: list[ClosedTrade],
    states_by_rec_id: dict[str, dict[str, Any]],
    initial_equity: float,
) -> list[EnrichedTrade]:
    """One ``EnrichedTrade`` per closed trade, joined to its decision state."""
    out: list[EnrichedTrade] = []
    for n, t in enumerate(trades, start=1):
        state = states_by_rec_id.get(t.recommendation_id, {})
        rec = state.get("recommendation")
        gates = state.get("gate_results", {})
        sign = 1.0 if t.side == "BUY" else -1.0
        gross = sign * (t.exit_price - t.entry_price) * t.quantity
        notional = t.entry_price * t.quantity
        hold_h = (t.closed_at - t.opened_at).total_seconds() / 3600.0
        outcome = "Win" if t.pnl > 0 else "Loss" if t.pnl < 0 else "Breakeven"

        confidence = getattr(rec, "confidence", None)
        regime = getattr(getattr(rec, "market_regime", None), "value", None)
        rr = getattr(rec, "risk_reward", None)
        tps = [tp.price for tp in getattr(rec, "take_profits", []) or []]
        stop = getattr(rec, "stop_loss", None)
        pos = getattr(rec, "position_size", None)
        pct_equity = getattr(pos, "pct_of_equity", None) if pos else None
        votes = [
            {"agent_id": v.agent_id, "vote": v.vote.value, "confidence": v.confidence}
            for v in getattr(getattr(rec, "vote_breakdown", None), "votes", []) or []
        ]
        evidence = [e.claim for e in getattr(rec, "evidence", []) or []][:5]
        counters = [e.claim for e in getattr(rec, "counterarguments", []) or []][:5]

        out.append(
            EnrichedTrade(
                trade_id=f"BT-{n:04d}",
                recommendation_id=t.recommendation_id,
                symbol=t.symbol,
                direction=t.side,
                opened_at=_iso(t.opened_at),
                closed_at=_iso(t.closed_at),
                holding_hours=round(hold_h, 3),
                entry_price=t.entry_price,
                exit_price=t.exit_price,
                stop_loss=stop,
                take_profits=tps,
                position_size=t.quantity,
                exit_reason=t.reason,
                gross_pnl=round(gross, 6),
                net_pnl=round(t.pnl, 6),
                commission=round(gross - t.pnl, 6),
                pct_return=round(t.pnl / notional, 6) if notional > 0 else 0.0,
                risk_reward=rr,
                confidence=confidence,
                market_regime=regime,
                strategy=regime,  # one regime-adaptive multi-agent strategy
                portfolio_pct_equity=pct_equity,
                outcome=outcome,
                # every enriched trade executed, so it cleared both gates;
                # surface the structured verdict when present, else "pass".
                chief_quant=_pass_default(_gate_verdict(gates, "critic")),
                risk_engine=_pass_default(_gate_verdict(gates, "risk_gate")),
                vote_breakdown=votes,
                key_evidence=evidence,
                counterarguments=counters,
            )
        )
    return out


def _iso(dt: datetime) -> str:
    return dt.isoformat() if isinstance(dt, datetime) else str(dt)


# CSV columns that hold nested structures are JSON-encoded so the file stays
# a flat, spreadsheet-loadable grid without losing the debate detail.
_JSON_COLUMNS = ("take_profits", "vote_breakdown", "key_evidence", "counterarguments")


def write_csv(path: Path, rows: list[EnrichedTrade]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(EnrichedTrade.__dataclass_fields__.keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            d = asdict(row)
            for col in _JSON_COLUMNS:
                d[col] = json.dumps(d[col], ensure_ascii=False)
            writer.writerow(d)


def write_json(path: Path, rows: list[EnrichedTrade]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(r) for r in rows], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
