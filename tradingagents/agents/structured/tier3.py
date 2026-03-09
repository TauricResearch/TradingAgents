"""Tier 3 agents: Bull/Bear debate, Risk assessment, Final decision.

Only runs on stocks that pass Tier 1 + Tier 2. Uses the deep-thinking LLM
for reasoning-heavy tasks (debate, risk, final synthesis).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from tradingagents.models import (
    BearCaseOutput,
    BullCaseOutput,
    DataFlag,
    DebateRefereeOutput,
    FinalDecisionOutput,
    RiskInvalidationOutput,
    invoke_structured,
)

logger = logging.getLogger(__name__)


def _summarize_tier2(state: Dict[str, Any]) -> str:
    """Build a compact summary of all Tier 1+2 findings for Tier 3 prompts."""
    card = state.get("company_card") or {}
    macro = state.get("macro") or {}
    liq = state.get("liquidity") or {}
    bq = state.get("business_quality") or {}
    inst = state.get("institutional_flow") or {}
    val = state.get("valuation") or {}
    et = state.get("entry_timing") or {}
    er = state.get("earnings_revisions") or {}
    sr = state.get("sector_rotation") or {}
    bl = state.get("backlog") or {}
    cr = state.get("crowding") or {}
    arch = state.get("archetype") or {}

    lines = [
        f"Company: {card.get('company_name', '?')} ({card.get('ticker', '?')})",
        f"Sector: {card.get('sector', '?')} | Industry: {card.get('industry', '?')}",
        f"Market Cap: {card.get('market_cap_formatted', 'N/A')}",
        f"Price: ${card.get('current_price', 'N/A')}",
        f"Archetype: {arch.get('archetype', 'N/A')}",
        "",
        f"Master Score: {state.get('master_score', 'N/A')} | Role: {state.get('position_role', 'N/A')}",
        "",
        "AGENT SCORES (0-10):",
        f"  Business Quality:    {bq.get('score_0_to_10', 'N/A')} — {bq.get('summary_1_sentence', '')}",
        f"  Macro Alignment:     {macro.get('macro_alignment_0_to_10', 'N/A')} — {macro.get('summary_1_sentence', '')}",
        f"  Institutional Flow:  {inst.get('score_0_to_10', 'N/A')} — {inst.get('summary_1_sentence', '')}",
        f"  Valuation:           {val.get('score_0_to_10', 'N/A')} — {val.get('summary_1_sentence', '')}",
        f"  Entry Timing:        {et.get('score_0_to_10', 'N/A')} — {et.get('summary_1_sentence', '')}",
        f"  Earnings Revisions:  {er.get('score_0_to_10', 'N/A')} — {er.get('summary_1_sentence', '')}",
        f"  Sector Rotation:     {sr.get('score_0_to_10', 'N/A')} — {sr.get('summary_1_sentence', '')}",
        f"  Backlog:             {bl.get('score_0_to_10', 'N/A')} — {bl.get('summary_1_sentence', '')}",
        f"  Crowding:            {cr.get('score_0_to_10', 'N/A')} — {cr.get('summary_1_sentence', '')}",
        f"  Liquidity:           {liq.get('score_0_to_10', 'N/A')} — {liq.get('summary_1_sentence', '')}",
        "",
        f"  Macro Regime: {macro.get('regime_label', '?')} | VIX: {macro.get('vix_level', '?')}",
        f"  Risk Appetite: {macro.get('risk_appetite', '?')} | Liquidity Regime: {macro.get('liquidity_regime', '?')}",
        f"  Regime Score Adjustment: {macro.get('regime_score_adjustment', 0):+.1f}",
        f"  Moat: {bq.get('competitive_moat', '?')} | Valuation: {val.get('valuation_verdict', '?')}",
        f"  Smart Money: {inst.get('smart_money_signal', '?')} | Accumulation: {inst.get('accumulation_signal', '?')}",
        f"  Short Trend: {inst.get('short_interest_trend', '?')} | Insider Signal: {inst.get('insider_transaction_signal', '?')}",
        f"  Timing: {et.get('timing_verdict', '?')}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Bull Case
# ---------------------------------------------------------------------------

def create_bull_case_node(llm):

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]
        summary = _summarize_tier2(state)

        prompt = f"""You are a Bull Case Researcher. Build the strongest possible bullish thesis for {ticker}.

{summary}

INSTRUCTIONS:
1. Write a concise thesis (2-3 sentences) for why this stock should be bought.
2. List 3-5 specific catalysts that could drive the stock higher.
3. Estimate upside_target (price) and upside_pct from current price.
4. List key assumptions your thesis depends on.
5. List thesis_invalidation_triggers — what would kill the bull case.
6. Set confidence 0-1 for how strong the bull case is.

