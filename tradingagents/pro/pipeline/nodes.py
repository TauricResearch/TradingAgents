"""Pipeline node implementations.

Every node returns a partial state update. Gates write ``rejection`` and
the graph routes to the terminal ``rejected`` node — a rejected run ends
with no TradeRecommendation (Constraint 4). LLM calls go through the same
injectable structured-output interface the evidence agents use.
"""

from __future__ import annotations

import logging
from importlib import resources
from typing import Any

from pydantic import ValidationError

from tradingagents.contracts import (
    AgentEvidence,
    AgentTeam,
    AgentVote,
    Direction,
    MarketRegime,
    MetricReading,
    PositionSize,
    ProConfig,
    TakeProfitLevel,
    TradeAction,
    TradeRecommendation,
    TradingMode,
)
from tradingagents.pro.agents import (
    SPECS_BY_TEAM,
    build_team,
    compute_quant_metrics,
    compute_risk_metrics,
    run_agents,
)
from tradingagents.pro.analytics import classify_regime
from tradingagents.pro.pipeline.gates import risk_gate
from tradingagents.pro.pipeline.schemas import (
    CriticReport,
    DebateTurn,
    JudgeVerdict,
    ReflectionNote,
)
from tradingagents.pro.pipeline.votes import (
    build_vote_breakdown,
    confidence_weighted_consensus,
    votes_from_evidence,
)

logger = logging.getLogger(__name__)

_OPPOSING = {TradeAction.BUY: Direction.BEARISH, TradeAction.SELL: Direction.BULLISH}
_SUPPORTING = {TradeAction.BUY: Direction.BULLISH, TradeAction.SELL: Direction.BEARISH}


def load_pipeline_prompt(name: str) -> str:
    return (
        resources.files("tradingagents.pro.pipeline")
        .joinpath("prompts", f"{name}.md")
        .read_text(encoding="utf-8")
    )


def _evidence_block(evidence: list[AgentEvidence]) -> str:
    if not evidence:
        return "(no evidence produced)"
    return "\n".join(
        f"- [{e.agent_id}] ({e.team.value}) {e.direction.value}, confidence {e.confidence}: "
        f"{e.claim}"
        for e in evidence
    )


def _debate_block(debate: list[dict]) -> str:
    if not debate:
        return "(debate has not started)"
    lines = []
    for entry in debate:
        cited = f" [cites: {', '.join(entry['cited'])}]" if entry.get("cited") else ""
        lines.append(
            f"{entry['speaker']} ({entry.get('stance', '-')}, "
            f"confidence {entry.get('confidence', '-')}): {entry['argument']}{cited}"
        )
    return "\n".join(lines)


def _all_evidence(state: dict) -> list[AgentEvidence]:
    return [e for team in state["evidence_by_team"].values() for e in team]


