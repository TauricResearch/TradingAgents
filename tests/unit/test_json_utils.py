"""Tests for robust JSON extraction from LLM output."""

import pytest

from tradingagents.agents.utils.json_utils import extract_json, sanitize_llm_output

# ─── sanitize_llm_output tests ───────────────────────────────────────────────


def test_sanitize_empty_string():
    assert sanitize_llm_output("") == ""


def test_sanitize_no_tags():
    text = "Just plain output with no tags."
    assert sanitize_llm_output(text) == text


def test_sanitize_closed_think_tag():
    text = "<think>internal reasoning</think>Final answer."
    assert sanitize_llm_output(text) == "Final answer."


def test_sanitize_thinking_variant():
    text = "<thinking>Some deliberation.</thinking>Result here."
    assert sanitize_llm_output(text) == "Result here."


def test_sanitize_thought_variant():
    text = "<thought>private thought</thought>Output."
    assert sanitize_llm_output(text) == "Output."


def test_sanitize_case_insensitive():
    text = "<THINK>Upper case think block.</THINK>Answer."
    assert sanitize_llm_output(text) == "Answer."


def test_sanitize_unclosed_think_at_start():
    """All content should be discarded when the unclosed tag starts at position 0."""
    text = "<think>Reasoning that was cut off mid-generation"
    assert sanitize_llm_output(text) == ""


def test_sanitize_unclosed_think_in_middle():
    """Content appearing before the unclosed tag must be preserved.

    sanitize_llm_output calls .strip() on the result, so any trailing whitespace
    or newline between the preserved content and the tag is removed.
    """
    text = '{"result": 1}\n<think>Unclosed reasoning leak'
    assert sanitize_llm_output(text) == '{"result": 1}'


def test_sanitize_trailing_whitespace_stripped():
    """sanitize_llm_output always strips leading/trailing whitespace from the result.

    When content before an unclosed tag ends with a newline or spaces those
    characters are stripped, not preserved.
    """
    text = "clean output  \n<think>leaked reasoning"
    result = sanitize_llm_output(text)
    assert result == "clean output"
    assert not result.endswith(("\n", " "))


def test_sanitize_orphan_close_tag():
    """A stray close-tag without a matching open-tag should be removed."""
    text = "Answer text.</think>"
    assert sanitize_llm_output(text) == "Answer text."


def test_sanitize_multiline_think_block():
    text = "<think>\nLine one.\nLine two.\n</think>\nFinal output."
    assert sanitize_llm_output(text) == "Final output."


def test_sanitize_multiple_closed_blocks():
    """Multiple reasoning blocks should all be stripped."""
    text = "<think>first</think> middle <thinking>second</thinking> end"
    result = sanitize_llm_output(text)
    assert "first" not in result
    assert "second" not in result
    assert "end" in result


# ─── Happy-path tests ─────────────────────────────────────────────────────────


def test_pure_json():
    assert extract_json('{"key": "value"}') == {"key": "value"}


def test_json_with_whitespace():
    assert extract_json('  \n{"key": "value"}\n  ') == {"key": "value"}


def test_markdown_fence_json():
    text = '```json\n{"key": "value"}\n```'
    assert extract_json(text) == {"key": "value"}


def test_markdown_fence_no_lang():
    text = '```\n{"key": "value"}\n```'
    assert extract_json(text) == {"key": "value"}


def test_think_preamble_only():
    text = '<think>I need to analyze the macro environment carefully.</think>\n{"key": "value"}'
    assert extract_json(text) == {"key": "value"}


def test_think_plus_fence():
    text = '<think>Some reasoning here.</think>\n```json\n{"key": "value"}\n```'
    assert extract_json(text) == {"key": "value"}


def test_prose_with_json():
    text = 'Here is the result:\n{"key": "value"}\nDone.'
    assert extract_json(text) == {"key": "value"}


def test_nested_json():
    data = {
        "timeframe": "1 month",
        "executive_summary": "Strong growth momentum",
        "macro_context": {
            "economic_cycle": "expansion",
            "central_bank_stance": "hawkish",
            "geopolitical_risks": ["trade tensions", "energy prices"],
        },
        "key_themes": [
            {
                "theme": "AI Infrastructure",
                "description": "Data center boom",
                "conviction": "high",
                "timeframe": "3-6 months",
            }
        ],
        "stocks_to_investigate": [
            {
                "ticker": "NVDA",
                "name": "NVIDIA Corp",
                "sector": "Technology",
                "rationale": "GPU demand for AI training",
                "thesis_angle": "growth",
                "conviction": "high",
                "key_catalysts": ["H100 demand", "Blackwell launch"],
                "risks": ["Supply constraints", "Competition"],
            }
        ],
        "risk_factors": ["Fed rate hikes", "China tensions"],
    }
    import json

    text = json.dumps(data)
    result = extract_json(text)
    assert result["timeframe"] == "1 month"
    assert result["stocks_to_investigate"][0]["ticker"] == "NVDA"


def test_deepseek_r1_realistic():
    """Simulate a real DeepSeek R1 response with think block and JSON fence."""
    text = (
        "<think>\n"
        "Let me analyze the macro environment. The geopolitical scanner shows tension...\n"
        "I need to identify the top 8-10 stocks.\n"
        "</think>\n"
        "```json\n"
        '{"timeframe": "1 month", "executive_summary": "Bullish macro backdrop", '
        '"macro_context": {"economic_cycle": "expansion", "central_bank_stance": "neutral", "geopolitical_risks": []}, '
        '"key_themes": [], "stocks_to_investigate": [{"ticker": "AAPL", "name": "Apple", "sector": "Technology", '
        '"rationale": "Strong cash flows", "thesis_angle": "value", "conviction": "high", '
        '"key_catalysts": ["Services growth"], "risks": ["China sales"]}], "risk_factors": []}\n'
        "```"
    )
    result = extract_json(text)
    assert result["timeframe"] == "1 month"
    assert result["stocks_to_investigate"][0]["ticker"] == "AAPL"


def test_preamble_and_postamble():
    """JSON buried in prose before and after."""
    text = (
        'Based on my analysis of the market data:\n\n{"result": 42}\n\nThis concludes my analysis.'
    )
    assert extract_json(text) == {"result": 42}


# ─── Error cases ──────────────────────────────────────────────────────────────


def test_empty_input():
    with pytest.raises(ValueError, match="Empty input"):
        extract_json("")


def test_whitespace_only():
    with pytest.raises(ValueError, match="Empty input"):
        extract_json("   \n\t  ")


def test_malformed_json_no_fallback():
    with pytest.raises(ValueError):
        extract_json('{"key": value_without_quotes}')


def test_no_json_at_all():
    with pytest.raises(ValueError):
        extract_json("Just some text with no JSON structure at all")


def test_array_input_raises_value_error():
    """extract_json rejects JSON arrays — only dicts are accepted.

    All callers (macro_synthesis, macro_bridge, CLI) call .get() on the result,
    so returning a list would cause AttributeError downstream.  The function
    enforces dict-only return at runtime.
    """
    with pytest.raises(ValueError, match="Expected a JSON object"):
        extract_json("[1, 2, 3]")
