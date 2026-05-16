"""SignalFusion node — aggregates per-analyst signals into a composite score.

This commit (1/2) lands the *scaffolding*: the node exists, runs after
the four analyst extractors have fanned in, and writes ``signal_weights``,
``composite_score`` and ``disagreement_axes`` to the graph state under
equal weights. The next commit replaces the equal-weights placeholder
with a real ``WeightEstimator`` (rolling-Lasso option, parquet cache,
lookahead guard) and rewires the Bull/Bear prompts to consume the
composite score, the weights table, the disagreement axes, and
compressed reports for low-weight analysts.

The split is intentional: this commit aims to be **behavior-neutral**
under equal weights. The Bull/Bear prompts still receive the same four
full reports they always did — the new state fields are populated but
not yet read by the researchers. That makes the topology change easy
to review in isolation before any weighting logic touches the prompt
contract.

Design notes
------------

- ``create_signal_fusion_node`` returns a plain function that LangGraph
  calls once after fan-in. It is *not* an LLM agent — pure Python aggregation.
- Disagreement detection picks the two analyst channels with the largest
  signed-score gap. This is the channel pair the Bull/Bear debate will
  be told to anchor on once commit 2 lands. Returns up to two channels;
  empty list when fewer than two analysts produced a signal.
- Missing channels (e.g. an analyst the user did not select, or whose
  extraction reached the heuristic fallback) are tolerated: the composite
  averages over whatever channels are actually present. SignalFusion
  never KeyErrors on a missing channel.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Tuple

from tradingagents.agents.schemas import AnalystSignal


_ANALYST_DISPLAY_NAME = {
    "market": "market",
    "social": "sentiment",
    "news": "news",
    "fundamentals": "fundamentals",
}


def equal_weights(channels: List[str]) -> Dict[str, float]:
    """Return a uniform weight distribution over the supplied channels.

    Empty input is tolerated and returns an empty dict — the fusion node
    upstream of this falls back to a zero composite in that case rather
    than raising.
    """
    if not channels:
        return {}
    w = 1.0 / len(channels)
    return {c: w for c in channels}


def compute_composite_score(
    signals: Dict[str, AnalystSignal],
    weights: Dict[str, float],
) -> float:
    """``Σ w_i × score_i × confidence_i`` over present channels.

    The confidence multiplier means a low-confidence analyst contributes
    proportionally less even if its weight is high. Empty inputs return
    0.0 — no edge to call.
    """
    if not signals:
        return 0.0
    total = 0.0
    for channel, signal in signals.items():
        if channel not in weights:
            continue
        total += weights[channel] * signal.score * signal.confidence
    return total


def detect_disagreement(signals: Dict[str, AnalystSignal]) -> List[str]:
    """Return the channel pair with the widest signed-score gap.

    Output format: one or two strings like
    ``"fundamentals (+0.71) vs sentiment (-0.42)"``. The Bull/Bear
    prompt uses these strings verbatim in commit 2 to anchor the debate
    on the actual divergence rather than rehashing every report.

    Behaviour:

    - 0 or 1 channels → empty list (nothing to disagree about).
    - 2+ channels → up to one disagreement string covering the widest
      gap. We keep this to one string for now; multi-gap reporting can
      come later if backtest evidence supports it.
    """
    if len(signals) < 2:
        return []

    scored: List[Tuple[str, float]] = [
        (channel, signal.score) for channel, signal in signals.items()
    ]
    # Largest signed gap = (max score channel) vs (min score channel).
    scored.sort(key=lambda kv: kv[1])
    lo_channel, lo_score = scored[0]
    hi_channel, hi_score = scored[-1]

    if hi_score - lo_score < 1e-6:
        return []

    return [
        f"{_ANALYST_DISPLAY_NAME.get(hi_channel, hi_channel)} ({hi_score:+.2f}) "
        f"vs {_ANALYST_DISPLAY_NAME.get(lo_channel, lo_channel)} ({lo_score:+.2f})"
    ]


def create_signal_fusion_node(
    *,
    weight_fn: Callable[[List[str]], Dict[str, float]] | None = None,
    weight_estimator=None,
    ticker_provider=lambda state: state.get("company_of_interest", ""),
    date_provider=lambda state: state.get("trade_date", ""),
):
    """Build the fan-in node that writes composite signal fields to state.

    Two ways to supply the weighting policy:

    - ``weight_fn`` — a pure function ``channels -> {channel: weight}``.
      Used by the equal-weights default and by unit tests.
    - ``weight_estimator`` — an object implementing the ``WeightEstimator``
      protocol from :mod:`tradingagents.dataflows.signal_weights`. The
      fusion node passes the ticker, the trade date, and the list of
      available channels so the estimator can read its parquet/CSV
      cache and apply the lookahead guard.

    ``weight_estimator`` wins when both are supplied.
    """
    weight_fn = weight_fn or equal_weights

    def signal_fusion_node(state) -> dict:
        signals: Dict[str, AnalystSignal] = state.get("analyst_signals") or {}
        channels = list(signals.keys())

        if weight_estimator is not None and channels:
            weights = weight_estimator.get_weights(
                ticker=ticker_provider(state),
                as_of_date=date_provider(state),
                available_channels=channels,
            )
        else:
            weights = weight_fn(channels)
        composite = compute_composite_score(signals, weights)
        disagreement = detect_disagreement(signals)

        return {
            "signal_weights": weights,
            "composite_score": composite,
            "disagreement_axes": disagreement,
        }

    return signal_fusion_node
