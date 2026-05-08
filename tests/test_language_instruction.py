"""Tests for get_language_instruction's resolution of language aliases.

We test the function as a black box because it reads from the runtime
config and emits prompt text that's interpolated into LLM system prompts.
The behavior we care about:

* English (default) → empty string (no extra prompt cost).
* Traditional Chinese aliases → firm Traditional-only instruction with
  explicit "no Simplified characters" guard. Mandarin-biased LLMs
  (DeepSeek, Qwen, GLM) need this guard or they emit mixed output.
* Simplified Chinese aliases → firm Simplified-only instruction.
* Bare "Chinese" → resolves to Traditional (the project default for
  ambiguous input; users wanting Simplified must say so explicitly).
* Other languages → generic instruction.
"""

import pytest

from tradingagents.agents.utils.agent_utils import get_language_instruction
from tradingagents.runtime import reset_context_config, set_runtime_config


@pytest.fixture(autouse=True)
def _reset_config():
    yield
    reset_context_config()


def _set_lang(lang: str) -> None:
    set_runtime_config({"output_language": lang}, scope="context")


def test_english_returns_empty():
    _set_lang("English")
    assert get_language_instruction() == ""


def test_english_case_insensitive():
    for v in ("english", "ENGLISH", "  English  "):
        _set_lang(v)
        assert get_language_instruction() == ""


def test_traditional_chinese_explicit():
    _set_lang("Traditional Chinese")
    out = get_language_instruction()
    assert "Traditional Chinese" in out
    assert "繁體中文" in out
    # Must explicitly forbid Simplified — this is the whole point of the function.
    assert "Simplified" in out
    assert "Do NOT" in out or "do not" in out.lower()


def test_traditional_chinese_native_script():
    _set_lang("繁體中文")
    out = get_language_instruction()
    assert "繁體中文" in out
    assert "Simplified" in out  # the no-Simplified guard


def test_traditional_chinese_locale_codes():
    for v in ("zh-TW", "zh_TW", "zh-HK", "TW Chinese", "Hong Kong Chinese"):
        _set_lang(v)
        out = get_language_instruction()
        assert "繁體中文" in out, f"failed for input {v!r}"


def test_simplified_chinese_explicit():
    _set_lang("Simplified Chinese")
    out = get_language_instruction()
    assert "Simplified Chinese" in out
    assert "简体中文" in out
    # Inverse guard
    assert "Traditional" in out


def test_simplified_chinese_locale_codes():
    for v in ("zh-CN", "zh_CN", "Mainland Chinese"):
        _set_lang(v)
        out = get_language_instruction()
        assert "简体中文" in out, f"failed for input {v!r}"


def test_bare_chinese_resolves_to_traditional():
    """Bare 'Chinese' is ambiguous; we map it to Traditional so Mandarin-biased
    models don't silently output Simplified."""
    _set_lang("Chinese")
    out = get_language_instruction()
    assert "繁體中文" in out
    assert "Simplified" in out  # still includes the guard


def test_native_chinese_word_resolves_to_traditional():
    _set_lang("中文")
    out = get_language_instruction()
    assert "繁體中文" in out


def test_other_language_uses_generic_template():
    _set_lang("Japanese")
    out = get_language_instruction()
    assert "Japanese" in out
    assert "Write your entire response" in out
    # No Chinese-specific guards
    assert "繁體" not in out
    assert "简体" not in out


def test_other_language_strips_whitespace():
    _set_lang("  Vietnamese  ")
    out = get_language_instruction()
    assert "Vietnamese" in out
    # Should not have extra whitespace artifacts
    assert "  " not in out.replace("Write your entire response in ", "")
