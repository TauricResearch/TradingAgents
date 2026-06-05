"""Warm DeepSeek official API context cache for TradingAgents prompt prefixes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable, Iterable

from tradingagents.agents.analysts.derivative_analyst import (
    DERIVATIVES_SYSTEM_MESSAGE,
    build_derivatives_user_prompt,
)
from tradingagents.agents.analysts.market_analyst import (
    MARKET_SYSTEM_MESSAGE,
    build_market_user_prompt,
)
from tradingagents.agents.analysts.sentiment_analyst import (
    SENTIMENT_SYSTEM_MESSAGE,
    build_sentiment_user_prompt,
)
from tradingagents.agents.managers.portfolio_manager import (
    PORTFOLIO_MANAGER_SYSTEM_PROMPT,
    build_portfolio_manager_user_prompt,
)
from tradingagents.agents.managers.research_manager import (
    RESEARCH_MANAGER_SYSTEM_PROMPT,
    build_research_manager_user_prompt,
)
from tradingagents.agents.trader.trader import (
    TRADER_SYSTEM_PROMPT,
    build_trader_user_prompt,
)
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.cost_callback import RunCostCallback
from tradingagents.graph.run_recorder import compute_cache_hit_ratio
from tradingagents.llm_clients import create_llm_client


@dataclass(frozen=True)
class WarmupFamily:
    name: str
    tier: str
    system_message: str
    user_builder: Callable[[], str]


def _warmup_state() -> dict:
    return {
        "company_of_interest": "CACHE-WARMUP",
        "asset_type": "stock",
        "trade_date": "2000-01-01",
        "market_report": "No market report. Cache warm-up only.",
        "sentiment_report": "No sentiment report. Cache warm-up only.",
        "news_report": "No news report. Cache warm-up only.",
        "fundamentals_report": "No fundamentals report. Cache warm-up only.",
        "derivatives_report": "No derivatives report. Cache warm-up only.",
        "investment_plan": "Hold. Cache warm-up only.",
        "trader_investment_plan": "Hold. Cache warm-up only.",
        "past_context": "",
        "prior_analysis_pack_context": "",
        "investment_debate_state": {
            "history": "Cache warm-up investment debate.",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 0,
        },
        "risk_debate_state": {
            "history": "Cache warm-up risk debate.",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "count": 0,
        },
    }


def iter_warmup_families() -> Iterable[WarmupFamily]:
    instrument_context = build_instrument_context("CACHE-WARMUP")
    state = _warmup_state()
    yield WarmupFamily(
        "market",
        "quick",
        MARKET_SYSTEM_MESSAGE,
        lambda: build_market_user_prompt(
            current_date="2000-01-01",
            instrument_context=instrument_context,
            market_snapshot_context="No snapshot. Cache warm-up only.",
        ),
    )
    yield WarmupFamily(
        "sentiment",
        "quick",
        SENTIMENT_SYSTEM_MESSAGE,
        lambda: build_sentiment_user_prompt(
            ticker="CACHE-WARMUP",
            instrument_context=instrument_context,
            start_date="1999-12-25",
            end_date="2000-01-01",
            news_block="No news. Cache warm-up only.",
            stocktwits_block="No StockTwits. Cache warm-up only.",
            reddit_block="No Reddit. Cache warm-up only.",
        ),
    )
    yield WarmupFamily(
        "derivatives",
        "quick",
        DERIVATIVES_SYSTEM_MESSAGE,
        lambda: build_derivatives_user_prompt(
            current_date="2000-01-01",
            instrument_context=instrument_context,
        ),
    )
    yield WarmupFamily(
        "research_manager",
        "deep",
        RESEARCH_MANAGER_SYSTEM_PROMPT,
        lambda: build_research_manager_user_prompt(state),
    )
    yield WarmupFamily(
        "trader",
        "quick",
        TRADER_SYSTEM_PROMPT,
        lambda: build_trader_user_prompt(state),
    )
    yield WarmupFamily(
        "portfolio_manager",
        "deep",
        PORTFOLIO_MANAGER_SYSTEM_PROMPT,
        lambda: build_portfolio_manager_user_prompt(state),
    )


def build_warmup_messages(family: WarmupFamily) -> list[dict]:
    return [
        {"role": "system", "content": family.system_message},
        {"role": "user", "content": family.user_builder()},
    ]


def _model_for_tier(config: dict, tier: str) -> str:
    return config["deep_think_llm"] if tier == "deep" else config["quick_think_llm"]


def run_warmup(*, dry_run: bool = False, config: dict | None = None) -> None:
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)
    if cfg.get("llm_provider") != "deepseek":
        raise RuntimeError("warm-up supports DeepSeek official API runs only")

    for family in iter_warmup_families():
        model = _model_for_tier(cfg, family.tier)
        messages = build_warmup_messages(family)
        if dry_run:
            print(f"{family.name}: model={model} messages={len(messages)}")
            continue

        callback = RunCostCallback()
        client = create_llm_client(
            provider="deepseek",
            model=model,
            base_url=cfg.get("backend_url"),
            callbacks=[callback],
        )
        llm = client.get_llm()
        llm.invoke(messages)
        totals = callback.totals_by_model()
        counts = next(iter(totals.values()), {})
        hit = counts.get("cache_hit_tokens", 0)
        miss = counts.get("cache_miss_tokens", 0)
        ratio = compute_cache_hit_ratio(hit, miss)
        print(
            f"{family.name}: model={model} "
            f"in_tokens={counts.get('in_tokens', 0)} "
            f"cache_hit_tokens={hit} cache_miss_tokens={miss} "
            f"cache_hit_ratio={ratio}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_warmup(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
