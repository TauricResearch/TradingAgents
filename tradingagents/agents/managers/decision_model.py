"""Deterministic scorer for the "structured" decision_mode (trading-workspace
TradingAgents#19).

Fixed, versioned, code-reviewed function -- NOT an LLM call. Takes the
FactorExtraction produced by factor_extractor.py and maps it to a
ResearchPlan the same way the Research Manager's debate synthesis would,
via an auditable formula instead of free-form argument. The LLM upstream can
adjust the *factors*; it never sees or can influence this function.

v0 is a simple weighted-average + fixed-threshold model, deliberately not
tuned yet -- there isn't enough decision_outcomes data to fit real weights
against (news-gap-ml's decision_outcomes table has 138 decisions / 72 scored
verdicts as of 2026-08-29). Treat every threshold below as a starting point
to be recalibrated once the retro-validation batch produces real outcomes,
not as a considered final design.
"""

from __future__ import annotations

from tradingagents.agents.schemas import PortfolioRating, ResearchPlan, render_research_plan

# The whole strategy this framework targets is a close-to-open gap trade --
# every retro transcript in this workspace's validation history converges on
# "no dated catalyst inside the decision window -> Hold" regardless of how
# strong the technical/sentiment case looks otherwise. Encode that as a hard
# gate rather than hoping the weighted score naturally lands on Hold.
_MAX_CATALYST_HOURS = 24.0

# Rating thresholds on the combined, confidence-weighted directional score
# (range roughly -1..+1). Asymmetric bands are not implied by anything other
# than matching the enum's 5 tiers evenly -- recalibrate once real outcomes
# exist.
_BUY_THRESHOLD = 0.5
_OVERWEIGHT_THRESHOLD = 0.2
_UNDERWEIGHT_THRESHOLD = -0.2
_SELL_THRESHOLD = -0.5

# Each risk flag shaves this fraction off the combined score's magnitude
# (pulls toward Hold) rather than gating outright -- a single flag shouldn't
# override a strong, catalyst-backed case, but several should.
_RISK_FLAG_DAMPING_PER_FLAG = 0.15

# TradingAgents#30 -- signed prior from the upstream signal's explicit
# direction (news-gap-ml's sector_direction, or a technical scanner's side).
# Added to the raw score before clamping: with otherwise neutral factors an
# "up" signal lands at +0.25 -> Overweight (never Underweight), while
# factors leaning the other way at >= 0.25 combined weight still cancel it
# back to Hold and stronger contrary evidence still flips it. So the prior
# breaks ties in the signal's favour and raises the bar for contradicting
# it; it does not override the reports. Tunable like every other constant
# here -- recalibrate against decision_outcomes once >= 50 post-change
# sector decisions exist (the issue's acceptance bar).
_EXTERNAL_SIGNAL_PRIOR_WEIGHT = 0.25
_EXTERNAL_SIGNAL_SIGN = {"up": 1.0, "down": -1.0}


def _combined_score(factors, external_direction: str | None = None) -> float:
    """Confidence-weighted sum of the technical and sentiment directions,
    clamped to [-1, 1].

    Deliberately a weighted SUM, not an average: an average normalizes by
    weight_sum, which means a single near-zero-confidence source still fully
    determines the score at its raw direction value (e.g. direction=0.9,
    confidence=0.01 would score 0.9 under an average -- confidence would only
    ever matter for weighting *between* two sources, never for suppressing a
    single low-confidence one). A weighted sum fixes that: low confidence
    genuinely damps toward zero regardless of how many sources are present,
    while a single fully-confident source can still reach full conviction
    (direction=1, confidence=1 -> 1.0) and two aligned confident sources can
    reinforce past what either alone would reach (clamped at the cap).

    ``external_direction`` ("up"/"down"/None) adds the signed
    _EXTERNAL_SIGNAL_PRIOR_WEIGHT prior before the clamp (TradingAgents#30)."""
    raw = (
        factors.technical_direction * factors.technical_confidence
        + factors.sentiment_direction * factors.sentiment_confidence
        + _EXTERNAL_SIGNAL_SIGN.get(external_direction or "", 0.0) * _EXTERNAL_SIGNAL_PRIOR_WEIGHT
    )
    return max(-1.0, min(1.0, raw))