Attack the investment aggressively. Find every reason to be bullish.
But be honest — don't fabricate catalysts. Use the data above."""

        try:
            result = invoke_structured(llm, BullCaseOutput, prompt)
        except Exception as e:
            logger.warning("BullCase LLM failed: %s", e)
            result = BullCaseOutput(
                thesis="Bull case analysis unavailable",
                confidence_0_to_1=0.1,
            )

        return {"bull_case": result.model_dump()}

    return node


# ---------------------------------------------------------------------------
# Bear Case
# ---------------------------------------------------------------------------

def create_bear_case_node(llm):

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]
        summary = _summarize_tier2(state)

        prompt = f"""You are a Bear Case Researcher. Build the strongest possible bearish thesis for {ticker}.

{summary}

INSTRUCTIONS:
1. Write a concise thesis (2-3 sentences) for why this stock should be avoided or sold.
2. List 3-5 specific risks that could drive the stock lower.
3. Estimate downside_target (price) and downside_pct from current price.
4. List key assumptions your bear thesis depends on.
5. List thesis_invalidation_triggers — what would kill the bear case.
6. Set confidence 0-1 for how strong the bear case is.

Be ruthless. Find every vulnerability, every overvaluation, every risk.
But be honest — don't fabricate risks. Use the data above."""

        try:
            result = invoke_structured(llm, BearCaseOutput, prompt)
        except Exception as e:
            logger.warning("BearCase LLM failed: %s", e)
            result = BearCaseOutput(
                thesis="Bear case analysis unavailable",
                confidence_0_to_1=0.1,
            )

        return {"bear_case": result.model_dump()}

    return node


# ---------------------------------------------------------------------------
# Debate Referee
# ---------------------------------------------------------------------------

def create_debate_node(llm):
    """Referee that evaluates bull vs bear case."""

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]
        bull = state.get("bull_case") or {}
        bear = state.get("bear_case") or {}

        prompt = f"""You are the Debate Referee. Evaluate the bull vs bear case for {ticker}.

BULL CASE (confidence: {bull.get('confidence_0_to_1', 'N/A')}):
Thesis: {bull.get('thesis', 'N/A')}
Catalysts: {', '.join(bull.get('catalysts', []))}
Upside: {bull.get('upside_pct', 'N/A')}%
Invalidation: {', '.join(bull.get('thesis_invalidation_triggers', []))}

BEAR CASE (confidence: {bear.get('confidence_0_to_1', 'N/A')}):
Thesis: {bear.get('thesis', 'N/A')}
Risks: {', '.join(bear.get('risks', []))}
Downside: {bear.get('downside_pct', 'N/A')}%
Invalidation: {', '.join(bear.get('thesis_invalidation_triggers', []))}

MASTER SCORE: {state.get('master_score', 'N/A')} | ROLE: {state.get('position_role', 'N/A')}

INSTRUCTIONS:
1. Declare winner: "bull" or "bear".
2. Score each side 0-10 on argument strength.
3. List key unresolved questions.
4. Set net_conviction_adjustment (-2 to +2) to modify the master score.
   Positive = debate strengthened the bull case. Negative = weakened it.
5. Provide reasoning for your decision."""

        try:
            result = invoke_structured(llm, DebateRefereeOutput, prompt)
        except Exception as e:
            logger.warning("Debate LLM failed: %s", e)
            result = DebateRefereeOutput()

        return {"debate": result.model_dump()}

    return node


# ---------------------------------------------------------------------------
# Risk / Invalidation
# ---------------------------------------------------------------------------

def create_risk_node(llm):

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]
        summary = _summarize_tier2(state)
        bull = state.get("bull_case") or {}
        bear = state.get("bear_case") or {}
        debate = state.get("debate") or {}

        prompt = f"""You are the Risk / Invalidation Analyst. Final risk gate for {ticker}.

{summary}

DEBATE OUTCOME: {debate.get('winner', '?')} won
  Bull strength: {debate.get('bull_strength_0_to_10', '?')}/10
  Bear strength: {debate.get('bear_strength_0_to_10', '?')}/10
  Conviction adjustment: {debate.get('net_conviction_adjustment', 0)}

Bear risks: {', '.join(bear.get('risks', []))}
Bull invalidation triggers: {', '.join(bull.get('thesis_invalidation_triggers', []))}

INSTRUCTIONS:
1. Classify overall_risk_level: low / medium / high.
2. Set max_position_size_pct (0-100). Low risk = up to 10%. High risk = max 2%.
3. Suggest stop_loss_pct (distance from entry to stop).
4. List invalidation_triggers — concrete events that should trigger exit.
5. Score overall risk-reward 0-10 (10 = great risk/reward).
6. Set veto=true ONLY if you find impossible/fraudulent data, or risk is so extreme
   that no position should be taken. This is a hard kill switch.
7. Be concise."""

        try:
            result = invoke_structured(llm, RiskInvalidationOutput, prompt)
        except Exception as e:
            logger.warning("Risk LLM failed: %s", e)
            result = RiskInvalidationOutput(
                score_0_to_10=5.0, confidence_0_to_1=0.3,
                summary_1_sentence="Risk analysis unavailable",
            )

        flags = [f.model_dump() for f in result.data_quality_flags]
        update: Dict[str, Any] = {"risk": result.model_dump(), "global_flags": flags}

        if result.veto:
            update["hard_veto"] = True
            update["hard_veto_reason"] = result.veto_reason

        return update

    return node


