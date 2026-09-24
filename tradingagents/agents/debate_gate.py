"""Optional early stop for the bull/bear debate, judged by TypeSafe's Jev.

The debate runs a fixed number of rounds. With ``jev_debate_gate: true`` and
``TYPESAFE_API_KEY`` set, after each complete round (bull and bear have both
spoken) Jev answers one typed question about the transcript so far: is the
case already decision-ready for the Research Manager? A confident yes ends
the debate early, saving a round of two LLM calls. Anything else — no key, an
API failure, low confidence — leaves the fixed-round flow untouched, exactly
as ``post_screen`` degrades for the Sentiment Analyst.
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from tradingagents.agents.post_screen import TypeSafeError, system_one

logger = logging.getLogger(__name__)

# One noul: Jev must be at least this confident the case is decision-ready.
_CONVERGED_ABOVE = 0.65
# Keep the transcript the judge sees inside the noul-state budget.
_MAX_CHARS_PER_SIDE = 4000

_QUESTIONS = {
    "decision_ready": {
        "type": "noul",
        "instructions": (
            "After this many rounds of debate, is the case between the bull "
            "and bear arguments already decision-ready for a research manager: "
            "each side's core claim, the evidence behind it, and the other "
            "side's rebuttal are all on the table?"
        ),
        "criteria": {
            "true": "Both positions and their key rebuttals are stated; another round would repeat or refine wording, not add substance.",
            "false": "A core claim or its rebuttal is still missing, vague, or unaddressed, or the sides are talking past each other.",
        },
    }
}


def jev_debate_gate() -> Optional[Callable[[dict], Optional[bool]]]:
    """A gate for :class:`ConditionalLogic`, or None without a TypeSafe key.

    The gate takes the investment-debate state dict and returns True (end the
    debate now) or None (keep the default flow). It never returns False, so
    the fixed round cap stays the only thing that can force the debate on.
    """
    if not os.environ.get("TYPESAFE_API_KEY"):
        return None

    def gate(debate_state: dict) -> bool | None:
        bull = str(debate_state.get("bull_history") or "")[-_MAX_CHARS_PER_SIDE:]
        bear = str(debate_state.get("bear_history") or "")[-_MAX_CHARS_PER_SIDE:]
        rounds = int(debate_state.get("count", 0)) // 2
        try:
            answers = system_one(
                {"rounds_completed": rounds, "bull_argument": bull,
                 "bear_argument": bear},
                _QUESTIONS,
            )
            ready = answers["decision_ready"]["noul"]
        except (TypeSafeError, KeyError, TypeError) as exc:
            logger.warning("Jev debate gate unavailable (%s); debate continues", exc)
            return None
        return ready >= _CONVERGED_ABOVE

    return gate
