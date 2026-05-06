"""End-to-end runner: agent committee -> MarketDecision -> ledger (-> Kalshi).

The runner is the thin orchestration layer that takes a Kalshi contract
identifier, runs the full agent pipeline against it, parses the
resulting ``MarketDecision``, sizes the stake, and either records
the intended trade (paper mode) or actually places the order (live).

Three concurrent guards prevent accidental live trading:
  1. ``paper_mode`` config flag (default True)
  2. ``TRADINGAGENTS_LIVE_DISABLED`` env var (kill switch)
  3. ``--live`` opt-in flag at the call site

Live mode requires all three to align (config off, env unset, caller opted-in).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple

from tradingagents.agents.schemas import (
    Confidence,
    MarketDecision,
    MarketSide,
)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

from . import kalshi_client, order_ledger, sizing
from .safety import resolve_mode

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    decision_id: str
    mode: str
    contract_id: str
    trade_date: str
    final_decision_markdown: str
    parsed_decision: Optional[MarketDecision]
    stake_plan: Optional[sizing.StakePlan]
    venue_order_id: Optional[str]
    notes: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.parsed_decision is not None:
            d["parsed_decision"] = self.parsed_decision.model_dump()
        if self.stake_plan is not None:
            d["stake_plan"] = asdict(self.stake_plan)
            d["stake_plan"]["side"] = self.stake_plan.side.value
        return d


# ---------------------------------------------------------------------------
# Decision parsing
# ---------------------------------------------------------------------------


_DECISION_FIELD_RE = re.compile(
    r"\*\*(?P<key>[A-Za-z_ ()]+?)\*\*\s*:\s*(?P<value>.+?)(?=\n\*\*|\Z)",
    re.DOTALL,
)


def _coerce_float(value: str) -> Optional[float]:
    cleaned = value.strip().replace(",", "").rstrip(".")
    cleaned = re.sub(r"[^\d\.\-eE+]", "", cleaned)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_market_decision(markdown: str) -> Optional[MarketDecision]:
    """Best-effort parse of the markdown the PM emits back into a MarketDecision.

    The PM's render_market_decision already produces stable headers
    (``**Recommended Side**``, ``**p_yes (committee)**``, ``**edge_bps**``,
    etc.) so this round-trip works for the structured-output path. When
    the PM fell back to free-text, parsing may return None for one or
    more fields — the runner falls back to a PASS plan in that case.
    """
    if not markdown:
        return None

    matches = {m.group("key").strip().lower(): m.group("value").strip()
               for m in _DECISION_FIELD_RE.finditer(markdown)}

    side_raw = matches.get("recommended side", "").upper()
    side = None
    for member in MarketSide:
        if member.value == side_raw:
            side = member
            break
    if side is None:
        # Fallback: rating line on free-text outputs
        rating = matches.get("rating", "").lower()
        if rating in ("buy", "overweight"):
            side = MarketSide.YES
        elif rating in ("sell", "underweight"):
            side = MarketSide.NO
        else:
            side = MarketSide.PASS

    confidence_raw = matches.get("confidence", "").lower()
    confidence = next(
        (c for c in Confidence if c.value == confidence_raw),
        Confidence.LOW,
    )

    p_yes = _coerce_float(matches.get("p_yes (committee)", "")) or 0.5
    market_p_yes = _coerce_float(matches.get("market_p_yes (kalshi)", "")) or p_yes
    edge_bps = _coerce_float(matches.get("edge_bps", ""))
    if edge_bps is None:
        edge_bps = (p_yes - market_p_yes) * 10000
    kelly_fraction = _coerce_float(matches.get("kelly fraction", "")) or 0.0

    return MarketDecision(
        p_yes=max(0.0, min(1.0, p_yes)),
        market_p_yes=max(0.0, min(1.0, market_p_yes)),
        edge_bps=edge_bps,
        recommended_side=side,
        confidence=confidence,
        kelly_fraction=max(0.0, min(1.0, kelly_fraction)),
        executive_summary=matches.get("executive summary", "").strip() or "—",
        investment_thesis=matches.get("investment thesis", "").strip() or "—",
        key_risks=matches.get("key risks", "").strip() or "—",
    )


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def run_contract(
    contract_id: str,
    trade_date: str,
    *,
    requested_live: bool = False,
    config: Optional[Dict] = None,
    bankroll_usd: Optional[float] = None,
) -> RunResult:
    """Run the full agent pipeline + execution layer for a single contract.

    Args:
        contract_id: Kalshi contract ticker.
        trade_date: Decision date in YYYY-MM-DD.
        requested_live: Caller opt-in for live trading. Even when True, the
            kill-switch env var or paper_mode config will down-grade to paper.
        config: Optional config dict; defaults to DEFAULT_CONFIG.
        bankroll_usd: Override bankroll (default: balance from Kalshi when
            live, else 1000.0 for paper).
    """
    config = config or DEFAULT_CONFIG
    mode = resolve_mode(requested_live=requested_live, config=config)

    logger.info(
        "Running pipeline for %s on %s in %s mode (requested_live=%s)",
        contract_id, trade_date, mode, requested_live,
    )

    graph = TradingAgentsGraph(config=config)
    final_state, decision_markdown = graph.propagate(contract_id, trade_date)

    parsed = parse_market_decision(decision_markdown)

    kalshi_cfg = config.get("kalshi", {})
    max_stake_usd = float(kalshi_cfg.get("max_stake_usd", 100.0))

    if bankroll_usd is None:
        bankroll_usd = _resolve_bankroll(mode=mode, default=1000.0)

    stake_plan = (
        sizing.plan_stake(parsed, bankroll_usd=bankroll_usd, max_stake_usd=max_stake_usd)
        if parsed is not None
        else None
    )

    decision_id = order_ledger.record_decision(
        config=config,
        contract_id=contract_id,
        trade_date=trade_date,
        mode=mode,
        side=stake_plan.side.value if stake_plan else None,
        count=stake_plan.contract_count if stake_plan else None,
        price_cents=stake_plan.price_cents if stake_plan else None,
        p_yes=parsed.p_yes if parsed else None,
        market_p_yes=parsed.market_p_yes if parsed else None,
        edge_bps=parsed.edge_bps if parsed else None,
        confidence=parsed.confidence.value if parsed else None,
        kelly_fraction=parsed.kelly_fraction if parsed else None,
        stake_usd=stake_plan.stake_usd if stake_plan else None,
        decision_payload={"final_state_keys": list(final_state.keys())},
    )

    venue_order_id: Optional[str] = None
    notes = stake_plan.notes if stake_plan else "PM output could not be parsed."

    if stake_plan and stake_plan.should_execute:
        if mode == "live":
            try:
                response = kalshi_client.place_order(
                    contract_id=contract_id,
                    side=stake_plan.side.value.lower(),
                    count=stake_plan.contract_count,
                    order_type="limit",
                    price_cents=stake_plan.price_cents,
                    client_order_id=decision_id,
                )
                order = response.get("order") or {}
                venue_order_id = order.get("order_id")
                order_ledger.update_status(
                    config=config,
                    decision_id=decision_id,
                    status="submitted",
                    venue_order_id=venue_order_id,
                    submitted_at=time.time(),
                )
                notes += f"\nLive order submitted: {venue_order_id}"
            except Exception as e:  # noqa: BLE001
                order_ledger.update_status(
                    config=config,
                    decision_id=decision_id,
                    status="rejected",
                    last_error=str(e),
                )
                notes += f"\nLive order failed: {e}"
                logger.exception("Live order placement failed for %s", contract_id)
        else:
            order_ledger.update_status(
                config=config,
                decision_id=decision_id,
                status="paper",
            )
            notes += "\nPaper mode: order recorded in ledger but not sent to Kalshi."
    else:
        order_ledger.update_status(
            config=config,
            decision_id=decision_id,
            status="passed",
        )

    return RunResult(
        decision_id=decision_id,
        mode=mode,
        contract_id=contract_id,
        trade_date=trade_date,
        final_decision_markdown=decision_markdown,
        parsed_decision=parsed,
        stake_plan=stake_plan,
        venue_order_id=venue_order_id,
        notes=notes,
    )


def _resolve_bankroll(*, mode: str, default: float) -> float:
    """Pull live cash balance from Kalshi when in live mode; default in paper."""
    if mode != "live":
        return default
    try:
        balance = kalshi_client.get_balance()
        cents = balance.get("balance") or balance.get("balance_cents")
        if cents is not None:
            return float(cents) / 100.0
    except Exception as e:  # noqa: BLE001 — non-fatal: fall back to default.
        logger.warning("Could not resolve Kalshi balance: %s", e)
    return default
