"""Tests for the pluggable fundamentals-style registry.

These tests lock the public surface of the styles package so adding a
new style can't accidentally break the existing ones, and so the agent
remains resilient to config typos (which should resolve to the default
style, not crash the run).
"""

from __future__ import annotations

import pytest

from tradingagents.agents.analysts.fundamentals_styles import (
    DEFAULT_STYLE_KEY,
    STYLES,
    FundamentalStyle,
    resolve_style,
)
from tradingagents.agents.analysts.fundamentals_styles.buffett_value import (
    BuffettValueStyle,
)
from tradingagents.agents.analysts.fundamentals_styles.comprehensive import (
    ComprehensiveStyle,
)
from tradingagents.agents.analysts.fundamentals_styles.growth import GrowthStyle
from tradingagents.runtime import reset_context_config, set_runtime_config


@pytest.fixture(autouse=True)
def _reset_config():
    yield
    reset_context_config()


def test_registry_has_default_and_named_styles():
    assert DEFAULT_STYLE_KEY in STYLES
    assert "comprehensive" in STYLES
    assert "buffett_value" in STYLES
    assert "growth" in STYLES


def test_default_style_key_is_comprehensive():
    """The previous default behavior (Comprehensive) stays the default to
    preserve backwards compatibility for users who don't pick a style."""
    assert DEFAULT_STYLE_KEY == "comprehensive"


def test_every_registered_style_satisfies_protocol():
    """Every entry in STYLES must have key/label/description/system_message/extra_tools."""
    for key, style in STYLES.items():
        # The Protocol is runtime_checkable
        assert isinstance(style, FundamentalStyle), f"{key} doesn't satisfy FundamentalStyle"
        # Spot check the attributes carry real content
        assert isinstance(style.key, str) and style.key
        assert isinstance(style.label, str) and style.label
        assert isinstance(style.description, str) and style.description
        # system_message returns non-trivial text
        msg = style.system_message()
        assert isinstance(msg, str) and len(msg) > 100, f"{key} system_message is too short"
        # extra_tools returns a list (possibly empty)
        tools = style.extra_tools()
        assert isinstance(tools, list)


def test_resolve_style_returns_default_for_none():
    style = resolve_style(None)
    assert style.key == DEFAULT_STYLE_KEY


def test_resolve_style_returns_default_for_empty_string():
    assert resolve_style("").key == DEFAULT_STYLE_KEY
    assert resolve_style("   ").key == DEFAULT_STYLE_KEY


def test_resolve_style_returns_default_for_unknown_key():
    """Config typos like 'bufett_value' must not crash — fall back gracefully."""
    style = resolve_style("bufett_value")  # missing one 'f'
    assert style.key == DEFAULT_STYLE_KEY


def test_resolve_style_is_case_insensitive():
    """Case and surrounding whitespace shouldn't matter."""
    assert resolve_style("Buffett_Value").key == "buffett_value"
    assert resolve_style("  GROWTH  ").key == "growth"


def test_resolve_style_returns_exact_match():
    assert resolve_style("buffett_value").key == "buffett_value"
    assert resolve_style("growth").key == "growth"


def test_buffett_style_includes_insider_transactions_tool():
    """Buffett analysis genuinely needs insider data; check the extra tool is wired."""
    style = BuffettValueStyle()
    tool_names = [t.name for t in style.extra_tools()]
    assert "get_insider_transactions" in tool_names


def test_comprehensive_and_growth_have_no_extra_tools():
    """These styles work fine with the four default fundamental-data tools."""
    assert ComprehensiveStyle().extra_tools() == []
    assert GrowthStyle().extra_tools() == []


def test_buffett_prompt_mentions_required_concepts():
    """Lock the Buffett prompt to its six lenses so future edits don't silently drop one."""
    msg = BuffettValueStyle().system_message().lower()
    assert "moat" in msg
    assert "owner earnings" in msg
    assert "margin of safety" in msg
    assert "roe" in msg
    assert "insider" in msg
    assert "intrinsic value" in msg


