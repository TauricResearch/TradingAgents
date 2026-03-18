"""Robust JSON extraction from LLM responses that may wrap JSON in markdown or prose."""

from __future__ import annotations

import json
import re
from typing import Any


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

    # 1. Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Strip <think>...</think> blocks (DeepSeek R1)
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Try again after stripping think blocks
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. Extract from markdown code fences
    fence_pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
    fences = re.findall(fence_pattern, cleaned, re.DOTALL)
    for block in fences:
        try:
            return json.loads(block.strip())
        except json.JSONDecodeError:
            continue

    # 4. Find first '{' to last '}'
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(cleaned[first_brace : last_brace + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"Could not extract valid JSON from LLM response (length={len(text)}, "
        f"preview={text[:200]!r})"
    )
