"""Bounded-context compaction for the bull/bear debate history (RE.md R1).

``investment_debate_state["history"]`` grows by one full argument per speaker
per round, and every researcher turn re-injects the whole thing into its prompt.
With ``max_debate_rounds`` set high (the deep tier uses 5), that text dominates
the prompt: token cost scales with the square of the rounds, and early arguments
get buried under later ones (attention dilution).

This module turns the raw history into a *bounded* context before it reaches a
prompt, without touching the stored ``history`` (downstream state stays intact):

- ``none``     — return the history unchanged (legacy behaviour, backwards-compatible).
- ``truncate`` — keep each side's opening stance plus its most recent turns, hard
                 cap the result at ``history_max_chars`` (zero LLM cost, the default).
- ``summarize``— truncate as above, then head/tail-elide the middle with a marker,
                 a cheap deterministic "summary" that needs no extra LLM call.

Every mode reports a ``token_estimate`` (chars / 4) so a run can quantify the
saving before/after compaction. The functions are pure: no LLM, no network, no
global state, so they are unit-testable on their own (``tests/test_context_budget.py``).
"""

from __future__ import annotations

from dataclasses import dataclass

# Speaker labels the researchers prefix each argument with (see bull/bear node).
BULL_PREFIX = "Bull Analyst:"
BEAR_PREFIX = "Bear Analyst:"

COMPRESS_MODES = ("none", "truncate", "summarize")

_DEFAULT_MAX_CHARS = 6000
_DEFAULT_MAX_TURNS = 4
_CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class BoundedHistory:
    """A compacted view of the debate history plus its cost metrics."""

    text: str
    token_estimate: int
    original_chars: int
    compacted_chars: int
    mode: str

    @property
    def saved_chars(self) -> int:
        return max(0, self.original_chars - self.compacted_chars)

    @property
    def saved_ratio(self) -> float:
        if self.original_chars <= 0:
            return 0.0
        return self.saved_chars / self.original_chars


def estimate_tokens(text: str) -> int:
    """Rough token count for ``text`` (chars / 4), the RE.md estimator."""
    if not text:
        return 0
    return (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN


def _split_arguments(history: str) -> list[str]:
    """Split a concatenated history into one argument per non-empty line block.

    The researchers append each argument as ``"\\n" + "Bull Analyst: ..."`` /
    ``"\\n" + "Bear Analyst: ..."``, so splitting on the speaker labels (keeping
    the label with its block) recovers the individual turns.
    """
    if not history or not history.strip():
        return []
    normalized = history.replace(BULL_PREFIX, f"\n{BULL_PREFIX}").replace(
        BEAR_PREFIX, f"\n{BEAR_PREFIX}"
    )
    return [chunk.strip() for chunk in normalized.split("\n") if chunk.strip()]


def _speaker(arg: str) -> str | None:
    if arg.startswith(BULL_PREFIX):
        return "bull"
    if arg.startswith(BEAR_PREFIX):
        return "bear"
    return None


def _keep_recent_per_side(arguments: list[str], max_turns: int) -> list[str]:
    """Keep each side's opening stance plus its most recent ``max_turns`` arguments.

    Retaining the opening argument preserves the "首" (first) core stance while
    the recent turns keep the live exchange; anything in between is dropped. A
    ``max_turns`` of 0 or less keeps no recent turns (opening only).
    """
    per_side: dict[str, list[tuple[int, str]]] = {"bull": [], "bear": []}
    unlabelled: list[tuple[int, str]] = []
    for index, arg in enumerate(arguments):
        speaker = _speaker(arg)
        if speaker is None:
            unlabelled.append((index, arg))
        else:
            per_side[speaker].append((index, arg))

    keep_indices: set[int] = set()
    for turns in per_side.values():
        if not turns:
            continue
        keep_indices.add(turns[0][0])  # opening stance
        if max_turns > 0:
            keep_indices.update(index for index, _ in turns[-max_turns:])
    # Unlabelled fragments (defensive: unexpected history format) follow the
    # same recent-window rule so nothing is silently lost in ``none``/legacy.
    if unlabelled and max_turns > 0:
        keep_indices.update(index for index, _ in unlabelled[-max_turns:])

    return [arg for index, arg in enumerate(arguments) if index in keep_indices]


def _head_tail_elide(text: str, max_chars: int) -> str:
    """Hard-cap ``text`` at ``max_chars``, eliding the middle with a marker."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    marker = "\n[... earlier debate elided ...]\n"
    room = max_chars - len(marker)
    if room <= 0:
        return text[:max_chars]
    head = room // 2
    tail = room - head
    return text[:head] + marker + text[-tail:]


def build_bounded_history(
    history: str,
    *,
    mode: str = "truncate",
    max_chars: int = _DEFAULT_MAX_CHARS,
    max_turns: int = _DEFAULT_MAX_TURNS,
) -> BoundedHistory:
    """Return the bounded context for ``history`` under the given policy.

    ``mode="none"`` returns the text unchanged (legacy); the metrics are still
    populated so callers can report a zero-saving baseline.
    """
    if mode not in COMPRESS_MODES:
        raise ValueError(
            f"history_compress must be one of {COMPRESS_MODES}, got {mode!r}"
        )
    history = history or ""
    original_chars = len(history)

    if mode == "none" or original_chars == 0:
        compacted = history
    else:
        arguments = _split_arguments(history)
        kept = _keep_recent_per_side(arguments, max_turns)
        compacted = "\n".join(kept)
        # ``summarize`` additionally elides an over-long middle after selection;
        # ``truncate`` applies the same hard character cap (zero LLM cost).
        compacted = _head_tail_elide(compacted, max_chars)

    return BoundedHistory(
        text=compacted,
        token_estimate=estimate_tokens(compacted),
        original_chars=original_chars,
        compacted_chars=len(compacted),
        mode=mode,
    )


def compact_from_config(history: str, config: dict | None = None) -> BoundedHistory:
    """Convenience wrapper reading the R1 keys off a run config dict.

    Honours ``debate_history_compact`` (master switch, default True) and the
    ``history_max_chars`` / ``history_max_turns`` / ``history_compress`` keys.
    When the master switch is off the history passes through unchanged.
    """
    config = config or {}
    if not config.get("debate_history_compact", True):
        return build_bounded_history(history, mode="none")
    return build_bounded_history(
        history,
        mode=config.get("history_compress", "truncate"),
        max_chars=config.get("history_max_chars", _DEFAULT_MAX_CHARS),
        max_turns=config.get("history_max_turns", _DEFAULT_MAX_TURNS),
    )
