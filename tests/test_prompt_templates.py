"""Tests for file-backed agent prompt templates."""

import pytest

from tradingagents.agents.utils.prompts import load_prompt_template, render_prompt_template


@pytest.mark.unit
def test_render_prompt_template_substitutes_named_values():
    prompt = render_prompt_template(
        "trader_user.md",
        {
            "company_name": "NVDA",
            "instrument_context": "Treat NVDA as an equity.",
            "investment_plan": "**Recommendation**: Buy",
        },
    )

    assert "NVDA" in prompt
    assert "Treat NVDA as an equity." in prompt
    assert "**Recommendation**: Buy" in prompt
    assert "{company_name}" not in prompt


@pytest.mark.unit
def test_render_prompt_template_requires_all_named_values():
    with pytest.raises(KeyError, match="investment_plan"):
        render_prompt_template(
            "trader_user.md",
            {
                "company_name": "NVDA",
                "instrument_context": "Treat NVDA as an equity.",
            },
        )


@pytest.mark.unit
def test_load_prompt_template_preserves_langchain_placeholders():
    prompt = load_prompt_template("tool_collaboration_system.md")

    assert "{tool_names}" in prompt
    assert "{system_message}" in prompt