def test_buffett_prompt_includes_skill_derived_framework():
    """Concepts pulled from the Anthropic skills bundle (buffett-analysis,
    moat-analysis, financial-metrics) — locking these guards against a future
    prompt edit silently regressing the framework to a thinner version."""
    msg = BuffettValueStyle().system_message().lower()

    # Seven cornerstones — the foundational filters
    assert "seven cornerstones" in msg
    assert "circle of competence" in msg
    assert "contrarian" in msg

    # Five-moat scoring rubric with specific anchors
    assert "brand power" in msg
    assert "switching cost" in msg
    assert "network effect" in msg
    assert "regulatory" in msg

    # Three-scenario DCF and Owner Earnings formula
    assert "pessimistic" in msg
    assert "10-year forecast" in msg or "10 year forecast" in msg or "10-year" in msg
    assert "d&a" in msg  # Owner Earnings formula reference
    assert "maintenance capex" in msg

    # The Three Terminal Questions
    assert "terminal question" in msg
    # Confirm all three terminal questions are mentioned
    assert "circle of competence" in msg  # Q1
    assert "10 years" in msg or "10-year" in msg  # Q2
    assert "5 years" in msg or "five years" in msg or "closed for 5" in msg  # Q3

    # Earnings-quality test markers
    assert "earnings-quality" in msg or "earnings quality" in msg
    assert "operating cf" in msg
    assert "accounts receivable" in msg

    # Margin-of-safety bands with explicit thresholds
    assert "≥25%" in msg or ">=25%" in msg or "25%" in msg
    assert "sweet spot" in msg or "30%" in msg


def test_buffett_prompt_has_output_format():
    """The committee-memo output table makes downstream parsing more reliable."""
    msg = BuffettValueStyle().system_message()
    # The required output format section
    assert "OUTPUT FORMAT" in msg or "output format" in msg.lower()
    # Markdown table column headers we rely on
    assert "Verdict" in msg
    assert "BUY / HOLD / SKIP" in msg or "BUY/HOLD/SKIP" in msg


def test_buffett_prompt_length_is_substantive_but_not_runaway():
    """Sanity bound: a prompt shorter than 4k chars probably lost content;
    longer than 14k chars probably duplicates or bloats and should be trimmed.

    Cap was raised from 12k → 14k when Lens 0 (currency sanity check) was
    added — the section is small but pushes the total above the old bound.
    """
    msg = BuffettValueStyle().system_message()
    assert 4000 < len(msg) < 14000, f"Buffett prompt is {len(msg)} chars"


def test_growth_prompt_mentions_required_concepts():
    """Lock the Growth prompt to its key Lynch/Fisher concepts."""
    msg = GrowthStyle().system_message().lower()
    assert "peg" in msg
    assert "growth" in msg
    assert "reinvestment" in msg or "reinvest" in msg
    assert "tam" in msg or "runway" in msg


def test_all_keys_are_unique():
    """Two styles can't share a key — that would shadow one of them in the registry."""
    keys = [s.key for s in STYLES.values()]
    assert len(keys) == len(set(keys))


def test_all_labels_are_distinct():
    """Distinct labels prevent confusion in the CLI picker."""
    labels = [s.label for s in STYLES.values()]
    assert len(labels) == len(set(labels))


def test_fundamentals_analyst_reads_style_from_runtime_config():
    """Smoke test that the analyst factory honors runtime config selection."""
    from tradingagents.agents.analysts.fundamentals_analyst import (
        create_fundamentals_analyst,
        _BASE_TOOLS,
    )
    from unittest.mock import MagicMock

    # With buffett_value selected, the analyst should add the insider tool
    set_runtime_config({"fundamentals_style": "buffett_value"}, scope="context")
    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value = MagicMock(invoke=MagicMock(
        return_value=MagicMock(tool_calls=[], content="ok")
    ))
    node = create_fundamentals_analyst(mock_llm)
    node({
        "trade_date": "2026-05-08",
        "company_of_interest": "AAPL",
        "messages": [],
    })
    # Should have been called with base tools + insider transactions
    bind_args = mock_llm.bind_tools.call_args[0][0]
    tool_names = [t.name for t in bind_args]
    assert "get_insider_transactions" in tool_names
    # Plus all base tools
    base_names = [t.name for t in _BASE_TOOLS]
    for name in base_names:
        assert name in tool_names


def test_fundamentals_analyst_falls_back_when_style_unknown():
    """A bad style key should not crash the analyst — fall back to default."""
    from tradingagents.agents.analysts.fundamentals_analyst import (
        create_fundamentals_analyst,
        _BASE_TOOLS,
    )
    from unittest.mock import MagicMock

    set_runtime_config({"fundamentals_style": "totally_made_up"}, scope="context")
    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value = MagicMock(invoke=MagicMock(
        return_value=MagicMock(tool_calls=[], content="ok")
    ))
    node = create_fundamentals_analyst(mock_llm)
    node({
        "trade_date": "2026-05-08",
        "company_of_interest": "AAPL",
        "messages": [],
    })
    # Default style has no extra tools, so we should see only the 4 base tools
    bind_args = mock_llm.bind_tools.call_args[0][0]
    tool_names = [t.name for t in bind_args]
    assert sorted(tool_names) == sorted([t.name for t in _BASE_TOOLS])
