"""Compare legacy and optimized DeepSeek prompt-cache prefix behavior.

This script does not call DeepSeek. It constructs two representative sentiment
requests with different ticker/date/source content and compares the prompt
prefix fingerprints that determine whether the static prefix can be reused.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

from tradingagents.agents.analysts.sentiment_analyst import (
    SENTIMENT_SYSTEM_MESSAGE,
    build_sentiment_user_prompt,
)
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.prompt_cache import (
    DYNAMIC_CONTEXT_MARKER,
    prompt_prefix_fingerprint,
)


@dataclass(frozen=True)
class SentimentScenario:
    ticker: str
    start_date: str
    end_date: str
    news_block: str
    stocktwits_block: str
    reddit_block: str


def _legacy_sentiment_messages(scenario: SentimentScenario) -> list[dict]:
    instrument_context = build_instrument_context(scenario.ticker)
    system_message = (
        "You are a financial market sentiment analyst. "
        f"Analyze {scenario.ticker} from {scenario.start_date} to {scenario.end_date}. "
        "Use news headlines, StockTwits messages, and Reddit posts."
    )
    user_message = (
        f"{instrument_context}\n\n"
        f"News headlines:\n{scenario.news_block}\n\n"
        f"StockTwits messages:\n{scenario.stocktwits_block}\n\n"
        f"Reddit posts:\n{scenario.reddit_block}"
    )
    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]


def _optimized_sentiment_messages(scenario: SentimentScenario) -> list[dict]:
    return [
        {"role": "system", "content": SENTIMENT_SYSTEM_MESSAGE},
        {
            "role": "user",
            "content": build_sentiment_user_prompt(
                ticker=scenario.ticker,
                instrument_context=build_instrument_context(scenario.ticker),
                start_date=scenario.start_date,
                end_date=scenario.end_date,
                news_block=scenario.news_block,
                stocktwits_block=scenario.stocktwits_block,
                reddit_block=scenario.reddit_block,
            ),
        },
    ]


def compare_sentiment_prompt_cache() -> dict:
    scenario_a = SentimentScenario(
        ticker="NVDA",
        start_date="2026-05-29",
        end_date="2026-06-05",
        news_block="NVDA news: AI capex demand remains strong.",
        stocktwits_block="NVDA StockTwits: Bullish retail flow.",
        reddit_block="NVDA Reddit: High engagement around earnings.",
    )
    scenario_b = SentimentScenario(
        ticker="AAPL",
        start_date="2026-05-28",
        end_date="2026-06-04",
        news_block="AAPL news: Services growth debated.",
        stocktwits_block="AAPL StockTwits: Mixed retail flow.",
        reddit_block="AAPL Reddit: Low engagement around valuation.",
    )

    legacy_a = _legacy_sentiment_messages(scenario_a)
    legacy_b = _legacy_sentiment_messages(scenario_b)
    optimized_a = _optimized_sentiment_messages(scenario_a)
    optimized_b = _optimized_sentiment_messages(scenario_b)

    legacy_a_fp = prompt_prefix_fingerprint(legacy_a)
    legacy_b_fp = prompt_prefix_fingerprint(legacy_b)
    optimized_a_fp = prompt_prefix_fingerprint(optimized_a)
    optimized_b_fp = prompt_prefix_fingerprint(optimized_b)

    return {
        "family": "sentiment",
        "legacy_prefix_equal": legacy_a_fp == legacy_b_fp,
        "optimized_prefix_equal": optimized_a_fp == optimized_b_fp,
        "optimized_has_dynamic_marker": DYNAMIC_CONTEXT_MARKER
        in optimized_a[1]["content"],
        "legacy_prefix_a": legacy_a_fp,
        "legacy_prefix_b": legacy_b_fp,
        "optimized_prefix_a": optimized_a_fp,
        "optimized_prefix_b": optimized_b_fp,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    result = compare_sentiment_prompt_cache()
    if args.json:
        print(json.dumps(result, sort_keys=True))
        return

    print("Prompt family: sentiment")
    print(f"Legacy prefixes equal: {result['legacy_prefix_equal']}")
    print(f"Optimized prefixes equal: {result['optimized_prefix_equal']}")
    print(f"Optimized dynamic marker present: {result['optimized_has_dynamic_marker']}")


if __name__ == "__main__":
    main()
