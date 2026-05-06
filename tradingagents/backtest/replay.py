"""Replay a single historical Kalshi contract through the agent committee.

The hard part of a faithful backtest is **point-in-time data**: when the
committee runs against a historical contract, it must see the world as it
existed at decision time, not the present. The replay shim achieves this
by monkey-patching the data layer fetchers to read from the
``HistoricalContract`` fixtures instead of hitting live APIs.

What's replayed:
- Coinbase candles (from the fixture's ``candles_to_decision`` list).
- Kalshi market state (synthesized from the fixture's
  ``kalshi_p_yes_at_decision`` value).

What's NOT replayed (yet — Phase 5+ work):
- News snapshots: RSS doesn't expose history reliably. Plug a paid
  archive (NewsAPI archive, GDELT) into ``patches`` to support it.
- On-chain history: blockchain.com's chart endpoints accept ``timespan``
  but the latest-N-days framing biases toward the present. For
  fidelity, snapshot the on-chain summary into the fixture at
  collection time.

Until those snapshots are wired, the replay still works but the news +
on-chain analysts read live data. That's a known fidelity hole and is
documented below; users running real sweeps will want to fix it before
relying on the calibration metric.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, Callable, Dict, Iterator, Optional
from unittest.mock import patch

from tradingagents.backtest.data_collector import HistoricalContract
from tradingagents.backtest.metrics import BacktestRecord
from tradingagents.execution.runner import RunResult, run_contract

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def frozen_data_layer(contract: HistoricalContract) -> Iterator[None]:
    """Patch the data-layer fetchers to serve ``contract``'s frozen snapshots."""

    candles_at_decision = contract.candles_to_decision

    def fake_get_candles(
        symbol: str = "BTC",
        granularity: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ):
        return candles_at_decision

    def fake_get_market(_contract_id: str):
        p = contract.kalshi_p_yes_at_decision
        if p is None:
            return None
        cents_yes = int(round(p * 100))
        cents_no = max(0, 100 - cents_yes)
        return {
            "ticker": contract.contract_id,
            "status": "open",
            "yes_bid": cents_yes - 1,
            "yes_ask": cents_yes + 1,
            "no_bid": cents_no - 1,
            "no_ask": cents_no + 1,
            "last_price": cents_yes,
        }

    def fake_get_market_p_yes(_contract_id: str):
        return contract.kalshi_p_yes_at_decision

    with patch("tradingagents.dataflows.coinbase.get_candles", side_effect=fake_get_candles), \
         patch("tradingagents.dataflows.kalshi_market.get_market", side_effect=fake_get_market), \
         patch("tradingagents.dataflows.kalshi_market.get_market_p_yes", side_effect=fake_get_market_p_yes):
        yield


def replay_contract(
    contract: HistoricalContract,
    *,
    config: Optional[Dict[str, Any]] = None,
) -> RunResult:
    """Run the agent committee against a single historical contract.

    Always runs in paper mode regardless of config. Backtests must never
    place real orders.
    """
    config = dict(config or {})
    kalshi_cfg = dict(config.get("kalshi", {}))
    kalshi_cfg["paper_mode"] = True
    config["kalshi"] = kalshi_cfg

    with frozen_data_layer(contract):
        result = run_contract(
            contract_id=contract.contract_id,
            trade_date=contract.decision_date,
            requested_live=False,
            config=config,
        )
    return result


def to_record(contract: HistoricalContract, result: RunResult) -> BacktestRecord:
    """Translate a replay run into a metrics-friendly BacktestRecord."""
    parsed = result.parsed_decision
    plan = result.stake_plan

    side = plan.side.value if plan else "PASS"
    realized_pnl = 0.0
    if plan and plan.should_execute:
        cost = (plan.price_cents / 100.0) * plan.contract_count
        won = (side == contract.settlement_outcome)
        realized_pnl = (plan.contract_count if won else 0.0) - cost

    return BacktestRecord(
        contract_id=contract.contract_id,
        decision_date=contract.decision_date,
        side=side,
        p_yes_committee=parsed.p_yes if parsed else 0.5,
        p_yes_market=parsed.market_p_yes if parsed else (contract.kalshi_p_yes_at_decision or 0.5),
        edge_bps=parsed.edge_bps if parsed else 0.0,
        confidence=parsed.confidence.value if parsed else "low",
        kelly_fraction=parsed.kelly_fraction if parsed else 0.0,
        stake_usd=plan.stake_usd if plan else 0.0,
        settlement_outcome=contract.settlement_outcome,
        realized_pnl_usd=realized_pnl,
    )
