"""Robust JSON extraction from LLM responses that may wrap JSON in markdown or prose."""

from __future__ import annotations

import json
import re
from typing import Any

# Pre-compiled regex patterns for better performance
THINK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
# Additional patterns for closed-tag variants only.
# Unclosed tags are handled separately in sanitize_llm_output via str.find() truncation,
# which preserves any content that appears *before* the opening tag (content at or
# after the tag position is discarded).
THINK_VARIANTS = [
    re.compile(r"<thinking>.*?</thinking>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<thought>.*?</thought>", re.DOTALL | re.IGNORECASE),
]
FENCE_PATTERN = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def sanitize_llm_output(text: str) -> str:
    """Robustly strip <think>, <thinking>, or <thought> blocks from LLM output.

    Used to prevent internal monologue from leaking into downstream prompts
    where it consumes unnecessary context and tokens.
    """
    if not text:
        return ""

    cleaned = text
    # 1. Strip the standard <think> tags (common in DeepSeek R1)
    cleaned = THINK_PATTERN.sub("", cleaned)

    # 2. Strip common variants
    for pattern in THINK_VARIANTS:
        cleaned = pattern.sub("", cleaned)

    # 3. Best-effort: if a tag is opened but never closed, strip everything after it
    # (Happens if LLM is cut off mid-thought)
    for tag in ("<think>", "<thinking>", "<thought>"):
        idx = cleaned.lower().find(tag)
        if idx != -1:
            cleaned = cleaned[:idx]

    # 4. Clean up any remaining close-tags that might exist without an open tag
    for tag in ("</think>", "</thinking>", "</thought>"):
        cleaned = re.sub(re.escape(tag), "", cleaned, flags=re.IGNORECASE)

    return cleaned.strip()


def extract_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from LLM output that may contain markdown fences,
    preamble/postamble text, or <think> blocks.

    Strategy (in order):
    1. Try direct json.loads() — works if the LLM returned pure JSON
    2. Strip <think>...</think> blocks (DeepSeek R1 reasoning)
    3. Extract from markdown code fences (```json ... ``` or ``` ... ```)
    4. Find the first '{' and last '}' and try to parse that substring
    5. Raise ValueError if nothing works

    Args:
        text: Raw LLM response string.

    Returns:
        Parsed JSON dict.

    Raises:
        ValueError: If no valid JSON object could be extracted.
    """
    if not text or not text.strip():
        raise ValueError("Empty input — no JSON to extract")

    def _ensure_dict(obj: object) -> dict[str, Any]:
        if not isinstance(obj, dict):
            raise ValueError(f"Expected a JSON object (dict), got {type(obj).__name__}")
        return obj

    # 1. Direct parse
    try:
        return _ensure_dict(json.loads(text))
    except json.JSONDecodeError:
        pass

    # 2. Strip <think>... blocks using the new utility
    cleaned = sanitize_llm_output(text)

    # Try again after stripping
    try:
        return _ensure_dict(json.loads(cleaned))
    except json.JSONDecodeError:
        pass

    # 3. Extract from markdown code fences
    fences = FENCE_PATTERN.findall(cleaned)
    for block in fences:
        try:
            return _ensure_dict(json.loads(block.strip()))
        except (json.JSONDecodeError, ValueError):
            # JSONDecodeError = bad JSON; ValueError = parsed but not a dict
            continue

    # 4. Find first '{' to last '}'
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            return _ensure_dict(json.loads(cleaned[first_brace : last_brace + 1]))
        except (json.JSONDecodeError, ValueError):
            # JSONDecodeError = bad JSON; ValueError = parsed but not a dict
            pass

    raise ValueError(
        f"Could not extract valid JSON from LLM response (length={len(text)}, "
        f"preview={text[:200]!r})"
    )
