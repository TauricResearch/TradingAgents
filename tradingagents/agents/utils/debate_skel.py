"""Shared argument rules and rendering for bull/bear debate."""

from __future__ import annotations

import json
from typing import Literal

from tradingagents.agents.schemas import DebateTurn
from tradingagents.agents.structured import NO_EXTERNAL_TOOLS


def build_debate_instructions(
    side: Literal["bull", "bear"],
    *,
    is_final_turn: bool,
) -> str:
    """Build shared SCAMPER instructions for one debate turn."""
    if side not in ("bull", "bear"):
        raise ValueError("side must be 'bull' or 'bear'")

    opponent = "bear" if side == "bull" else "bull"

    reverse_rule = (
        "This is your final turn. reverse_check must explain the strongest "
        "attack an opponent could make against your own reasoning."
        if is_final_turn
        else
        "You may use reverse_check to identify weaknesses in your reasoning. "
        "Use an empty string if no reverse check is provided this turn."
    )

    return f"""
You are the {side} analyst. Return a DebateTurn matching the supplied schema.

Apply these argument rules:

1. Substitute:
   In each key_claims entry, use the sequence:
   Evidence -> Reasoning -> Direct response to the {opponent} analyst.
   If the opponent has not spoken, state an opening thesis instead of
   inventing an opponent argument.

2. Combine:
   Ground your claims in at least one available analyst report:
   market, fundamentals, news, or sentiment.
   Put source labels and supporting figures in evidence_refs.
   Quote numeric evidence when available. Never invent figures, sources,
   or missing reports. State evidence gaps explicitly.

3. Eliminate:
   In refuted_points, list your OWN earlier claims that are no longer
   defensible after considering the opponent's evidence.
   Explain why each claim is withdrawn.
   Use an empty list on the opening turn or when no withdrawal is justified.
   Do not list the opponent's claims here.
   Avoid repeating previous claims without new evidence or reasoning.

4. Modify:
   Give stance_score between -1 and 1:
   -1 = strongly bearish, 0 = neutral, +1 = strongly bullish.
   Revise your score when the evidence warrants it, regardless of your role.

5. Reverse:
   {reverse_rule}

{NO_EXTERNAL_TOOLS}
""".strip()

def render_debate_turn(
    turn: DebateTurn,
    *,
    is_final_turn: bool,
) -> str:
    """Validate and serialize a debate turn for the existing history."""
    turn = DebateTurn.model_validate(turn)

    if is_final_turn and not turn.reverse_check.strip():
        raise ValueError("Final debate turn requires a non-empty reverse_check")

    return turn.model_dump_json(indent=2)

def invoke_debate_turn(llm, structured_llm, prompt: str) -> DebateTurn:
    """Obtain a validated turn using native structure or JSON output."""
    if structured_llm is not None:
        return DebateTurn.model_validate(structured_llm.invoke(prompt))

    json_prompt = (
        prompt
        + "\n\nReturn only a JSON object matching this schema. "
        "Do not include Markdown fences.\n"
        + json.dumps(DebateTurn.model_json_schema(), ensure_ascii=False)
    )
    response = llm.invoke(json_prompt)
    return DebateTurn.model_validate_json(response.content)
