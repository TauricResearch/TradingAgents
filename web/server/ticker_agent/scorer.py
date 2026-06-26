"""Accuracy scoring engine for the ticker accuracy agent.

Computes right/wrong verdicts for each ticker from completed runs.
Reuses the same verdict logic as the existing frontend verdicts.ts.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TickerScore:
    ticker: str
    total_runs: int
    right: int
    wrong: int
    unknown: int
    win_rate: float | None
    avg_confidence: float | None
    target_hit_rate: float | None
    trending_accuracy: float | None
    last_evaluated: str | None
    sector: str | None = None


def _classify_run_outcome(run: dict) -> str | None:
    """Classify a single run as 'right', 'wrong', or 'unknown'.

    Simplified verdict logic matching verdicts.ts:
    - BUY: right if end_price > start_price
    - SELL: right if end_price < start_price
    - HOLD: always 'unknown' without a threshold check
    - Unknown action or missing prices: 'unknown'
    """
    action = run.get("decision_action")
    start_price = run.get("start_price")
    end_price = run.get("end_price")
    if not action or start_price is None or end_price is None:
        return None
    verdict_map = {
        "BUY": "right" if end_price > start_price else "wrong",
        "SELL": "right" if end_price < start_price else "wrong",
        "HOLD": "unknown",
    }
    return verdict_map.get(action)


def compute_ticker_scores(
    runs_by_ticker: dict[str, list[dict]],
    min_samples: int = 3,
) -> dict[str, TickerScore]:
    """Compute accuracy scores for all tickers with enough data.

    Args:
        runs_by_ticker: Dict mapping ticker to list of run dicts.
        min_samples: Minimum number of runs required to score.

    Returns:
        Dict mapping ticker to TickerScore, sorted by win_rate desc.
    """
    scores: dict[str, TickerScore] = {}
    for ticker, runs in runs_by_ticker.items():
        score = compute_score_for_ticker(ticker, runs)
        if score is not None and score.total_runs >= min_samples:
            scores[ticker] = score

    sorted_scores = dict(
        sorted(scores.items(), key=lambda x: (x[1].win_rate or -1, x[1].total_runs), reverse=True)
    )
    return sorted_scores


def compute_score_for_ticker(ticker: str, runs: list[dict]) -> TickerScore | None:
    """Compute accuracy score for a single ticker. Returns None if no completed runs."""
    completed = [r for r in runs if r.get("status") == "done"]
    if not completed:
        return None

    right = 0
    wrong = 0
    unknown = 0
    total_confidence = 0.0
    confidence_count = 0
    target_hits = 0
    target_total = 0

    for run in completed:
        outcome = _classify_run_outcome(run)
        if outcome == "right":
            right += 1
        elif outcome == "wrong":
            wrong += 1
        else:
            unknown += 1

        confidence = run.get("decision_confidence")
        if confidence is not None:
            try:
                total_confidence += float(confidence)
                confidence_count += 1
            except (ValueError, TypeError):
                pass

        target = run.get("decision_target")
        if target is not None and outcome in ("right", "wrong"):
            target_total += 1
            if outcome == "right":
                target_hits += 1

    total_scored = right + wrong
    win_rate = right / total_scored if total_scored > 0 else None
    avg_confidence = total_confidence / confidence_count if confidence_count > 0 else None
    target_hit_rate = target_hits / target_total if target_total > 0 else None

    # Trending: win rate of last 10 runs vs all-time
    recent = completed[:10]
    recent_right = 0
    recent_total = 0
    for run in recent:
        o = _classify_run_outcome(run)
        if o == "right":
            recent_right += 1
            recent_total += 1
        elif o == "wrong":
            recent_total += 1
    trending = recent_right / recent_total if recent_total > 0 else None

    return TickerScore(
        ticker=ticker,
        total_runs=len(completed),
        right=right,
        wrong=wrong,
        unknown=unknown,
        win_rate=win_rate,
        avg_confidence=avg_confidence,
        target_hit_rate=target_hit_rate,
        trending_accuracy=trending,
        last_evaluated=completed[-1].get("started_at") if completed else None,
    )
