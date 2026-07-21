"""Per-agent performance attribution over a backtest's enriched trades.

Extends the dashboard's vote-agreement scoring (``service.agent_performance``)
with P&L attribution and regime-conditioned accuracy:

- an agent that voted the executed direction is "aligned"; the opposite
  directional vote is "opposed"; HOLD is neutral (ignored);
- "correct" = aligned on a win, or opposed on a loss (it would have kept you
  out); the mirror is "incorrect"; breakeven is neutral;
- attributed P&L credits an aligned agent the trade's net pnl and debits an
  opposed agent the same (its dissent, had it won the debate, would have
  avoided the trade).

This is honest vote-level attribution — not a counterfactual re-run of the
pipeline without the agent (which the recorded data can't support). The report
states that limitation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from tradingagents.pro.backtest.trade_log import EnrichedTrade

_DIRECTIONS = {"BUY", "SELL"}


@dataclass
class AgentScore:
    agent_id: str
    votes: int
    aligned: int
    opposed: int
    correct: int
    incorrect: int
    hit_rate: float  # correct / scored (scored = aligned + opposed)
    avg_confidence: float
    attributed_pnl: float
    by_regime: dict[str, dict] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


def agent_attribution(trades: list[EnrichedTrade]) -> list[AgentScore]:
    """Score every agent that voted on an executed trade, ranked by attributed
    P&L (descending). Only directional trades contribute (each enriched trade
    is an executed BUY/SELL)."""
    acc: dict[str, dict] = {}

    for t in trades:
        won = t.outcome == "Win"
        lost = t.outcome == "Loss"
        for v in t.vote_breakdown:
            aid = v["agent_id"]
            vote = v["vote"]
            a = acc.setdefault(
                aid,
                {
                    "votes": 0, "aligned": 0, "opposed": 0,
                    "correct": 0, "incorrect": 0, "conf_sum": 0,
                    "pnl": 0.0, "regime": {},
                },
            )
            a["votes"] += 1
            a["conf_sum"] += v.get("confidence", 0)
            if vote not in _DIRECTIONS:
                continue  # HOLD / abstain: neutral
            aligned = vote == t.direction
            if aligned:
                a["aligned"] += 1
                a["pnl"] += t.net_pnl
            else:
                a["opposed"] += 1
                a["pnl"] -= t.net_pnl
            correct = (aligned and won) or (not aligned and lost)
            if won or lost:
                a["correct" if correct else "incorrect"] += 1
            reg = a["regime"].setdefault(
                t.market_regime or "unknown", {"scored": 0, "correct": 0}
            )
            if won or lost:
                reg["scored"] += 1
                reg["correct"] += 1 if correct else 0

    scores: list[AgentScore] = []
    for aid, a in acc.items():
        scored = a["correct"] + a["incorrect"]
        by_regime = {
            r: {
                "scored": d["scored"],
                "correct": d["correct"],
                "hit_rate": round(d["correct"] / d["scored"], 4) if d["scored"] else 0.0,
            }
            for r, d in a["regime"].items()
        }
        scores.append(
            AgentScore(
                agent_id=aid,
                votes=a["votes"],
                aligned=a["aligned"],
                opposed=a["opposed"],
                correct=a["correct"],
                incorrect=a["incorrect"],
                hit_rate=round(a["correct"] / scored, 4) if scored else 0.0,
                avg_confidence=round(a["conf_sum"] / a["votes"], 2) if a["votes"] else 0.0,
                attributed_pnl=round(a["pnl"], 4),
                by_regime=by_regime,
            )
        )
    scores.sort(key=lambda s: s.attributed_pnl, reverse=True)
    return scores
