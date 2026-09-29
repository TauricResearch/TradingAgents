"""Externalized agent prompt loading and policy coverage."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import pytest

from tradingagents.prompts.loader import (
    load_global_policy,
    load_prompt,
    render_agent_prompt,
)

ROLE_PROMPTS = {
    "analysts/market.txt": "You are a trading assistant tasked with analyzing financial markets.",
    "analysts/fundamentals.txt": "You are a researcher tasked with analyzing fundamental information",
    "analysts/news.txt": "You are a news researcher tasked with analyzing recent news",
    "analysts/sentiment.txt": "You are a financial market sentiment analyst.",
    "researchers/bull.txt": "You are a Bull Analyst advocating",
    "researchers/bear.txt": "You are a Bear Analyst making the case",
    "managers/research_manager.txt": "As the Research Manager and debate facilitator",
    "trader/system.txt": "You are a trading agent analyzing market data",
    "risk_mgmt/aggressive.txt": "As the Aggressive Risk Analyst",
    "risk_mgmt/conservative.txt": "As the Conservative Risk Analyst",
    "risk_mgmt/neutral.txt": "As the Neutral Risk Analyst",
    "managers/portfolio_manager.txt": "As the Portfolio Manager",
}

KNOWN_LLM_AGENT_MODULES = [
    "analysts/market_analyst.py",
    "analysts/news_analyst.py",
    "analysts/fundamentals_analyst.py",
    "analysts/sentiment_analyst.py",
    "researchers/bull_researcher.py",
    "researchers/bear_researcher.py",
    "managers/research_manager.py",
    "managers/portfolio_manager.py",
    "risk_mgmt/aggressive_debator.py",
    "risk_mgmt/conservative_debator.py",
    "risk_mgmt/neutral_debator.py",
    "trader/trader.py",
]


@pytest.mark.unit
@pytest.mark.parametrize("path", [
    "global_policy.txt",
    "global_policy.example.hardmode.txt",
    "analysts/tool_system.txt",
    "analysts/prefetched_system.txt",
    "trader/user.txt",
    *ROLE_PROMPTS.keys(),
])
def test_builtin_prompt_files_load(path):
    assert load_prompt(path).strip()


@pytest.mark.unit
def test_prompt_files_are_available_through_package_resources():
    root = resources.files("tradingagents.prompts")
    assert root.joinpath("global_policy.txt").is_file()
    assert root.joinpath("analysts/market.txt").is_file()
    assert root.joinpath("global_policy.example.hardmode.txt").is_file()


@pytest.mark.unit
def test_dynamic_placeholders_interpolate_correctly():
    rendered = render_agent_prompt("analysts/news.txt", asset_label="asset")
    assert "for asset-specific news by ticker symbol" in rendered
    assert "{asset_label}" not in rendered

    user_prompt = load_prompt("trader/user.txt").format(
        company_name="NVDA",
        instrument_context="Instrument context",
        report_section="Technical Market Report:\nRSI 61\n\n",
        portfolio_context="Portfolio context",
        investment_plan="Buy plan",
    )
    assert "NVDA" in user_prompt
    assert "RSI 61" in user_prompt
    assert "Buy plan" in user_prompt


@pytest.mark.unit
@pytest.mark.parametrize("path, role_snippet", ROLE_PROMPTS.items())
def test_global_policy_and_role_text_are_present_after_loading(path, role_snippet):
    rendered = render_agent_prompt(
        path,
        asset_label="company",
        ticker="NVDA",
        start_date="2026-08-01",
        end_date="2026-08-08",
        news_block="news",
        stocktwits_block="stocktwits",
        reddit_block="reddit",
        target_label="stock",
        instrument_context="instrument",
        market_research_report="market",
        sentiment_report="sentiment",
        news_report="macro",
        fundamentals_label="Company fundamentals report",
        fundamentals_report="fundamentals",
        history="history",
        current_response="opponent",
        NO_EXTERNAL_TOOLS="no tools",
        company_name="NVDA",
        report_section="",
        portfolio_context="portfolio",
        investment_plan="plan",
        trader_decision="trader",
        current_conservative_response="conservative",
        current_neutral_response="neutral",
        current_aggressive_response="aggressive",
        research_plan="research",
        trader_plan="trader",
        lessons_line="",
        grounding="",
    )
    assert load_global_policy().strip() in rendered
    assert role_snippet in rendered


@pytest.mark.unit
def test_no_known_llm_agent_omits_global_policy_loader():
    agents_dir = Path(__file__).resolve().parents[1] / "tradingagents" / "agents"
    missing = []
    for rel in KNOWN_LLM_AGENT_MODULES:
        src = (agents_dir / rel).read_text(encoding="utf-8")
        if "render_agent_prompt(" not in src:
            missing.append(rel)
    assert missing == []


@pytest.mark.unit
def test_hardmode_policy_is_not_referenced_by_runtime_code():
    root = Path(__file__).resolve().parents[1] / "tradingagents"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "global_policy.example.hardmode" in text:
            offenders.append(path.relative_to(root).as_posix())
    assert offenders == []
