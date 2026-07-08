"""Pipeline node implementations.

Every node returns a partial state update. Gates write ``rejection`` and
the graph routes to the terminal ``rejected`` node — a rejected run ends
with no TradeRecommendation (Constraint 4). LLM calls go through the same
injectable structured-output interface the evidence agents use.

Phase 6: evidence gathering is split into ``prepare`` + five parallel team
nodes + a ``join`` gate; live mode pauses at the ``human_approval`` node
(LangGraph interrupt) and only an explicit approval resumes into execution.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from importlib import resources
from typing import Any

from langgraph.types import interrupt
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


# Fixed iteration order keeps votes/evidence deterministic regardless of
# which parallel team branch finished first.
TEAM_ORDER = (
    AgentTeam.TECHNICAL,
    AgentTeam.MACRO,
    AgentTeam.NEWS_SENTIMENT,
    AgentTeam.QUANT,
    AgentTeam.RISK,
)


def _all_evidence(state: dict) -> list[AgentEvidence]:
    by_team = state["evidence_by_team"]
    return [e for team in TEAM_ORDER for e in by_team.get(team.value, [])]


def _with_memory(evidence_block: str, state: dict) -> str:
    """Append the memory context (analogs, lessons, relations) to an
    evidence block; the record shown to debaters includes what the desk
    has learned, with the same no-invention rules."""
    context = state.get("memory_context") or ""
    return f"{evidence_block}\n\n{context}" if context else evidence_block


class PipelineNodes:
    """Node functions bound to an LLM, config, equity base, and optional memory.

    ``llm_retries`` bounds re-attempts of failed structured calls;
    ``agent_workers`` > 1 runs a team's evidence agents on a thread pool
    (LLM calls are I/O bound).
    """

    def __init__(
        self,
        llm,
        config: ProConfig,
        equity: float = 100_000.0,
        memory=None,
        llm_retries: int = 1,
        agent_workers: int = 1,
    ):
        if llm_retries < 0 or agent_workers < 1:
            raise ValueError("llm_retries must be >= 0 and agent_workers >= 1")
        self.llm = llm
        self.config = config
        self.equity = equity
        self.memory = memory  # ProMemory | None (duck-typed; tests may fake it)
        self.llm_retries = llm_retries
        self.agent_workers = agent_workers
        self._prompts = {
            name: load_pipeline_prompt(name)
            for name in ("debate", "sentiment", "critic", "reflection", "judge")
        }

    def _invoke(self, schema, prompt: str):
        for attempt in range(1 + self.llm_retries):
            try:
                return self.llm.with_structured_output(schema).invoke(prompt)
            except Exception:
                logger.warning(
                    "pipeline structured call failed for %s (attempt %d/%d)",
                    schema.__name__, attempt + 1, 1 + self.llm_retries, exc_info=True,
                )
        return None

    # --- prepare -> parallel teams -> join ------------------------------------

    def prepare(self, state: dict) -> dict[str, Any]:
        """Deterministic pre-work: engine metrics, regime, memory context."""
        snapshot = state["snapshot"]
        bars = snapshot.bars
        quant = compute_quant_metrics(bars)
        stats = self.memory.win_stats(snapshot.symbol) if self.memory else None
        win_kwargs = (
            {"win_rate": stats[0], "avg_win": stats[1], "avg_loss": stats[2]}
            if stats
            else {}
        )
        equity = state.get("equity") or self.equity
        risk = compute_risk_metrics(
            snapshot, self.config.risk, equity, **win_kwargs
        )
        regime = classify_regime(bars) if len(bars) >= 3 else MarketRegime.UNKNOWN

        analogs, memory_context = [], ""
        if self.memory:
            from tradingagents.pro.memory import describe_snapshot

            self.memory.record_regime(
                snapshot.symbol, regime,
                {name: m.value for name, m in quant.items()},
            )
            query = describe_snapshot(snapshot, regime)
            analogs = self.memory.historical_analogs(query, k=3, symbol=snapshot.symbol)
            blocks = []
            if analogs:
                blocks.append("Historical analogs (from memory, with outcomes):")
                blocks.extend(
                    f"- [{a.similarity:.2f} similar] {a.description} => {a.outcome}"
                    for a in analogs
                )
            lessons = self.memory.lessons(query, k=3, symbol=snapshot.symbol)
            if lessons:
                blocks.append("Lessons from prior decisions:")
                blocks.extend(f"- {hit.record.text}" for hit in lessons)
            relations = self.memory.relations_block(snapshot.symbol)
            if relations:
                blocks.append(relations)
            memory_context = "\n".join(blocks)

        return {
            "quant_metrics": quant,
            "risk_metrics": risk,
            "regime": regime,
            "debate": [],
            "technical_rounds": 0,
            "macro_rounds": 0,
            "historical_analogs": analogs,
            "memory_context": memory_context,
        }

    def make_team_node(self, team: AgentTeam):
        """One node per team; the graph runs the five in the same superstep,
        so LangGraph executes them concurrently. Each writes only its own
        key into the reduced ``evidence_by_team`` channel."""

        def node(state: dict) -> dict[str, Any]:
            snapshot = state["snapshot"]
            extras: dict[str, MetricReading] = {
                **state["quant_metrics"], **state["risk_metrics"]
            }
            agents = build_team(SPECS_BY_TEAM[team], self.llm)
            if self.agent_workers > 1:
                with ThreadPoolExecutor(max_workers=self.agent_workers) as pool:
                    results = list(pool.map(
                        lambda agent: agent.analyze(snapshot, extra_metrics=extras),
                        agents,
                    ))
                evidence = [e for e in results if e is not None]
            else:
                evidence = run_agents(agents, snapshot, extra_metrics=extras)
            return {"evidence_by_team": {team.value: evidence}}

        node.__name__ = f"team_{team.value}"
        return node

    def join(self, state: dict) -> dict[str, Any]:
        """Fan-in gate: no evidence from any team means nothing to debate."""
        if not any(state.get("evidence_by_team", {}).values()):
            return {"rejection": {
                "stage": "join",
                "reasons": ["no agent produced evidence; nothing to debate"],
            }}
        return {}

    # --- debate ----------------------------------------------------------------

    def _debate_turn(self, state: dict, team: AgentTeam, stance: str) -> dict:
        evidence = state["evidence_by_team"].get(team.value, [])
        prompt = self._prompts["debate"].format(
            stance=stance,
            team=team.value,
            symbol=state["snapshot"].symbol,
            asset=state["snapshot"].asset.value,
            evidence_block=_with_memory(_evidence_block(evidence), state),
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
        if self.memory:
            self.memory.record_reflection(
                state["snapshot"].symbol, note.weaknesses, note.invalidation
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
            evidence_block=_with_memory(_evidence_block(evidence), state),
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
                historical_analogs=state.get("historical_analogs", []),
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
        equity = state.get("equity") or self.equity
        sided = compute_risk_metrics(snapshot, self.config.risk, equity,
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
                historical_analogs=state.get("historical_analogs", []),
            )
        except (ValidationError, KeyError) as exc:
            return {"rejection": {
                "stage": "portfolio_manager",
                "reasons": [f"recommendation failed contract validation: {exc}"],
            }}
        return {"recommendation": recommendation}

    def human_approval(self, state: dict) -> dict:
        """Mandatory human gate for live mode (Constraint 5).

        Pauses the graph via LangGraph interrupt; resuming with
        ``Command(resume={"approved": bool, "approver": str, ...})`` decides
        the route. Paper/backtest pass through untouched.
        """
        if self.config.mode is not TradingMode.LIVE:
            return {}
        rec = state.get("recommendation")
        decision = interrupt({
            "question": "Approve live execution of this recommendation?",
            "recommendation": rec.model_dump(mode="json") if rec is not None else None,
        })
        approved = bool(decision.get("approved")) if isinstance(decision, dict) else False
        update: dict[str, Any] = {"human_approval": {
            "approved": approved,
            "approver": (decision or {}).get("approver", "unknown")
            if isinstance(decision, dict) else "unknown",
        }}
        if not approved:
            update["rejection"] = {
                "stage": "human_approval",
                "reasons": ["human approver declined live execution"],
            }
        return update

    def execution(self, state: dict) -> dict:
        recommendation = state.get("recommendation")
        if self.config.mode is TradingMode.LIVE:
            approval = state.get("human_approval") or {}
            if not approval.get("approved"):
                # unreachable via the graph (human_approval gates first),
                # but fail closed if this node is ever invoked directly
                return {"execution_status":
                        "refused: live execution without recorded human approval"}
            if self.memory and recommendation is not None:
                self.memory.record_trade(recommendation, regime=state["regime"])
            return {"execution_status":
                    "accepted:live (human-approved; broker routing arrives in Phase 9)"}
        if self.memory and recommendation is not None:
            self.memory.record_trade(recommendation, regime=state["regime"])
        return {"execution_status": f"accepted:{self.config.mode.value}"}

    def rejected(self, state: dict) -> dict:
        rejection = state.get("rejection") or {"stage": "unknown", "reasons": []}
        logger.info("pipeline rejected at %s: %s", rejection["stage"], rejection["reasons"])
        return {"recommendation": None,
                "execution_status": f"rejected:{rejection['stage']}"}
