import re
from typing import Any

_EXPECTED_RETURN_RE = re.compile(
    r"\b(?:expected|projected|target)\s+"
    r"(?:return|pnl|profit|upside|downside)\b\s*[:=]?\s*"
    r"([+-]?\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)


def _extract_labeled_float(text: str, label: str) -> float | None:
    pattern = re.compile(
        rf"\*?\*?{re.escape(label)}\*?\*?\s*:\s*\*?\*?\s*\$?\s*"
        r"([+-]?\d[\d,]*(?:\.\d+)?)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def extract_expected_return(final_decision: str, trader_plan: str = "") -> float | None:
    """Infer expected return from rendered decision/proposal markdown if present.

    Structured runs usually expose an entry price in the Trader proposal and a
    price target in the Portfolio Manager decision. Free-text runs may instead
    mention an explicit expected/projected return percentage. This stays
    best-effort: callers can omit the signal without changing reflection flow.
    """
    for text in (final_decision or "", trader_plan or ""):
        match = _EXPECTED_RETURN_RE.search(text)
        if match:
            return float(match.group(1)) / 100

    entry_price = (
        _extract_labeled_float(trader_plan or "", "Entry Price")
        or _extract_labeled_float(final_decision or "", "Entry Price")
    )
    target_price = (
        _extract_labeled_float(final_decision or "", "Price Target")
        or _extract_labeled_float(final_decision or "", "Target Price")
        or _extract_labeled_float(trader_plan or "", "Price Target")
        or _extract_labeled_float(trader_plan or "", "Target Price")
    )
    if entry_price is None or target_price is None or entry_price <= 0 or target_price <= 0:
        return None
    return (target_price - entry_price) / entry_price


def calculate_surprise_ratio(raw_return: float, expected_return: float) -> float:
    """Return outcome surprise using percentage-point units.

    Issue #718 defines the denominator as ``max(abs(expected_pnl), 1)``. Since
    this code stores returns as fractions, convert to percentage points first so
    the floor is one percentage point rather than 100%.
    """
    raw_pct = raw_return * 100
    expected_pct = expected_return * 100
    return abs(raw_pct - expected_pct) / max(abs(expected_pct), 1.0)


class Reflector:
    """Handles reflection on trading decisions."""

    def __init__(self, quick_thinking_llm: Any):
        """Initialize the reflector with an LLM."""
        self.quick_thinking_llm = quick_thinking_llm
        self.log_reflection_prompt = self._get_log_reflection_prompt()

    def _get_log_reflection_prompt(self) -> str:
        """Concise prompt for reflect_on_final_decision (Phase B log entries).

        Produces 2-4 sentences of plain prose — compact enough to be re-injected
        into future agent prompts without bloating the context window.
        """
        return (
            "You are a trading analyst reviewing your own past decision now that the outcome is known.\n"
            "Write exactly 2-4 sentences of plain prose (no bullets, no headers, no markdown).\n\n"
            "Cover in order:\n"
            "1. Was the directional call correct? (cite the alpha figure)\n"
            "2. Which part of the investment thesis held or failed?\n"
            "3. One concrete lesson to apply to the next similar analysis.\n\n"
            "If an expected return and surprise ratio are provided, use them to "
            "calibrate the lesson: a high surprise ratio means the outcome may "
            "reflect luck or regime noise, so do not over-credit direction alone.\n\n"
            "Be specific and terse. Your output will be stored verbatim in a decision log "
            "and re-read by future analysts, so every word must earn its place."
        )

    def reflect_on_final_decision(
        self,
        final_decision: str,
        raw_return: float,
        alpha_return: float,
        benchmark_name: str = "SPY",
        expected_return: float | None = None,
    ) -> str:
        """Single reflection call on the final trade decision with outcome context.

        Used by Phase B deferred reflection. The final_trade_decision already
        synthesises all analyst insights, so no separate market context is needed.
        ``benchmark_name`` is the label used for the alpha line (e.g. ``"SPY"``
        for US tickers, ``"^N225"`` for ``.T`` listings); defaults to SPY for
        callers that haven't been updated to thread the benchmark through.
        """
        outcome_lines = [
            f"Raw return: {raw_return:+.1%}",
            f"Alpha vs {benchmark_name}: {alpha_return:+.1%}",
        ]
        if expected_return is not None:
            surprise_ratio = calculate_surprise_ratio(raw_return, expected_return)
            outcome_lines.extend([
                f"Expected return at entry: {expected_return:+.1%}",
                f"Surprise ratio: {surprise_ratio:.2f}",
            ])
        messages = [
            ("system", self.log_reflection_prompt),
            (
                "human",
                "\n".join(outcome_lines) + f"\n\nFinal Decision:\n{final_decision}",
            ),
        ]
        return self.quick_thinking_llm.invoke(messages).content
