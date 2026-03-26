"""Candidate prioritization for the Portfolio Manager.

Scores and ranks scanner-generated stock candidates based on conviction,
thesis quality, sector diversification, and whether the ticker is already held.

All scoring logic is pure Python (no external dependencies).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tradingagents.portfolio.risk_evaluator import sector_concentration

if TYPE_CHECKING:
    from tradingagents.portfolio.models import Holding, Portfolio
    from tradingagents.agents.utils.memory import FinancialSituationMemory


# ---------------------------------------------------------------------------
# Scoring tables
# ---------------------------------------------------------------------------

_CONVICTION_WEIGHTS: dict[str, float] = {
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
}

_THESIS_SCORES: dict[str, float] = {
    "growth": 3.0,
    "momentum": 2.5,
    "catalyst": 2.5,
    "value": 2.0,
    "turnaround": 1.5,
    "defensive": 1.0,
}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_candidate(
    candidate: dict[str, Any],
    holdings: list["Holding"],
    portfolio_total_value: float,
    config: dict[str, Any],
) -> float:
    """Compute a composite priority score for a single candidate.

    Formula::

        score = conviction_weight * thesis_score * diversification_factor * held_penalty

    Args:
        candidate: Dict with at least ``conviction`` and ``thesis_angle`` keys.
        holdings: Current holdings list.
        portfolio_total_value: Total portfolio value (used for sector %
            calculation).
        config: Portfolio config dict (max_sector_pct).

    Returns:
        Non-negative composite score.  Returns 0.0 when sector is at max
        exposure limit.
    """
    conviction = (candidate.get("conviction") or "").lower()
    thesis = (candidate.get("thesis_angle") or "").lower()
    sector = candidate.get("sector") or ""
    ticker = (candidate.get("ticker") or "").upper()

    conviction_weight = _CONVICTION_WEIGHTS.get(conviction, 1.0)
    thesis_score = _THESIS_SCORES.get(thesis, 1.0)

    # Diversification factor based on sector exposure.
    # Tiered: 0.0× (sector full), 0.5× (70–100% of limit), 1.0× (under 70%), 2.0× (new sector).
    max_sector_pct: float = config.get("max_sector_pct", 0.35)
    concentration = sector_concentration(holdings, portfolio_total_value)
    current_sector_pct = concentration.get(sector, 0.0)

    if current_sector_pct >= max_sector_pct:
        diversification_factor = 0.0  # sector at or above limit — skip
    elif current_sector_pct >= 0.70 * max_sector_pct:
        diversification_factor = 0.5  # near limit — reduced bonus
    elif current_sector_pct > 0.0:
        diversification_factor = 1.0  # existing sector with room
    else:
        diversification_factor = 2.0  # new sector — diversification bonus

    # Held penalty: already-owned tickers score half (exposure already taken).
    held_tickers = {h.ticker for h in holdings}
    held_penalty = 0.5 if ticker in held_tickers else 1.0

    return conviction_weight * thesis_score * diversification_factor * held_penalty


def _build_candidate_description(candidate: dict) -> str:
    """Concatenate ticker, sector, thesis_angle, rationale, conviction for BM25 query."""
    parts = [candidate.get(k, "") for k in
             ("ticker", "sector", "thesis_angle", "rationale", "conviction")]
    return " ".join(p for p in parts if p)


def prioritize_candidates(
    candidates: list[dict[str, Any]],
    portfolio: "Portfolio",
    holdings: list["Holding"],
    config: dict[str, Any],
    top_n: int | None = None,
    selection_memory: "FinancialSituationMemory | None" = None,
) -> list[dict[str, Any]]:
    """Score and rank candidates by priority_score descending.

    Each returned candidate dict is enriched with a ``priority_score`` field.
    Candidates that score 0.0 also receive a ``skip_reason`` field.

    Args:
        candidates: List of candidate dicts from the macro scanner.
        portfolio: Current Portfolio instance.
        holdings: Current holdings list.
        config: Portfolio config dict.
        top_n: If given, return only the top *n* candidates.

    Returns:
        Sorted list of enriched candidate dicts (highest priority first).
    """
    if not candidates:
        return []

    total_value = portfolio.total_value or (
        portfolio.cash + sum(
            h.current_value if h.current_value is not None else h.shares * h.avg_cost
            for h in holdings
        )
    )

    enriched: list[dict[str, Any]] = []
    for candidate in candidates:
        ps = score_candidate(candidate, holdings, total_value, config)
        item = dict(candidate)
        item["priority_score"] = ps
        if ps == 0.0:
            sector = candidate.get("sector") or "Unknown"
            item["skip_reason"] = (
                f"Sector '{sector}' is at or above max exposure limit "
                f"({config.get('max_sector_pct', 0.35):.0%})"
            )

        # Memory rejection gate
        if selection_memory is not None and ps > 0.0:
            desc = _build_candidate_description(candidate)
            matches = selection_memory.get_memories(desc, n_matches=1)
            if matches and matches[0]["similarity_score"] > 0.5:
                ps = 0.0
                item["priority_score"] = 0.0
                item["skip_reason"] = (
                    f"Memory lesson (score={matches[0]['similarity_score']:.2f}): "
                    f"{matches[0]['recommendation'][:120]}"
                )

        enriched.append(item)

    enriched.sort(key=lambda c: c["priority_score"], reverse=True)

    if top_n is not None:
        enriched = enriched[:top_n]

    return enriched
