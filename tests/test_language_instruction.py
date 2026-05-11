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


# ---------------------------------------------------------------------------
# Localized section-header labels
# ---------------------------------------------------------------------------

from tradingagents.agents.utils.agent_utils import get_localized_label


def test_english_default_returns_key_unchanged():
    """When language is English, the localized label is identical to the key
    so existing parsers and tests that grep for English labels keep working."""
    _set_lang("English")
    for key in ("Rating", "Action", "Reasoning", "Executive Summary",
                "Investment Thesis", "Recommendation"):
        assert get_localized_label(key) == key


def test_traditional_chinese_translates_key_labels():
    _set_lang("Traditional Chinese")
    assert get_localized_label("Rating") == "評等"
    assert get_localized_label("Executive Summary") == "執行摘要"
    assert get_localized_label("Investment Thesis") == "投資論述"
    assert get_localized_label("Action") == "交易動作"
    assert get_localized_label("Reasoning") == "決策依據"
    assert get_localized_label("Recommendation") == "建議評等"


def test_simplified_chinese_translates_key_labels():
    _set_lang("Simplified Chinese")
    assert get_localized_label("Rating") == "评级"
    assert get_localized_label("Executive Summary") == "执行摘要"
    assert get_localized_label("Action") == "交易动作"


def test_bare_chinese_resolves_to_traditional_labels():
    """Bare 'Chinese' should follow the same Traditional-default mapping as the prompt."""
    _set_lang("Chinese")
    assert get_localized_label("Rating") == "評等"


def test_unknown_key_falls_back_to_english():
    """Adding a new render field without updating every translation map should
    degrade to English rather than crash or return None."""
    _set_lang("Traditional Chinese")
    assert get_localized_label("Some Brand New Field") == "Some Brand New Field"


def test_other_language_uses_english_labels():
    """For non-Chinese languages, the prompt instructs the LLM in that language
    but section headers stay English to keep downstream parsers working."""
    _set_lang("Japanese")
    assert get_localized_label("Rating") == "Rating"


def test_render_pm_decision_uses_localized_labels():
    """End-to-end: when language is Traditional Chinese, the rendered markdown
    must use the Chinese labels but keep the Enum value (Buy/Hold/...) English."""
    from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating, render_pm_decision

    _set_lang("Traditional Chinese")
    decision = PortfolioDecision(
        rating=PortfolioRating.OVERWEIGHT,
        executive_summary="分批建立部位",
        investment_thesis="估值偏低",
    )
    md = render_pm_decision(decision)
    assert "**評等**: Overweight" in md          # label localized, value canonical
    assert "**執行摘要**: 分批建立部位" in md
    assert "**投資論述**: 估值偏低" in md
    # English labels must NOT appear in the Chinese-mode render
    assert "**Rating**" not in md
    assert "**Executive Summary**" not in md


def test_render_pm_decision_english_default_unchanged():
    """English render output is unchanged from the legacy shape — guards backward compat."""
    from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating, render_pm_decision

    _set_lang("English")
    decision = PortfolioDecision(
        rating=PortfolioRating.HOLD,
        executive_summary="Maintain position.",
        investment_thesis="Balanced view.",
    )
    md = render_pm_decision(decision)
    assert "**Rating**: Hold" in md
    assert "**Executive Summary**: Maintain position." in md
    assert "**Investment Thesis**: Balanced view." in md


def test_render_trader_proposal_localized_but_final_line_stays_english():
    """The 'FINAL TRANSACTION PROPOSAL' tail line is part of an external contract
    (stop-signal regex elsewhere) and must remain English even in Chinese mode."""
    from tradingagents.agents.schemas import TraderAction, TraderProposal, render_trader_proposal

    _set_lang("Traditional Chinese")
    proposal = TraderProposal(action=TraderAction.BUY, reasoning="估值便宜")
    md = render_trader_proposal(proposal)
    assert "**交易動作**: Buy" in md
    assert "**決策依據**: 估值便宜" in md
    # The tail-line stop signal must NOT be localized
    assert "FINAL TRANSACTION PROPOSAL: **BUY**" in md


def test_rating_parser_still_works_on_localized_render():
    """parse_rating greps for the canonical English rating word; localized
    labels must not break that contract."""
    from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating, render_pm_decision
    from tradingagents.agents.utils.rating import parse_rating

    _set_lang("Traditional Chinese")
    decision = PortfolioDecision(
        rating=PortfolioRating.BUY,
        executive_summary="進場",
        investment_thesis="安全邊際大",
    )
    md = render_pm_decision(decision)
    assert parse_rating(md) == "Buy"