# ---------------------------------------------------------------------------
# Final Decision (prose generated AFTER all scoring)
# ---------------------------------------------------------------------------

def create_final_decision_node(llm):

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]
        card = state.get("company_card") or {}
        summary = _summarize_tier2(state)

        bull = state.get("bull_case") or {}
        bear = state.get("bear_case") or {}
        debate = state.get("debate") or {}
        risk = state.get("risk") or {}
        theme = state.get("theme_substitution") or {}
        replacement = state.get("position_replacement") or {}

        master_score = state.get("master_score", 0)
        adjusted_score = state.get("adjusted_score", 0)
        position_role = state.get("position_role", "Avoid")
        conviction_adj = debate.get("net_conviction_adjustment", 0)

        # Apply debate conviction adjustment
        final_score = round(adjusted_score + conviction_adj, 2)
        final_role = _role_from_score(final_score)

        # Determine action
        if state.get("hard_veto"):
            action = "AVOID"
            final_role = "Avoid"
            final_score = 0.0
        elif final_score >= 70:
            action = "BUY"
        elif final_score >= 50:
            action = "HOLD"
        else:
            action = "AVOID"

        # Theme/replacement context
        theme_lines = ""
        if theme.get("theme_name"):
            theme_lines = (
                f"\nTHEME CONTEXT:"
                f"\n  Theme: {theme.get('theme_name', '?')}"
                f"\n  Best expression: {'Yes' if theme.get('best_expression_of_theme') else 'No'}"
                f"\n  Stronger alternatives: {', '.join(theme.get('stronger_alternatives', [])) or 'None'}"
                f"\n  Score gap vs best: {theme.get('relative_score_gap', 0):.1f}"
            )
        if replacement.get("should_replace"):
            theme_lines += (
                f"\n  REPLACEMENT FLAG: Consider {replacement.get('replace_with', '?')} instead"
                f"\n  Reason: {replacement.get('replacement_reason', '')}"
            )

        prompt = f"""You are the Final Decision Synthesizer for {ticker}.

{summary}

DEBATE: {debate.get('winner', '?')} won | Conviction adjustment: {conviction_adj:+.1f}
RISK: {risk.get('overall_risk_level', '?')} | Max position: {risk.get('max_position_size_pct', '?')}%
{theme_lines}

FINAL SCORES:
  Master Score: {master_score}
  Adjusted Score: {adjusted_score} (after data quality penalties)
  Post-Debate Score: {final_score} (after conviction adjustment)
  Position Role: {final_role}
  Action: {action}

INSTRUCTIONS:
Write a concise narrative (3-5 sentences) that:
1. Summarizes the investment thesis.
2. Highlights the top 2-3 catalysts and top 2-3 risks.
3. States the action ({action}) and position role ({final_role}).
4. Notes what would change the thesis (invalidation triggers).
5. If theme analysis found stronger alternatives, mention them and whether
   this stock is still the best expression of the theme.

Also provide:
- thesis_summary (one sentence)
- key_catalysts (top 3 from bull case)
- key_risks (top 3 from bear case)
- invalidation_triggers (from risk agent)
- position_sizing_pct (from risk agent)
- confidence (average of all agent confidences)"""

        try:
            result = invoke_structured(llm, FinalDecisionOutput, prompt)
        except Exception as e:
            logger.warning("FinalDecision LLM failed: %s", e)
            result = FinalDecisionOutput()

        # Override with computed values (deterministic, not LLM-driven)
        result.ticker = ticker
        result.company_name = card.get("company_name", "")
        result.master_score = master_score
        result.adjusted_score = final_score
        result.position_role = final_role
        result.action = action
        result.risk_level = risk.get("overall_risk_level", "medium")
        result.position_sizing_pct = risk.get("max_position_size_pct", 0)

        # Compute aggregate confidence
        agents_with_confidence = [
            state.get(k, {}).get("confidence_0_to_1")
            for k in (
                "macro", "liquidity", "business_quality", "institutional_flow",
                "valuation", "entry_timing", "earnings_revisions",
                "sector_rotation", "backlog", "crowding",
            )
        ]
        valid_confs = [c for c in agents_with_confidence if c is not None]
        result.confidence = round(sum(valid_confs) / len(valid_confs), 2) if valid_confs else 0.5

        return {"final_decision": result.model_dump()}

    return node


def _role_from_score(score: float) -> str:
    if score > 80:
        return "Core Position"
    if score > 70:
        return "Strong Position"
    if score > 60:
        return "Tactical / Satellite"
    if score > 50:
        return "Watchlist"
    return "Avoid"
