"""Tests for debate turn authorship (capability debate-turn-authorship).

Verifies:
- Opening-turn prompts omit rebuttal wording and the opposing-argument line.
- Subsequent-turn prompts include both.
- No prompt stages a moderated panel (no "moderator" framing).
- Stored turn bodies carry no self-label; the composed history does.
- The composed history keeps the speaker labels context_compaction.py needs.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.researchers.bear_researcher import _build_bear_prompt
from tradingagents.agents.researchers.bull_researcher import _build_bull_prompt
from tradingagents.agents.risk_mgmt.aggressive_debator import _build_aggressive_prompt
from tradingagents.agents.risk_mgmt.conservative_debator import _build_conservative_prompt
from tradingagents.agents.risk_mgmt.neutral_debator import _build_neutral_prompt

# --- Helpers -----------------------------------------------------------------

def _base_prompt_kwargs(**overrides):
    base = {
        "target_label": "stock",
        "instrument_context": "Ticker: TEST",
        "alignment_line": "",
        "market_research_report": "market ok",
        "sentiment_report": "sentiment ok",
        "news_report": "news ok",
        "fundamentals_label": "Company fundamentals report",
        "fundamentals_report": "fundamentals ok",
        "history": "",
        "skill_prompt": "",
        "language_instruction": "",
    }
    base.update(overrides)
    return base


def _base_risk_prompt_kwargs(**overrides):
    base = {
        "trader_decision": "BUY 100 shares",
        "instrument_context": "Ticker: TEST",
        "market_research_report": "market ok",
        "sentiment_report": "sentiment ok",
        "news_report": "news ok",
        "fundamentals_report": "fundamentals ok",
        "history": "",
        "language_instruction": "",
    }
    base.update(overrides)
    return base


# --- Bull researcher -------------------------------------------------------


@pytest.mark.unit
def test_bull_opening_prompt_has_no_rebuttal_wording():
    prompt = _build_bull_prompt(
        **_base_prompt_kwargs(opposing_response="", history="")
    )
    assert "rebut" not in prompt.lower()
    assert "counter" not in prompt.lower().split("key points")[0] if "key points" in prompt.lower() else True
    # No "last bear argument" line when there is no bear argument.
    assert "last bear" not in prompt.lower()


@pytest.mark.unit
def test_bull_rebuttal_prompt_includes_opposing_argument():
    prompt = _build_bull_prompt(
        **_base_prompt_kwargs(
            opposing_response="bear says sell",
            history="Bear Analyst: bear says sell",
        )
    )
    assert "rebut" in prompt.lower() or "counter" in prompt.lower()
    assert "bear says sell" in prompt
    assert "last bear analyst argument" in prompt.lower()


@pytest.mark.unit
def test_bull_prompt_has_no_moderator_framing():
    prompt = _build_bull_prompt(
        **_base_prompt_kwargs(opposing_response="bear case")
    )
    lower = prompt.lower()
    # Prompt must not stage a moderated panel: no addressing a moderator as
    # a participant, no "moderator's" possession, no "dear moderator" form.
    # The phrase "do not address a moderator" is a prohibition, not framing.
    assert "the moderator's" not in lower
    assert "dear moderator" not in lower
    assert "mr. moderator" not in lower
    assert "address the moderator" not in lower


@pytest.mark.unit
def test_bull_prompt_forbids_other_speakers():
    prompt = _build_bull_prompt(**_base_prompt_kwargs(opposing_response=""))
    assert "single speaker" in prompt.lower() or "only as the bull analyst" in prompt.lower()


@pytest.mark.unit
def test_bull_prompt_forbids_self_label():
    prompt = _build_bull_prompt(**_base_prompt_kwargs(opposing_response=""))
    assert "no self-label" in prompt.lower() or "do not prepend a speaker label" in prompt.lower()


# --- Bear researcher -------------------------------------------------------


@pytest.mark.unit
def test_bear_opening_prompt_has_no_rebuttal_wording():
    prompt = _build_bear_prompt(
        **_base_prompt_kwargs(opposing_response="", history="")
    )
    assert "last bull" not in prompt.lower()


@pytest.mark.unit
def test_bear_rebuttal_prompt_includes_opposing_argument():
    prompt = _build_bear_prompt(
        **_base_prompt_kwargs(
            opposing_response="bull says buy",
            history="Bull Analyst: bull says buy",
        )
    )
    assert "bull says buy" in prompt
    assert "last bull analyst argument" in prompt.lower()


@pytest.mark.unit
def test_bear_prompt_has_no_moderator_framing():
    prompt = _build_bear_prompt(
        **_base_prompt_kwargs(opposing_response="bull case")
    )
    lower = prompt.lower()
    assert "the moderator's" not in lower
    assert "dear moderator" not in lower
    assert "mr. moderator" not in lower
    assert "address the moderator" not in lower


# --- Turn body vs composed history label -----------------------------------


def _mock_llm_response(content: str) -> MagicMock:
    response = MagicMock()
    response.content = content
    llm = MagicMock()
    llm.invoke.return_value = response
    return llm


@pytest.mark.unit
def test_bull_stored_body_has_no_label_composed_history_does():
    from tradingagents.agents.researchers.bull_researcher import create_bull_researcher

    llm = _mock_llm_response("bull argument text")
    state = {
        "company_of_interest": "TEST",
        "asset_type": "stock",
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 0,
        },
        "market_report": "market ok",
        "sentiment_report": "sentiment ok",
        "news_report": "news ok",
        "fundamentals_report": "fundamentals ok",
    }
    result = create_bull_researcher(llm)(state)
    new_state = result["investment_debate_state"]

    # Per-side body and current_response carry raw text (no label prefix).
    assert new_state["current_response"] == "bull argument text"
    assert "bull argument text" in new_state["bull_history"]
    assert not new_state["bull_history"].strip().startswith("Bull Analyst:")

    # Composed history carries the label (compactor contract).
    assert "Bull Analyst: bull argument text" in new_state["history"]


@pytest.mark.unit
def test_bear_stored_body_has_no_label_composed_history_does():
    from tradingagents.agents.researchers.bear_researcher import create_bear_researcher

    llm = _mock_llm_response("bear argument text")
    state = {
        "company_of_interest": "TEST",
        "asset_type": "stock",
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 0,
        },
        "market_report": "market ok",
        "sentiment_report": "sentiment ok",
        "news_report": "news ok",
        "fundamentals_report": "fundamentals ok",
    }
    result = create_bear_researcher(llm)(state)
    new_state = result["investment_debate_state"]

    assert new_state["current_response"] == "bear argument text"
    assert not new_state["bear_history"].strip().startswith("Bear Analyst:")
    assert "Bear Analyst: bear argument text" in new_state["history"]


# --- Risk debators ----------------------------------------------------------


@pytest.mark.unit
def test_aggressive_opening_prompt_has_no_opposing_lines():
    prompt = _build_aggressive_prompt(
        **_base_risk_prompt_kwargs(
            conservative_response="",
            neutral_response="",
        )
    )
    assert "last conservative" not in prompt.lower()
    assert "last neutral" not in prompt.lower()


@pytest.mark.unit
def test_aggressive_rebuttal_prompt_includes_opposing_arguments():
    prompt = _build_aggressive_prompt(
        **_base_risk_prompt_kwargs(
            conservative_response="conservative says no",
            neutral_response="neutral says maybe",
        )
    )
    assert "conservative says no" in prompt
    assert "neutral says maybe" in prompt


@pytest.mark.unit
def test_aggressive_prompt_has_no_moderator_framing():
    prompt = _build_aggressive_prompt(
        **_base_risk_prompt_kwargs(
            conservative_response="x",
            neutral_response="y",
        )
    )
    lower = prompt.lower()
    assert "the moderator's" not in lower
    assert "dear moderator" not in lower
    assert "mr. moderator" not in lower


@pytest.mark.unit
def test_conservative_prompt_has_no_moderator_framing():
    prompt = _build_conservative_prompt(
        **_base_risk_prompt_kwargs(
            aggressive_response="x",
            neutral_response="y",
        )
    )
    lower = prompt.lower()
    assert "the moderator's" not in lower
    assert "dear moderator" not in lower
    assert "mr. moderator" not in lower


@pytest.mark.unit
def test_neutral_prompt_has_no_moderator_framing():
    prompt = _build_neutral_prompt(
        **_base_risk_prompt_kwargs(
            aggressive_response="x",
            conservative_response="y",
        )
    )
    lower = prompt.lower()
    assert "the moderator's" not in lower
    assert "dear moderator" not in lower
    assert "mr. moderator" not in lower


# --- Foreign-attribution detector (reusable for rendering guard) ------------


FOREIGN_SPEAKER_PATTERNS = (
    "Moderator:",
    "Bull Analyst:",
    "Bear Analyst:",
    "Aggressive Analyst:",
    "Conservative Analyst:",
    "Neutral Analyst:",
)


def contains_foreign_attribution(text: str, own_label: str) -> bool:
    """Return True if the text appears to contain another participant's attribution.

    Used by both the prompt tests and (later) the rendering guard. Checks for
    bolded or plain speaker labels belonging to roles other than ``own_label``.
    """
    lines = text.strip().splitlines()
    # Check the first few lines (where a speaker label typically appears).
    for line in lines[:5]:
        stripped = line.lstrip("*# ").strip()
        for pattern in FOREIGN_SPEAKER_PATTERNS:
            if pattern.lower() in stripped.lower() and pattern != own_label:
                return True
    return False


@pytest.mark.unit
def test_foreign_attribution_detector_flags_other_speaker():
    text = "**Moderator:** hello\n**Bear Analyst:** thanks"
    assert contains_foreign_attribution(text, "Bull Analyst:") is True


@pytest.mark.unit
def test_foreign_attribution_detector_ignores_clean_turn():
    text = "Here is my argument:\n- point one\n- point two"
    assert contains_foreign_attribution(text, "Bull Analyst:") is False


@pytest.mark.unit
def test_foreign_attribution_detector_ignores_own_label():
    text = "Bull Analyst: my argument here"
    assert contains_foreign_attribution(text, "Bull Analyst:") is False
