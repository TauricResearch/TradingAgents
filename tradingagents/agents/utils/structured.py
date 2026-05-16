"""Shared helpers for invoking an agent with structured output and a graceful fallback.

The Portfolio Manager, Trader, and Research Manager all follow the same
canonical pattern:

1. At agent creation, wrap the LLM with ``with_structured_output(Schema)``
   so the model returns a typed Pydantic instance. If the provider does
   not support structured output (rare; mostly older Ollama models), the
   wrap is skipped and the agent uses free-text generation instead.
2. At invocation, run the structured call and render the result back to
   markdown. If the structured call itself fails for any reason
   (malformed JSON from a weak model, transient provider issue), fall
   back to a plain ``llm.invoke`` so the pipeline never blocks.

Centralising the pattern here keeps the agent factories small and ensures
all three agents log the same warnings when fallback fires.

The analyst extraction path (:func:`extract_analyst_signal`) follows a
stricter contract than ``invoke_structured_or_freetext``: SignalFusion
needs a typed ``AnalystSignal`` for every channel, not a free-text
fallback, so the helper tries structured output, then a JSON-mode
self-repair retry, then a heuristic last-resort that synthesises a
neutral signal from the markdown. This keeps the dict-merge reducer's
key set predictable and the fusion math KeyError-free.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def bind_structured(llm: Any, schema: type[T], agent_name: str) -> Optional[Any]:
    """Return ``llm.with_structured_output(schema)`` or ``None`` if unsupported.

    Logs a warning when the binding fails so the user understands the agent
    will use free-text generation for every call instead of one-shot fallback.
    """
    try:
        return llm.with_structured_output(schema)
    except (NotImplementedError, AttributeError) as exc:
        logger.warning(
            "%s: provider does not support with_structured_output (%s); "
            "falling back to free-text generation",
            agent_name, exc,
        )
        return None


def invoke_structured_or_freetext(
    structured_llm: Optional[Any],
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
) -> str:
    """Run the structured call and render to markdown; fall back to free-text on any failure.

    ``prompt`` is whatever the underlying LLM accepts (a string for chat
    invocations, a list of message dicts for chat models that take that
    shape). The same value is forwarded to the free-text path so the
    fallback sees the same input the structured call did.
    """
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            return render(result)
        except Exception as exc:
            logger.warning(
                "%s: structured-output invocation failed (%s); retrying once as free text",
                agent_name, exc,
            )

    response = plain_llm.invoke(prompt)
    return response.content


# ---------------------------------------------------------------------------
# Strict extraction (used by analysts to populate AnalystSignal)
# ---------------------------------------------------------------------------


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _coerce_to_pydantic(schema: type[T], data: Any) -> T:
    """Validate ``data`` against ``schema``; raises ``ValidationError`` on failure."""
    if isinstance(data, schema):
        return data
    if isinstance(data, dict):
        return schema.model_validate(data)
    if isinstance(data, str):
        match = _JSON_BLOCK_RE.search(data)
        if match is None:
            raise ValidationError.from_exception_data(
                schema.__name__,
                [{"type": "value_error", "loc": (), "msg": "no JSON object found", "input": data}],
            )
        return schema.model_validate_json(match.group(0))
    raise ValidationError.from_exception_data(
        schema.__name__,
        [{"type": "value_error", "loc": (), "msg": "unexpected type", "input": data}],
    )


def extract_structured_with_repair(
    *,
    structured_llm: Optional[Any],
    plain_llm: Any,
    schema: type[T],
    prompt: Any,
    agent_name: str,
    heuristic_fallback: Callable[[], T],
) -> T:
    """Try structured output → one JSON-mode self-repair retry → heuristic fallback.

    The contract is stricter than :func:`invoke_structured_or_freetext`:
    the caller always gets back a valid ``schema`` instance, never a raw
    string. SignalFusion relies on this — every analyst channel must end
    up with a typed ``AnalystSignal`` so the dict-merge reducer's key
    set is predictable.

    Steps:

    1. ``structured_llm.invoke(prompt)`` — if it returns a model instance
       or anything that validates against ``schema``, return it.
    2. On any failure, send a repair prompt that includes the original
       request, the validator's error, and an explicit JSON-only output
       instruction; parse the response with :func:`_coerce_to_pydantic`.
    3. If repair also fails, call ``heuristic_fallback()`` and log a
       warning. The fallback should produce a sensible neutral / low-
       confidence signal — the pipeline must continue.
    """
    last_error: Optional[Exception] = None

    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            return _coerce_to_pydantic(schema, result)
        except Exception as exc:
            last_error = exc
            logger.warning(
                "%s: structured-output call failed (%s); attempting JSON-mode self-repair",
                agent_name, exc,
            )

    repair_prompt = _build_repair_prompt(prompt, schema, last_error)
    try:
        response = plain_llm.invoke(repair_prompt)
        content = response.content if hasattr(response, "content") else response
        return _coerce_to_pydantic(schema, content)
    except Exception as exc:
        logger.warning(
            "%s: self-repair JSON pass failed (%s); falling back to heuristic synthesis",
            agent_name, exc,
        )

    return heuristic_fallback()


def extract_analyst_signal(
    *,
    llm: Any,
    markdown_report: str,
    analyst_name: str,
    ticker: str,
) -> "AnalystSignal":
    """Convert an analyst's free-text markdown report to a typed ``AnalystSignal``.

    The four analyst nodes call this after their tool loop has completed
    and the markdown report is final. The call always succeeds: structured
    output → JSON-mode self-repair → heuristic synthesis, in that order.
    The fusion layer is therefore guaranteed to see a signal for every
    requested channel.
    """
    from tradingagents.agents.schemas import AnalystSignal, SignalDirection  # local to avoid cycle

    prompt = (
        f"You are extracting a structured signal from the {analyst_name} report "
        f"on {ticker}. Read the report below and emit a JSON object matching "
        "the AnalystSignal schema.\n\n"
        "Conventions:\n"
        "- ``direction`` is bullish / bearish / neutral.\n"
        "- ``score`` is on [-1, 1]: -1 max bearish, +1 max bullish, 0 no signal. "
        "Match the sign of ``direction``.\n"
        "- ``confidence`` is on [0, 1] and reflects evidence quality and "
        "sample size, not the magnitude of the call.\n"
        "- ``evidence_count`` counts distinct data points (indicators, "
        "headlines, ratios, posts) the report cites.\n"
        "- ``key_evidence`` is three to five short bullet-style strings that "
        "each stand alone as a piece of evidence.\n"
        "- ``report`` echoes the full markdown report you were given.\n\n"
        f"Report:\n<<<\n{markdown_report}\n>>>"
    )

    structured_llm = bind_structured(llm, AnalystSignal, f"{analyst_name} extractor")

    def _heuristic() -> "AnalystSignal":
        direction = _heuristic_direction(markdown_report)
        score = {SignalDirection.BULLISH: 0.3, SignalDirection.BEARISH: -0.3, SignalDirection.NEUTRAL: 0.0}[direction]
        logger.warning(
            "%s extractor: using heuristic AnalystSignal (direction=%s, low confidence)",
            analyst_name, direction.value,
        )
        return AnalystSignal(
            report=markdown_report,
            direction=direction,
            score=score,
            confidence=0.3,
            evidence_count=0,
            key_evidence=[],
        )

    signal = extract_structured_with_repair(
        structured_llm=structured_llm,
        plain_llm=llm,
        schema=AnalystSignal,
        prompt=prompt,
        agent_name=f"{analyst_name} extractor",
        heuristic_fallback=_heuristic,
    )

    # Models occasionally drop or truncate the echoed report. Restore it
    # so the downstream Bull/Bear prompt always sees the original prose.
    if not signal.report or len(signal.report) < 0.5 * len(markdown_report):
        signal = signal.model_copy(update={"report": markdown_report})

    return _normalise_sign_consistency(signal, analyst_name)


def _heuristic_direction(markdown_report: str) -> Any:
    """Last-resort direction read from FINAL TRANSACTION PROPOSAL or keyword tally."""
    from tradingagents.agents.schemas import SignalDirection

    upper = markdown_report.upper()
    proposal_match = re.search(r"FINAL TRANSACTION PROPOSAL:\s*\*\*(BUY|SELL|HOLD)\*\*", upper)
    if proposal_match:
        word = proposal_match.group(1)
        if word == "BUY":
            return SignalDirection.BULLISH
        if word == "SELL":
            return SignalDirection.BEARISH
        return SignalDirection.NEUTRAL

    bullish_keywords = ("BULLISH", "OVERWEIGHT", "BUY", "STRONG GROWTH", "UPSIDE")
    bearish_keywords = ("BEARISH", "UNDERWEIGHT", "SELL", "DOWNSIDE", "DETERIORATION")
    bull = sum(upper.count(k) for k in bullish_keywords)
    bear = sum(upper.count(k) for k in bearish_keywords)
    if bull > bear * 1.5:
        return SignalDirection.BULLISH
    if bear > bull * 1.5:
        return SignalDirection.BEARISH
    return SignalDirection.NEUTRAL


def _normalise_sign_consistency(signal: "AnalystSignal", agent_name: str) -> "AnalystSignal":
    """If direction and score sign disagree, clamp ``score`` toward ``direction``.

    Models occasionally emit e.g. ``direction=bullish`` with ``score=-0.1``.
    Rather than failing the run, we trust ``direction`` (the categorical
    label models get right more often than the magnitude) and clamp the
    score to a small value of the matching sign — logged so the user can
    inspect frequency in production.
    """
    from tradingagents.agents.schemas import SignalDirection

    if signal.direction == SignalDirection.BULLISH and signal.score < 0:
        logger.warning("%s extractor: bullish direction with negative score (%.3f); clamping to 0.1", agent_name, signal.score)
        return signal.model_copy(update={"score": 0.1})
    if signal.direction == SignalDirection.BEARISH and signal.score > 0:
        logger.warning("%s extractor: bearish direction with positive score (%.3f); clamping to -0.1", agent_name, signal.score)
        return signal.model_copy(update={"score": -0.1})
    if signal.direction == SignalDirection.NEUTRAL and abs(signal.score) > 0.5:
        logger.warning("%s extractor: neutral direction with large score (%.3f); clamping to 0.0", agent_name, signal.score)
        return signal.model_copy(update={"score": 0.0})
    return signal


def _build_repair_prompt(original_prompt: Any, schema: type[BaseModel], error: Optional[Exception]) -> str:
    """Compose a single-string repair prompt the plain LLM can answer."""
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    error_str = f"{type(error).__name__}: {error}" if error is not None else "no prior attempt"

    if isinstance(original_prompt, str):
        original = original_prompt
    elif isinstance(original_prompt, list):
        parts = []
        for msg in original_prompt:
            if isinstance(msg, dict):
                parts.append(f"[{msg.get('role', '?')}] {msg.get('content', '')}")
            else:
                parts.append(str(msg))
        original = "\n".join(parts)
    else:
        original = str(original_prompt)

    return (
        "The previous attempt to produce a JSON object failed validation.\n"
        f"Validator error: {error_str}\n\n"
        "Re-emit ONLY a JSON object that satisfies this schema. No prose, "
        "no markdown fences, no commentary — just the JSON object.\n\n"
        f"Schema:\n{schema_json}\n\n"
        f"Original request:\n{original}"
    )
