"""Jev judgments that end the debates once they converge.

Fit 3 in docs/jev-use-cases.md. The bull/bear and risk debates run a fixed
number of rounds, and every turn sends a debater's prompt, with every analyst
report in it, to the LLM. After each turn that could end a debate, Jev is asked
whether the turn raised anything the debate had not already heard; the router
(``ConditionalLogic``) stops at the end of a round in which no turn did. When
the investment debate ends, Jev is asked whose case is better supported, and
the Research Manager gets the answer as a hint, not a verdict.

Jev only answers the two questions. Which turns are asked, the threshold, the
minimum number of rounds, and the lead the hint needs before it names a side
are ``DebatePolicy``, so a change to any of them is
an edit here rather than a reworded question. The answers are kept in the debate
state, one per turn, so the policy can be tuned without asking again.

Both entry points return None when Jev is off or a request fails, and the
debate then runs its configured rounds as before. A long debate is cut to its
latest turns before it is sent, since Jev rejects a request past its input limit.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache

from tradingagents.agents.jev import MAX_STATE_CHARS, jev_client

logger = logging.getLogger(__name__)

# The sides the investment debate can favour, in the order the hint lists them.
SIDES = ("bull", "bear", "even")
SIDE_LABELS = {"bull": "bull", "bear": "bear", "even": "evenly matched"}

# Every debater starts its turn on a new line with its label ("Bull Analyst: ...").
_TURN_START = re.compile(r"\n(?=(?:Bull|Bear|Aggressive|Conservative|Neutral) Analyst: )")
OMITTED = "[Earlier turns omitted for length.]"


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DebatePolicy:
    """Every number the convergence rule and the Research Manager's hint read.

    Starting points, not values tuned for this domain: tune them on backtest
    outcomes (``tradingagents/backtest.py``). A debate never runs past its
    configured rounds (``max_debate_rounds`` / ``max_risk_discuss_rounds``).
    """

    # Rounds always held. Round 1 is every side's opening, so it always adds
    # arguments; the earliest a debate can converge is after round 2.
    min_rounds: int = 2
    # A turn whose P(new argument) is below this adds nothing new. Stopping is
    # the costly mistake (the manager loses an argument), so the bar is low.
    new_argument_min: float = 0.30
    # The Research Manager's hint names a side only when Jev gives it at least
    # this probability; below it, the hint says there was no clear winner.
    side_lead_min: float = 0.50

    def __post_init__(self):
        if self.min_rounds < 2:
            raise ValueError(
                f"min_rounds must be at least 2 (round 1 is the openings), got {self.min_rounds}"
            )


DEFAULT_POLICY = DebatePolicy()


def worth_judging(turn: int, speakers: int, max_rounds: int, policy: DebatePolicy = DEFAULT_POLICY) -> bool:
    """Whether turn ``turn`` (1-based) is in a round the debate could end after.

    Turns in the rounds before ``min_rounds`` and in the last configured round
    are never asked about, since their answer could not change when it ends.
    """
    round_ = (turn - 1) // speakers + 1
    return policy.min_rounds <= round_ < max_rounds


def converged(debate_state: Mapping, speakers: int, policy: DebatePolicy = DEFAULT_POLICY) -> bool:
    """Whether the round just finished added nothing new.

    True only at the end of a round, from ``min_rounds`` on, when every turn in
    that round was judged and each scored below ``new_argument_min``. A turn
    left unjudged (Jev off or failing) keeps the debate going.
    """
    count = debate_state.get("count", 0)
    if count == 0 or count % speakers or count // speakers < policy.min_rounds:
        return False
    scores = list(debate_state.get("new_argument") or [])[count - speakers:count]
    return len(scores) == speakers and all(
        s is not None and s < policy.new_argument_min for s in scores
    )


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


@cache
def _questions() -> dict[str, dict]:
    # Imported here, not at module level, so the router and the Research
    # Manager load without the ``jev`` extra; this runs only once a client exists.
    from typesafe_sdk import Choice, Noul, NoulCriteria

    return {
        "turn": {"new_argument": Noul(
            instructions=(
                "Does `latest_turn` raise a substantive argument or piece of evidence "
                "that does not already appear in `prior_turns`?"
            ),
            criteria=NoulCriteria(
                true="It makes a point no earlier turn made: a new fact, figure, event, "
                     "risk, or line of reasoning, or a rebuttal that brings evidence not "
                     "cited before.",
                false="Everything it argues already appears in `prior_turns`: it "
                      "restates, rephrases, or summarises earlier points, repeats "
                      "evidence already cited, or adds only emphasis or rhetoric.",
            ),
        )},
        "sides": {"stronger_side": Choice(
            instructions=(
                "Based on `bull_case` and `bear_case`, whose case is better supported "
                "by evidence?"
            ),
            criteria={
                "bull": "The bull case rests on more specific evidence (figures, reported "
                        "results, concrete events) and answers the bear's main points, "
                        "while the bear case leans more on speculation or leaves the "
                        "bull's points unanswered.",
                "bear": "The bear case rests on more specific evidence (figures, reported "
                        "results, concrete events) and answers the bull's main points, "
                        "while the bull case leans more on speculation or leaves the "
                        "bear's points unanswered.",
                "even": "Both cases are about equally well supported, or each is strong "
                        "on different points and neither clearly outweighs the other.",
            },
        )},
    }


# ---------------------------------------------------------------------------
# Judging
# ---------------------------------------------------------------------------


def latest_turns(text: str, budget: int) -> str:
    """The end of ``text`` that fits in ``budget`` characters, starting at a turn.

    Returns ``text`` unchanged when it fits. Otherwise the oldest turns go, and
    the result opens with ``OMITTED``; a single turn longer than the budget is
    cut from its start.
    """
    text = text.strip()
    if len(text) <= budget:
        return text
    keep = max(budget - len(OMITTED) - 1, 0)
    # One character more than is kept, so a turn that starts right at the cut stays.
    tail = text[len(text) - keep - 1:]
    start = _TURN_START.search(tail)
    return f"{OMITTED}\n{tail[start.end() if start else 1:]}".strip()


def new_argument(prior_turns: str, latest_turn: str) -> float | None:
    """P(``latest_turn`` raises something not in ``prior_turns``), or None.

    None means Jev is off or the request failed; the caller keeps debating.
    A long debate is judged against its latest turns only. A point last made
    in a dropped turn then reads as new, which keeps the debate going.
    """
    client = jev_client()
    if client is None:
        return None
    prior_turns = latest_turns(prior_turns, MAX_STATE_CHARS - len(latest_turn))
    try:
        with client:
            response = client.system_one(
                state={"prior_turns": prior_turns, "latest_turn": latest_turn},
                questions=_questions()["turn"],
            )
        return response.answers["new_argument"].noul
    except Exception as exc:  # noqa: BLE001 — hold the configured rounds instead
        logger.warning("Debate convergence check failed (%s); holding the configured rounds", exc)
        return None


def stronger_side(bull_case: str, bear_case: str) -> dict[str, float] | None:
    """Jev's probability for each of ``SIDES``, or None.

    None when either case is empty, Jev is off, or the request failed; the
    Research Manager then works without a hint. In a long debate each side is
    judged on its latest turns, half the state budget each.
    """
    if not (bull_case.strip() and bear_case.strip()):
        return None
    client = jev_client()
    if client is None:
        return None
    try:
        with client:
            response = client.system_one(
                state={
                    "bull_case": latest_turns(bull_case, MAX_STATE_CHARS // 2),
                    "bear_case": latest_turns(bear_case, MAX_STATE_CHARS // 2),
                },
                questions=_questions()["sides"],
            )
        answer = response.answers["stronger_side"]
        return {side: float(answer.probabilities.get(side, 0.0)) for side in SIDES}
    except Exception as exc:  # noqa: BLE001 — the manager decides without a hint
        logger.warning("Debate side check failed (%s); the Research Manager gets no hint", exc)
        return None


def render_side_hint(probabilities: Mapping[str, float], policy: DebatePolicy = DEFAULT_POLICY) -> str:
    """The Research Manager's prompt block for a ``stronger_side`` answer."""
    top = max(SIDES, key=lambda side: probabilities.get(side, 0.0))
    if top == "even":
        verdict = "judged the two cases evenly matched"
    elif probabilities.get(top, 0.0) < policy.side_lead_min:
        verdict = "found no clear winner"
    else:
        verdict = f"judged the {top} case better supported"
    spread = " · ".join(f"{SIDE_LABELS[s]} {probabilities.get(s, 0.0):.0%}" for s in SIDES)
    return (
        "**Independent evidence check (a hint, not a verdict):** a separate classifier "
        f"that read only the debate {verdict} ({spread}). It did not see the analyst "
        "reports. Reach your own view from the arguments; do not adopt this reading "
        "without checking it against them."
    )