class PipelineNodes:
    """Node functions bound to an LLM, config, and equity base."""

    def __init__(self, llm, config: ProConfig, equity: float = 100_000.0):
        self.llm = llm
        self.config = config
        self.equity = equity
        self._prompts = {
            name: load_pipeline_prompt(name)
            for name in ("debate", "sentiment", "critic", "reflection", "judge")
        }

    def _invoke(self, schema, prompt: str):
        try:
            return self.llm.with_structured_output(schema).invoke(prompt)
        except Exception:
            logger.warning("pipeline structured call failed for %s", schema.__name__,
                           exc_info=True)
            return None

    # --- gather ----------------------------------------------------------------

    def gather(self, state: dict) -> dict[str, Any]:
        snapshot = state["snapshot"]
        bars = snapshot.bars
        quant = compute_quant_metrics(bars)
        risk = compute_risk_metrics(snapshot, self.config.risk, self.equity)
        extras: dict[str, MetricReading] = {**quant, **risk}

        evidence_by_team: dict[str, list[AgentEvidence]] = {}
        for team in (
            AgentTeam.TECHNICAL,
            AgentTeam.MACRO,
            AgentTeam.NEWS_SENTIMENT,
            AgentTeam.QUANT,
            AgentTeam.RISK,
        ):
            agents = build_team(SPECS_BY_TEAM[team], self.llm)
            evidence_by_team[team.value] = run_agents(agents, snapshot, extra_metrics=extras)

        regime = classify_regime(bars) if len(bars) >= 3 else MarketRegime.UNKNOWN
        update: dict[str, Any] = {
            "evidence_by_team": evidence_by_team,
            "quant_metrics": quant,
            "risk_metrics": risk,
            "regime": regime,
            "debate": [],
            "technical_rounds": 0,
            "macro_rounds": 0,
        }
        if not any(evidence_by_team.values()):
            update["rejection"] = {
                "stage": "gather",
                "reasons": ["no agent produced evidence; nothing to debate"],
            }
        return update

    # --- debate ----------------------------------------------------------------

    def _debate_turn(self, state: dict, team: AgentTeam, stance: str) -> dict:
        evidence = state["evidence_by_team"].get(team.value, [])
        prompt = self._prompts["debate"].format(
            stance=stance,
            team=team.value,
            symbol=state["snapshot"].symbol,
            asset=state["snapshot"].asset.value,
            evidence_block=_evidence_block(evidence),
            debate_block=_debate_block(state["debate"]),
        )
        turn = self._invoke(DebateTurn, prompt)
        entry = {
            "speaker": f"{team.value}_{stance}",
            "stance": stance,
            "argument": turn.argument if turn else "(abstained: structured output failed)",
            "cited": list(turn.cited_agent_ids) if turn else [],
            "confidence": turn.confidence if turn else 0,
        }
        return {"debate": [*state["debate"], entry]}

    def technical_bull(self, state: dict) -> dict:
        return self._debate_turn(state, AgentTeam.TECHNICAL, "bull")

    def technical_bear(self, state: dict) -> dict:
        update = self._debate_turn(state, AgentTeam.TECHNICAL, "bear")
        update["technical_rounds"] = state["technical_rounds"] + 1
        return update

    def macro_bull(self, state: dict) -> dict:
        return self._debate_turn(state, AgentTeam.MACRO, "bull")

    def macro_bear(self, state: dict) -> dict:
        update = self._debate_turn(state, AgentTeam.MACRO, "bear")
        update["macro_rounds"] = state["macro_rounds"] + 1
        return update

    def sentiment(self, state: dict) -> dict:
        evidence = state["evidence_by_team"].get(AgentTeam.NEWS_SENTIMENT.value, [])
        prompt = self._prompts["sentiment"].format(
            symbol=state["snapshot"].symbol,
            asset=state["snapshot"].asset.value,
            evidence_block=_evidence_block(evidence),
            debate_block=_debate_block(state["debate"]),
        )
        turn = self._invoke(DebateTurn, prompt)
        entry = {
            "speaker": "sentiment",
            "stance": "rapporteur",
            "argument": turn.argument if turn else "(abstained: structured output failed)",
            "cited": list(turn.cited_agent_ids) if turn else [],
            "confidence": turn.confidence if turn else 0,
        }
        return {"debate": [*state["debate"], entry]}

    # --- gates and judgment ------------------------------------------------------

    def risk_gate(self, state: dict) -> dict:
        result = risk_gate(state["risk_metrics"], self.config)
        update: dict[str, Any] = {
            "gate_results": {**state.get("gate_results", {}),
                             "risk": {"passed": result.passed,
                                      "checks": result.checks,
                                      "reasons": list(result.reasons)}},
        }
        if not result.passed:
            update["rejection"] = {"stage": "risk_gate", "reasons": list(result.reasons)}
        return update

    def critic(self, state: dict) -> dict:
        prompt = self._prompts["critic"].format(
            symbol=state["snapshot"].symbol,
            asset=state["snapshot"].asset.value,
            evidence_block=_evidence_block(_all_evidence(state)),
            debate_block=_debate_block(state["debate"]),
        )
        report = self._invoke(CriticReport, prompt)
        if report is None:
            # fail closed: an unauditable debate does not proceed
            report = CriticReport(verdict="fail", issues=["critic model unavailable"])
        entry = {
            "speaker": "critic",
            "stance": report.verdict,
            "argument": "; ".join(report.issues) if report.issues else "no defects found",
            "cited": [],
            "confidence": 100,
        }
        update: dict[str, Any] = {
            "debate": [*state["debate"], entry],
            "gate_results": {**state.get("gate_results", {}),
                             "critic": {"passed": report.verdict == "pass",
                                        "issues": report.issues}},
        }
        if report.verdict == "fail":
            update["rejection"] = {"stage": "critic", "reasons": report.issues}
        return update

    def reflection(self, state: dict) -> dict:
        prompt = self._prompts["reflection"].format(
            symbol=state["snapshot"].symbol,
            asset=state["snapshot"].asset.value,
            evidence_block=_evidence_block(_all_evidence(state)),
            debate_block=_debate_block(state["debate"]),
        )
        note = self._invoke(ReflectionNote, prompt)
        if note is None:
            note = ReflectionNote(
                weaknesses="reflection model unavailable; treat thesis as untested",
                invalidation="unknown — no invalidation condition was produced",
            )
        entry = {
            "speaker": "reflection",
            "stance": "falsification",
            "argument": f"Weaknesses: {note.weaknesses} Invalidation: {note.invalidation}",
            "cited": [],
            "confidence": 100,
        }
        return {
            "debate": [*state["debate"], entry],
            "reflection": {"weaknesses": note.weaknesses, "invalidation": note.invalidation},
        }

    def judge(self, state: dict) -> dict:
        evidence = _all_evidence(state)
        votes = votes_from_evidence(evidence)
        consensus_action, share = confidence_weighted_consensus(votes)
        prompt = self._prompts["judge"].format(
            symbol=state["snapshot"].symbol,
            asset=state["snapshot"].asset.value,
            vote_summary=(
                f"{consensus_action.value} carries {share:.0%} of confidence weight "
                f"across {len(votes)} agent votes"
            ),
            evidence_block=_evidence_block(evidence),
            debate_block=_debate_block(state["debate"]),
        )
        verdict = self._invoke(JudgeVerdict, prompt)
        if verdict is None:
            verdict = JudgeVerdict(
                action="HOLD", confidence=0,
                rationale="judge model unavailable; defaulting to HOLD",
            )
        action = TradeAction(verdict.action)
        judge_vote = AgentVote(agent_id="judge", vote=action, confidence=verdict.confidence)
        entry = {
            "speaker": "judge",
            "stance": action.value,
            "argument": verdict.rationale,
            "cited": [],
            "confidence": verdict.confidence,
        }
        return {
            "debate": [*state["debate"], entry],
            "judge_action": action,
            "judge_confidence": verdict.confidence,
            "judge_rationale": verdict.rationale,
            "vote_breakdown": build_vote_breakdown(evidence, judge_vote),
        }

    def portfolio_manager(self, state: dict) -> dict:
        snapshot = state["snapshot"]
        action: TradeAction = state["judge_action"]
        evidence = _all_evidence(state)

        if action is TradeAction.HOLD:
            recommendation = TradeRecommendation(
                symbol=snapshot.symbol,
                asset=snapshot.asset,
                action=TradeAction.HOLD,
                confidence=state["judge_confidence"],
                position_size=PositionSize(quantity=0),
                market_regime=state["regime"],
                evidence=evidence,
                vote_breakdown=state["vote_breakdown"],
            )
            return {"recommendation": recommendation}

        supporting = [e for e in evidence if e.direction is _SUPPORTING[action]]
        opposing = [e for e in evidence if e.direction is _OPPOSING[action]]
        if not supporting:
            return {"rejection": {
                "stage": "portfolio_manager",
                "reasons": [f"judge ruled {action.value} but no evidence supports it"],
            }}

        # Recompute engine levels for the ruled side (Constraint 2).
        sided = compute_risk_metrics(snapshot, self.config.risk, self.equity,
                                     side=action.value)
        gate = risk_gate(sided, self.config, proposed_action=action)
        if not gate.passed:
            return {"rejection": {"stage": "portfolio_manager",
                                  "reasons": list(gate.reasons)}}

        try:
            recommendation = TradeRecommendation(
                symbol=snapshot.symbol,
                asset=snapshot.asset,
                action=action,
                confidence=state["judge_confidence"],
                entry_price=sided["ENTRY_REF_PRICE"].value,
                stop_loss=sided["ATR_STOP"].value,
                take_profits=[
                    TakeProfitLevel(price=sided["ATR_TP1"].value, size_fraction=0.5),
                    TakeProfitLevel(price=sided["ATR_TP2"].value, size_fraction=0.5),
                ],
                position_size=PositionSize(
                    quantity=sided["POSITION_SIZE_UNITS"].value,
                    notional=sided["POSITION_NOTIONAL"].value,
                    pct_of_equity=sided["POSITION_PCT_EQUITY"].value,
                ),
                market_regime=state["regime"],
                evidence=supporting,
                counterarguments=opposing,
                vote_breakdown=state["vote_breakdown"],
            )
        except (ValidationError, KeyError) as exc:
            return {"rejection": {
                "stage": "portfolio_manager",
                "reasons": [f"recommendation failed contract validation: {exc}"],
            }}
        return {"recommendation": recommendation}

    def execution(self, state: dict) -> dict:
        if self.config.mode is TradingMode.LIVE:
            # Constraint 5: the human-approval graph node arrives in Phase 6;
            # until it exists, live routing is refused unconditionally.
            return {"execution_status":
                    "refused: live mode requires the human-approval node (Phase 6)"}
        return {"execution_status": f"accepted:{self.config.mode.value}"}

    def rejected(self, state: dict) -> dict:
        rejection = state.get("rejection") or {"stage": "unknown", "reasons": []}
        logger.info("pipeline rejected at %s: %s", rejection["stage"], rejection["reasons"])
        return {"recommendation": None,
                "execution_status": f"rejected:{rejection['stage']}"}