def _rating_for_score(score: float) -> PortfolioRating:
    if score >= _BUY_THRESHOLD:
        return PortfolioRating.BUY
    if score >= _OVERWEIGHT_THRESHOLD:
        return PortfolioRating.OVERWEIGHT
    if score <= _SELL_THRESHOLD:
        return PortfolioRating.SELL
    if score <= _UNDERWEIGHT_THRESHOLD:
        return PortfolioRating.UNDERWEIGHT
    return PortfolioRating.HOLD


def compute_rating(factors, external_direction: str | None = None) -> tuple[PortfolioRating, float, str]:
    """Returns (rating, final_score, reason) -- the pure decision logic,
    separated from ResearchPlan rendering so it's directly unit-testable.

    ``external_direction`` ("up"/"down"/None, TradingAgents#30) is the
    upstream signal's explicit direction, applied as a signed prior to the
    combined score. It does NOT bypass the catalyst hard gates: a sector fire
    is itself a dated catalyst, and the Factor Extractor is shown the signal
    so it can record it as one -- the gate stays the extractor's honest call."""
    external_direction = external_direction if external_direction in _EXTERNAL_SIGNAL_SIGN else None
    if not factors.dated_catalyst_present:
        return (
            PortfolioRating.HOLD, 0.0,
            "No dated catalyst identified within this decision's holding window -- "
            "hard gate to Hold regardless of technical/sentiment scores.",
        )
    if (
        factors.catalyst_hours_to_resolution is not None
        and factors.catalyst_hours_to_resolution > _MAX_CATALYST_HOURS
    ):
        return (
            PortfolioRating.HOLD, 0.0,
            f"Catalyst identified but resolves in {factors.catalyst_hours_to_resolution:.1f}h, "
            f"beyond the {_MAX_CATALYST_HOURS:.0f}h window this close-to-open strategy targets -- "
            "hard gate to Hold.",
        )

    score = _combined_score(factors, external_direction)
    n_flags = len(factors.risk_flags)
    if n_flags:
        damping = max(0.0, 1.0 - _RISK_FLAG_DAMPING_PER_FLAG * n_flags)
        score *= damping

    rating = _rating_for_score(score)
    prior_note = ""
    if external_direction:
        signed = _EXTERNAL_SIGNAL_SIGN[external_direction] * _EXTERNAL_SIGNAL_PRIOR_WEIGHT
        prior_note = f", external signal {external_direction} prior {signed:+.2f}"
    reason = (
        f"Combined confidence-weighted score {score:+.2f} "
        f"(technical {factors.technical_direction:+.2f}@{factors.technical_confidence:.2f} conf, "
        f"sentiment {factors.sentiment_direction:+.2f}@{factors.sentiment_confidence:.2f} conf"
        + prior_note
        + (f", damped {n_flags} risk flag(s)" if n_flags else "")
        + f") -> {rating.value}."
    )
    return rating, score, reason


def score_factors(factors, company_name: str, external_direction: str | None = None) -> str:
    """Maps FactorExtraction -> a rendered ResearchPlan string, the same
    shape state["investment_plan"] already holds for the debate_enabled=True
    path, so Trader/Portfolio Manager consume it unchanged."""
    rating, score, reason = compute_rating(factors, external_direction)

    rationale_parts = [reason]
    if factors.dated_catalyst_present and factors.catalyst_hours_to_resolution is not None:
        rationale_parts.append(
            f"Catalyst expected to resolve in ~{factors.catalyst_hours_to_resolution:.1f}h."
        )
    if factors.risk_flags:
        rationale_parts.append(f"Risk flags: {', '.join(factors.risk_flags)}.")

    if rating == PortfolioRating.HOLD:
        strategic_actions = "No fresh position -- stand aside for this decision window."
    else:
        direction = "long" if score > 0 else "short"
        strategic_actions = (
            f"Open a {direction}-biased options position in {company_name} sized to the "
            f"{rating.value} conviction level (score {score:+.2f}); size down if any risk "
            f"flags are present. Standard close-to-open exit discipline applies."
        )

    plan = ResearchPlan(
        recommendation=rating,
        rationale=" ".join(rationale_parts),
        strategic_actions=strategic_actions,
    )
    return render_research_plan(plan)
