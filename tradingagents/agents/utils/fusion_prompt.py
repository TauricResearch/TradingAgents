"""Helpers that render SignalFusion state into a Bull/Bear prompt block.

The Bull and Bear researchers used to interpolate the four analyst
reports verbatim into their prompts. Once SignalFusion has populated
``composite_score`` / ``signal_weights`` / ``disagreement_axes``, the
researchers also need:

1. A short numeric header so they know the weighted directional read
   before reading any report.
2. A weights table so they understand which channel the desk is leaning
   on (and which is being discounted).
3. An explicit disagreement anchor so the debate focuses on the actual
   divergence rather than rehashing each report.
4. Compressed versions of low-weight reports — the weights are
   physically load-bearing in context, not just a number the LLM is
   free to ignore.

This module is the single source of truth for that rendering. Both
``bull_researcher`` and ``bear_researcher`` call into it so the two
sides see the exact same fused context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from tradingagents.agents.schemas import (
    AnalystSignal,
    render_analyst_signal_summary,
)


# Display names that read more naturally in a prompt than the internal
# selector keys ("social" → "sentiment" etc.).
_CHANNEL_DISPLAY = {
    "market": "Market",
    "social": "Sentiment",
    "news": "News",
    "fundamentals": "Fundamentals",
}


def _composite_label(score: float) -> str:
    """Verbal description for a composite score on [-1, 1]."""
    if score >= 0.6:
        return "strongly bullish"
    if score >= 0.2:
        return "moderately bullish"
    if score <= -0.6:
        return "strongly bearish"
    if score <= -0.2:
        return "moderately bearish"
    return "near-neutral"


def _summarise_to_sentences(text: str, max_sentences: int) -> str:
    """Crude sentence-truncation for the no-key-evidence path.

    The compressed-summary path normally relies on the analyst's
    ``key_evidence`` field. When that's empty (e.g. heuristic fallback
    fired), we fall back to clipping the first ``max_sentences`` of the
    markdown. Good enough; the user knows the channel is downweighted.
    """
    if not text:
        return ""
    sentences = []
    buf = ""
    for ch in text.strip():
        buf += ch
        if ch in ".!?\n" and buf.strip():
            sentences.append(buf.strip())
            buf = ""
            if len(sentences) >= max_sentences:
                break
    if buf.strip() and len(sentences) < max_sentences:
        sentences.append(buf.strip())
    return " ".join(sentences)


@dataclass
class FusionPromptConfig:
    compress_threshold: float = 0.10
    compress_to_sentences: int = 3


@dataclass
class FusionPromptParts:
    """The pieces a researcher prompt needs from SignalFusion state."""

    fusion_preamble: str
    market_block: str
    sentiment_block: str
    news_block: str
    fundamentals_block: str


def render_fusion_prompt_parts(
    *,
    market_report: str,
    sentiment_report: str,
    news_report: str,
    fundamentals_report: str,
    analyst_signals: Dict[str, AnalystSignal],
    signal_weights: Dict[str, float],
    composite_score: float,
    disagreement_axes: List[str],
    config: Optional[FusionPromptConfig] = None,
) -> FusionPromptParts:
    """Compose the fusion preamble and four (possibly compressed) report blocks.

    ``composite_score=0`` together with empty ``signal_weights`` is
    treated as "fusion not active": the preamble degrades to an empty
    string and the four reports are returned verbatim. The Bull/Bear
    prompts can interpolate the parts unchanged in both the fusion-on
    and fusion-off graph topologies.
    """
    cfg = config or FusionPromptConfig()
    fusion_active = bool(signal_weights)

    fusion_preamble = _build_preamble(
        composite_score=composite_score,
        signal_weights=signal_weights,
        disagreement_axes=disagreement_axes,
    ) if fusion_active else ""

    def _block(channel: str, full_report: str) -> str:
        if not fusion_active:
            return full_report
        weight = signal_weights.get(channel, 0.0)
        if weight >= cfg.compress_threshold:
            return full_report
        signal = analyst_signals.get(channel)
        if signal is not None and signal.key_evidence:
            return render_analyst_signal_summary(signal)
        # No key evidence to render — clip the markdown instead.
        return (
            f"[Downweighted to {weight:.0%}. Compressed digest below.]\n"
            f"{_summarise_to_sentences(full_report, cfg.compress_to_sentences)}"
        )

    return FusionPromptParts(
        fusion_preamble=fusion_preamble,
        market_block=_block("market", market_report),
        sentiment_block=_block("social", sentiment_report),
        news_block=_block("news", news_report),
        fundamentals_block=_block("fundamentals", fundamentals_report),
    )


def _build_preamble(
    *,
    composite_score: float,
    signal_weights: Dict[str, float],
    disagreement_axes: List[str],
) -> str:
    label = _composite_label(composite_score)
    lines = [
        f"**Fused signal:** {composite_score:+.2f} ({label}, weighted by analyst confidence).",
        "",
        "**Per-analyst weights** (driven by historical predictive value of each channel for this ticker):",
        "",
        "| Analyst | Weight |",
        "|---|---|",
    ]
    for channel in ("market", "social", "news", "fundamentals"):
        if channel not in signal_weights:
            continue
        display = _CHANNEL_DISPLAY.get(channel, channel)
        lines.append(f"| {display} | {signal_weights[channel]:.0%} |")
    if disagreement_axes:
        lines.extend([
            "",
            "**Key analyst disagreement to anchor your debate on:** "
            + "; ".join(disagreement_axes),
            "",
            "Focus your argument on resolving this specific divergence rather than "
            "rehashing every report end-to-end. The composite score above is the "
            "starting point — argue for or against it on the merits of the "
            "specific channel pair in disagreement.",
        ])
    return "\n".join(lines)
