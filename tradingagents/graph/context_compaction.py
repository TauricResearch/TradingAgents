"""Safe, bounded context compaction for multi-turn debates.

The compactor treats debate text as user-visible working context, never as a
store for a model's private chain of thought.  Its output can therefore be
included in an audit/replay record while keeping the prompt within a known
bound.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from langchain_core.messages import AIMessage, RemoveMessage, ToolMessage

from .runtime_events import record_runtime_event

_SPEAKER = re.compile(
    r"(?=^(?:Bull Analyst|Bear Analyst|Aggressive Analyst|Conservative Analyst|Neutral Analyst):)",
    re.MULTILINE,
)


@dataclass(frozen=True)
class CompactionResult:
    history: str
    compacted: bool
    preserved_turns: int
    flushed_facts: tuple[str, ...]
    method: str


def compact_debate_history(
    history: str,
    *,
    max_characters: int = 12_000,
    recent_turns: int = 3,
    summarize: Callable[[str], str] | None = None,
) -> CompactionResult:
    """Keep recent debate turns and replace older public context with a summary.

    ``summarize`` may call an LLM, but callers must supply a prompt that asks
    for externally checkable facts/caveats only.  If that call fails or is not
    enabled, a deterministic extract is used instead.  The latter deliberately
    avoids generating conclusions that were not present in the debate.
    """
    if max_characters < 512:
        raise ValueError("max_characters must be at least 512")
    if recent_turns < 1:
        raise ValueError("recent_turns must be at least one")
    if len(history) <= max_characters:
        return CompactionResult(history, False, 0, (), "none")

    turns = _split_turns(history)
    if len(turns) <= recent_turns:
        # There are no old rounds that can be safely replaced.  Hard trim the
        # retained text from the left and make that behavior auditable.
        clipped = history[-max_characters:]
        return CompactionResult(clipped, True, len(turns), (), "bounded_tail")

    old_turns = turns[:-recent_turns]
    recent = turns[-recent_turns:]
    old_text = "\n".join(old_turns).strip()
    facts = _extract_public_facts(old_turns)
    summary = ""
    method = "deterministic_extract"
    if summarize is not None:
        try:
            candidate = summarize(old_text).strip()
        except Exception:
            candidate = ""
        if candidate:
            summary = candidate
            method = "llm_public_summary"
    if not summary:
        summary = _render_deterministic_summary(facts, old_text)
    compacted = "[Earlier debate context (public summary)]\n" + summary
    compacted += "\n[Recent debate turns]\n" + "\n".join(recent)
    if len(compacted) > max_characters:
        # Recent turns are the invariant; trim the summary before touching
        # them.  When the newest three alone exceed the bound, retain their
        # tail rather than silently dropping the most recent response.
        budget = max_characters - len("[Earlier debate context (public summary)]\n\n[Recent debate turns]\n") - len("\n".join(recent))
        if budget > 64:
            compacted = (
                "[Earlier debate context (public summary)]\n"
                + summary[:budget].rstrip()
                + "\n[Recent debate turns]\n"
                + "\n".join(recent)
            )
        else:
            compacted = ("[Recent debate turns]\n" + "\n".join(recent))[-max_characters:]
    return CompactionResult(compacted, True, len(recent), tuple(facts), method)


def is_context_overflow_error(error: BaseException) -> bool:
    """Recognise common provider context-window failures without vendor imports."""
    text = str(error).casefold()
    return any(
        marker in text
        for marker in (
            "context length",
            "context window",
            "maximum context",
            "max context",
            "too many tokens",
            "token limit exceeded",
        )
    )


def compact_state_for_context_retry(
    state: dict | object,
    *,
    state_key: str,
    summarize: Callable[[str], str] | None,
) -> tuple[dict, CompactionResult] | None:
    """Return a bounded state copy for one genuine context-overflow retry.

    The original checkpoint/state remains untouched until the retried node
    succeeds.  Only public facts from compacted-away debate turns can be
    returned in the successful delta.
    """
    if not isinstance(state, dict):
        return None
    debate = state.get(state_key)
    if not isinstance(debate, dict) or not isinstance(debate.get("history"), str):
        return None
    compacted = compact_debate_history(debate["history"], summarize=summarize)
    if not compacted.compacted:
        return None
    retry_state = dict(state)
    retry_debate = dict(debate)
    retry_debate["history"] = compacted.history
    retry_state[state_key] = retry_debate
    record_runtime_event(
        "microcompact",
        "context_overflow_retry_compacted",
        metadata={
            "preserved_turn_count": compacted.preserved_turns,
            "public_fact_count": len(compacted.flushed_facts),
        },
    )
    return retry_state, compacted


def microcompact_tool_messages(
    state: dict | object,
    delta: dict | object,
    *,
    maximum_messages: int,
) -> dict | object:
    """Trim only old tool results after a real ToolNode execution.

    The incoming batch is never removed.  Older results are represented by
    ``RemoveMessage`` operations so LangGraph applies the trim through its
    normal messages reducer rather than mutating prior checkpoint state.

    ToolMessages are removed together with the AIMessage that issued their
    tool_calls.  Removing a ToolMessage without its AIMessage leaves an
    assistant message whose tool_calls have no matching tool responses,
    which OpenAI-compatible providers (DeepSeek, OpenAI) reject with a 400.
    When a turn straddles the retention cut, the entire turn is removed so
    the pairing stays intact.
    """
    if maximum_messages < 1:
        raise ValueError("max_tool_messages_in_context must be at least one")
    if not isinstance(state, dict) or not isinstance(delta, dict):
        return delta
    existing_messages = state.get("messages")
    incoming_messages = delta.get("messages")
    if not isinstance(existing_messages, (list, tuple)) or not isinstance(
        incoming_messages, (list, tuple)
    ):
        return delta
    existing_tools = [message for message in existing_messages if isinstance(message, ToolMessage)]
    incoming_tools = [message for message in incoming_messages if isinstance(message, ToolMessage)]
    if not incoming_tools:
        return delta
    retained_old_count = max(0, maximum_messages - len(incoming_tools))
    cut = len(existing_tools) - retained_old_count
    if cut <= 0:
        return delta
    removed_tools = existing_tools[:cut]
    removed_tool_call_ids = {
        getattr(message, "tool_call_id", None) for message in removed_tools
    }
    removed_tool_call_ids.discard(None)
    if not removed_tool_call_ids:
        return delta

    removed_ai_ids: set[str] = set()
    for message in existing_messages:
        if not isinstance(message, AIMessage) or not getattr(message, "tool_calls", None):
            continue
        msg_tool_call_ids = {
            tc.get("id") for tc in message.tool_calls if tc.get("id")
        }
        if msg_tool_call_ids & removed_tool_call_ids:
            removed_ai_ids.add(message.id)
            removed_tool_call_ids |= msg_tool_call_ids

    all_removed_tools = [
        message
        for message in existing_tools
        if getattr(message, "tool_call_id", None) in removed_tool_call_ids
    ]
    removals = [RemoveMessage(id=message.id) for message in all_removed_tools if message.id]
    removals.extend(RemoveMessage(id=ai_id) for ai_id in removed_ai_ids if ai_id)
    if not removals:
        return delta
    updated = dict(delta)
    updated["messages"] = [*removals, *incoming_messages]
    record_runtime_event(
        "microcompact",
        "old_tool_messages_trimmed",
        metadata={
            "removed_tool_message_count": len(all_removed_tools),
            "retained_tool_message_count": len(existing_tools) - len(all_removed_tools) + len(incoming_tools),
            "incoming_tool_message_count": len(incoming_tools),
            "removed_ai_message_count": len(removed_ai_ids),
        },
    )
    return updated


def _split_turns(history: str) -> list[str]:
    turns = [part.strip() for part in _SPEAKER.split(history) if part.strip()]
    return turns or [history.strip()]


def _extract_public_facts(turns: list[str]) -> list[str]:
    """Extract short, attributable sentences without inferring new facts."""
    facts: list[str] = []
    for turn in turns:
        speaker, _, body = turn.partition(":")
        for sentence in re.split(r"(?<=[。.!?])\s+", body.strip()):
            normalized = " ".join(sentence.split())
            if len(normalized) >= 24:
                facts.append(f"{speaker}: {normalized[:280]}")
                break
    return facts[:12]


def _render_deterministic_summary(facts: list[str], old_text: str) -> str:
    if facts:
        return "\n".join(f"- {fact}" for fact in facts)
    excerpt = " ".join(old_text.split())[:800]
    return f"- Earlier public debate excerpt: {excerpt}" if excerpt else "- No prior public debate text."
