from typing import Any


class Reflector:
    """Handles reflection on trading decisions."""

    def __init__(self, quick_thinking_llm: Any):
        """Initialize the reflector with an LLM."""
        self.quick_thinking_llm = quick_thinking_llm

    def _system_prompt(self, holding_days: int) -> str:
        """Concise prompt for reflect_on_final_decision (Phase B log entries).

        Produces 2-4 sentences of plain prose, compact enough to be re-injected
        into future agent prompts without bloating the context window. The
        window is named because it bounds what the outcome can show: a thesis
        written for months is not disproved by a week, and a lesson that ignores
        the difference is read by later runs as an established failure.
        """
        return (
            "You are a trading analyst reviewing your own past decision now that the outcome is known.\n"
            f"The outcome covers {holding_days} trading days after the analysis date, "
            "which may be shorter than the horizon the decision was written for.\n"
            "Write exactly 2-4 sentences of plain prose (no bullets, no headers, no markdown).\n\n"
            "Cover in order:\n"
            f"1. What the {holding_days}-day alpha shows about the directional call (cite the figure), "
            "and say so plainly if the window is too short to judge the thesis.\n"
            "2. Which part of the investment thesis this window supports or undercuts.\n"
            "3. One concrete lesson to apply to the next similar analysis.\n\n"
            "Be specific and terse. Your output will be stored verbatim in a decision log "
            "and re-read by future analysts, so every word must earn its place."
        )

    def reflect_on_final_decision(
        self,
        final_decision: str,
        raw_return: float,
        alpha_return: float,
        benchmark_name: str = "SPY",
        holding_days: int = 5,
    ) -> str:
        """Single reflection call on the final trade decision with outcome context.

        Used by Phase B deferred reflection. The final_trade_decision already
        synthesises all analyst insights, so no separate market context is needed.
        ``benchmark_name`` is the label used for the alpha line (e.g. ``"SPY"``
        for US tickers, ``"^N225"`` for ``.T`` listings); defaults to SPY for
        callers that haven't been updated to thread the benchmark through.
        """
        messages = [
            ("system", self._system_prompt(holding_days)),
            (
                "human",
                (
                    f"Raw return over {holding_days} trading days: {raw_return:+.1%}\n"
                    f"Alpha vs {benchmark_name}: {alpha_return:+.1%}\n\n"
                    f"Final Decision:\n{final_decision}"
                ),
            ),
        ]
        return self.quick_thinking_llm.invoke(messages).content
