"""Live regression test for the news analyst prompt and validator.

This test replays a reduced version of the CSTM payload captured from a real
run where the model cited an internal prompt header ("Macro Regime
Classification") as if it were a source. The test is opt-in because it makes a
real LLM call and is non-deterministic by nature.

Run manually with:
    TRADINGAGENTS_ENABLE_LIVE_LLM_TESTS=1 \
    TRADINGAGENTS_LIVE_NEWS_ANALYST_PROVIDER=openai \
    OPENAI_API_KEY=... \
    pytest tests/integration/test_news_analyst_live.py -v -m integration

For OpenRouter, also set:
    TRADINGAGENTS_LIVE_NEWS_ANALYST_PROVIDER=openrouter
    TRADINGAGENTS_LIVE_NEWS_ANALYST_MODEL=<provider-specific-model-name>
    OPENROUTER_API_KEY=...
"""

from __future__ import annotations

import os

import pytest
from langchain_core.messages import HumanMessage

from tradingagents.agents.analysts.news_analyst import create_news_analyst
from tradingagents.agents.utils.agent_utils import format_prefetched_context
from tradingagents.agents.utils.output_validation import (
    extract_allowed_sources_from_context,
    validate_news_analysis_detailed,
)
from tradingagents.llm_clients.factory import create_llm_client

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket()]


def _resolve_live_llm_config() -> tuple[str, str]:
    if os.getenv("TRADINGAGENTS_ENABLE_LIVE_LLM_TESTS") != "1":
        pytest.skip("Set TRADINGAGENTS_ENABLE_LIVE_LLM_TESTS=1 to run live LLM regressions")

    provider = os.getenv("TRADINGAGENTS_LIVE_NEWS_ANALYST_PROVIDER")
    if not provider:
        if os.getenv("OPENROUTER_API_KEY"):
            provider = "openrouter"
        elif os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        else:
            pytest.skip("No LLM API key found for a live news analyst regression")

    model = os.getenv("TRADINGAGENTS_LIVE_NEWS_ANALYST_MODEL")
    if not model:
        if provider == "openai":
            model = "gpt-5-mini"
        else:
            pytest.skip(
                "Set TRADINGAGENTS_LIVE_NEWS_ANALYST_MODEL for non-OpenAI live LLM regressions"
            )

    return provider, model


def _build_cstm_state() -> dict:
    return {
        "messages": [HumanMessage(content="Continue")],
        "trade_date": "2026-04-02",
        "company_of_interest": "CSTM",
        "macro_regime_report": """# Macro Regime Classification
# Data retrieved on: 2026-04-02 14:05:14

## Regime: TRANSITION

| Attribute | Value |
|-----------|-------|
| Regime | **TRANSITION** |
| Composite Score | -1 / 6 |
| Confidence | Low |
| VIX | 27.60 |

## Interpretation

Macro regime: **TRANSITION** (score -1/6, confidence: low). 2 risk-on signals, 3 risk-off signals, 1 neutral.

### What This Means for Trading

- Mixed signals: No strong directional bias — size positions conservatively
- Watch: Upcoming catalysts may resolve direction
- Technicals: Use wider stops; avoid overconfident entries
""",
        "scanner_context_packet": """# SCANNER CONTEXT PACKET: CSTM
Date: 2026-04-02

## I. TICKER-SPECIFIC SCANNER THESIS
Rationale: Breakout accumulation signals align with Materials YTD +9.90% performance and +2 net analyst upgrade bias.
Conviction: medium

## II. STRUCTURED LIVE DATA (GROUND TRUTH)
| Asset | Symbol | Current Price | Change % |
|---|---|---:|---:|
| WTI Crude | CL=F | $109.58 | +9.45% |
| Brent Crude | BZ=F | $109.13 | +7.88% |
| EUR/USD | EURUSD=X | $1.15 | -0.43% |

## III. SMART MONEY & FLOW SIGNALS
- CSTM (Basic Materials) – Footprint: Breakout accumulation; Δ vs sector rotation: +9.90% YTD (confirm)

## IV. FACTOR ALIGNMENT & DRIFT
- Materials revisions align with +9.90% YTD but conflict with -5.60 ppts deceleration (partial divergence)

## VI. SECTOR ROTATION & MARKET REGIME
- Materials YTD +9.90% (2nd)
- Maximum deceleration (1M-1W): Industrials -5.60 ppts

## VII. KEY GLOBAL THEMES
- Defensive Quality Rotation Over Cyclical Exposure: Defensives lead cyclicals by +1.58 ppts over 1 month.
""",
    }


def _build_cstm_prefetched_news() -> dict[str, str]:
    return {
        "Company-Specific News (Last 7 Days)": """{
    "items": "1",
    "feed": [
        {
            "title": "Is It Time To Reassess Constellium (CSTM) After Its 120% One Year Share Price Surge",
            "time_published": "20260327T201008",
            "summary": "This article analyzes Constellium (NYSE: CSTM) after its 120% share price surge over the last year. The DCF analysis indicates a 50.1% undervaluation compared to its intrinsic value of $48.02 per share.",
            "source": "Sahm",
            "source_domain": "Sahm",
            "overall_sentiment_score": 0.422731,
            "overall_sentiment_label": "Bullish"
        }
    ]
}""",
        "Global Macroeconomic News (Last 7 Days)": """{
    "items": "4",
    "feed": [
        {
            "title": "Oil shock manageable but prices reflect assumption that conflict will end soon: BMO",
            "time_published": "20260401T221034",
            "summary": "BMO economists believe oil prices can return to an average of US$80-$85 a barrel if the conflict resolves quickly.",
            "source": "TownAndCountryToday.com",
            "source_domain": "TownAndCountryToday.com"
        },
        {
            "title": "FVCBankcorp Inc Stock: Regional Banking Stability and Growth Potential for North American Investors",
            "time_published": "20260401T220432",
            "summary": "This analysis highlights stability in regional banking for North American investors.",
            "source": "AD HOC NEWS",
            "source_domain": "AD HOC NEWS"
        },
        {
            "title": "Goldman Sachs initiates Freeport-McMoRan stock with buy rating",
            "time_published": "20260401T210741",
            "summary": "Goldman Sachs initiated Freeport-McMoRan with a Buy rating and a $70 price target.",
            "source": "Investing.com",
            "source_domain": "Investing.com"
        },
        {
            "title": "Nonfarm Payrolls Expected to Rise After ADP, ISM",
            "time_published": "20260401T203000",
            "summary": "StoneX said ADP implied +133K payrolls and the ISM employment component implied about +245K.",
            "source": "StoneX",
            "source_domain": "StoneX"
        }
    ]
}""",
    }


def test_news_analyst_live_cstm_payload_avoids_internal_header_citations(monkeypatch):
    provider, model = _resolve_live_llm_config()
    prefetched = _build_cstm_prefetched_news()

    monkeypatch.setattr(
        "tradingagents.agents.analysts.news_analyst.prefetch_tools_parallel",
        lambda _: prefetched,
    )

    llm = create_llm_client(
        provider,
        model,
        timeout=180,
        max_retries=1,
    ).get_llm()

    node = create_news_analyst(llm)
    result = node(_build_cstm_state())
    report = result["news_report"]

    assert "Macro Regime Classification" not in report
    assert not report.startswith("[CRITICAL ABORT]"), report

    prefetched_context = format_prefetched_context(prefetched)
    validation = validate_news_analysis_detailed(
        report,
        "CSTM",
        allowed_source_names=extract_allowed_sources_from_context(prefetched_context),
    )
    assert validation.is_valid, validation.reason
