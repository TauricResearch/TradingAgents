"""Reflection: a settled decision's outcome turned into a short lesson for later runs."""

from typing import Any


class Reflector:
    """Handles reflection on trading decisions."""

    def __init__(self, quick_thinking_llm: Any):
        """Initialize the reflector with an LLM."""
        self.quick_thinking_llm = quick_thinking_llm

    def _system_prompt(self, holding_days: int) -> str:
        """Concise prompt for reflect_on_final_decision (settled memory log entries).

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
            "Be specific and terse. Your output will be stored verbatim in a memory log "
            "and re-read by future analysts, so every word must earn its place."
        )

    def reflect_on_final_decision(
        self,
        final_decision: str,
        raw_return: float | None = None,
        alpha_return: float | None = None,
        benchmark_name: str = "SPY",
        holding_days: int = 5,
        settled: dict[int, dict] | None = None,
        configured: list[int] | None = None,
    ) -> str:
        """Reflection call on the final trade decision with outcome context.

        Multi-horizon when ``settled`` (a mapping of horizon-days ->
        ``{"raw", "alpha"}``) is given: the lesson covers every measured window
        and is refreshed as longer windows close, so it tracks the multi-horizon
        outcome instead of a single anchor figure — this is what replaces the
        old 5d-only lesson. Falls back to the single-window (anchor) framing
        when only ``raw_return``/``alpha_return`` are given (legacy callers).
        ``configured`` is the full list of evaluation windows (trading days) for
        context. ``benchmark_name`` labels the alpha line (e.g. ``"SPY"``,
        ``"^N225"``); the final decision already synthesises the analyst insights,
        so no separate market context is needed.
        """
        if settled:
            return self._reflect_multi_horizon(
                final_decision, settled, configured or [], benchmark_name,
            )
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

    def _reflect_multi_horizon(
        self,
        final_decision: str,
        settled: dict[int, dict],
        configured: list[int],
        benchmark_name: str = "SPY",
    ) -> str:
        """Multi-horizon lesson over every window measured so far."""
        lines = []
        for h in sorted(settled):
            v = settled[h] or {}
            raw = v.get("raw")
            alpha = v.get("alpha")
            raw_s = f"{raw:+.1%}" if isinstance(raw, (int, float)) else "n/a"
            alpha_s = f"{alpha:+.1%}" if isinstance(alpha, (int, float)) else "n/a"
            lines.append(f"  - {h} trading days: {raw_s} total / {alpha_s} vs {benchmark_name}")
        open_windows = [h for h in sorted(configured) if h not in settled]
        open_note = (
            f"\nLonger windows still open (not yet measured): "
            f"{', '.join(str(h) for h in open_windows)} trading days."
            if open_windows else ""
        )
        all_windows = (
            ", ".join(str(h) for h in sorted(configured)) if configured
            else ", ".join(str(h) for h in sorted(settled))
        )
        system = (
            "You are a trading analyst reviewing your own past decision across its "
            "evaluation windows, now that some of them have traded.\n"
            "Write exactly 2-4 sentences of plain prose (no bullets, no headers, no markdown).\n\n"
            "Cover in order:\n"
            "1. How the directional call played out over the measured windows (cite the alpha "
            "figures), and which windows confirm or undercut the thesis.\n"
            "2. What the multi-window pattern (short vs long horizons) suggests.\n"
            "3. One concrete lesson to apply to the next similar decision at these horizons.\n\n"
            "Be specific and terse. Your output is stored verbatim in a memory log and "
            "re-read by future analysts, so every word must earn its place."
        )
        human = (
            f"Evaluation windows (trading days): {all_windows}\n"
            f"Outcomes measured so far:\n" + "\n".join(lines) + open_note + "\n\n"
            f"Final Decision:\n{final_decision}"
        )
        return self.quick_thinking_llm.invoke([("system", system), ("human", human)]).content
