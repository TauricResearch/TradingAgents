import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from tradingagents.agents.discovery.indicators import (
    calculate_momentum_score,
    calculate_relative_strength_metrics,
    calculate_support_resistance_metrics,
    calculate_volume_metrics,
)
from tradingagents.agents.discovery.indicators.timeframe import (
    calculate_timeframe_signals,
)
from tradingagents.agents.discovery.quantitative_cache import clear_run_cache
from tradingagents.agents.discovery.quantitative_models import QuantitativeMetrics
from tradingagents.config import QuantitativeWeightsConfig, get_settings

if TYPE_CHECKING:
    from tradingagents.agents.discovery.models import TrendingStock

logger = logging.getLogger(__name__)


def calculate_unified_score(
    momentum: float,
    volume: float,
    rs: float,
    rr: float,
    weights: QuantitativeWeightsConfig,
) -> float:
    score = (
        momentum * weights.momentum_weight
        + volume * weights.volume_weight
        + rs * weights.relative_strength_weight
        + rr * weights.risk_reward_weight
    )
    return max(0.0, min(1.0, score))


def calculate_single_stock_metrics(
    ticker: str,
    curr_date: str,
) -> QuantitativeMetrics | None:
    try:
        settings = get_settings()
        weights = settings.quantitative_weights

        momentum = calculate_momentum_score(ticker, curr_date)
        volume = calculate_volume_metrics(ticker, curr_date)
        rs = calculate_relative_strength_metrics(ticker, curr_date)
        sr = calculate_support_resistance_metrics(ticker, curr_date)

        timeframe = calculate_timeframe_signals(momentum, rs)

        momentum_score = momentum.get("momentum_score", 0.5)
        volume_score = volume.get("volume_score", 0.5)
        rs_score = rs.get("relative_strength_score", 0.5)
        rr_score = sr.get("risk_reward_score", 0.5)

        unified_score = calculate_unified_score(
            momentum=momentum_score,
            volume=volume_score,
            rs=rs_score,
            rr=rr_score,
            weights=weights,
        )

        return QuantitativeMetrics(
            momentum_score=momentum_score,
            volume_score=volume_score,
            relative_strength_score=rs_score,
            risk_reward_score=rr_score,
            rsi=momentum.get("rsi"),
            macd=momentum.get("macd"),
            macd_signal=momentum.get("macd_signal"),
            macd_histogram=momentum.get("macd_histogram"),
            price_vs_sma50=momentum.get("price_vs_sma50"),
            price_vs_sma200=momentum.get("price_vs_sma200"),
            ema10_direction=momentum.get("ema10_direction"),
            volume_ratio=volume.get("volume_ratio"),
            volume_trend=volume.get("volume_trend"),
            dollar_volume=volume.get("dollar_volume"),
            rs_vs_spy_5d=rs.get("rs_vs_spy_5d"),
            rs_vs_spy_20d=rs.get("rs_vs_spy_20d"),
            rs_vs_spy_60d=rs.get("rs_vs_spy_60d"),
            rs_vs_sector=rs.get("rs_vs_sector"),
            sector_etf=rs.get("sector_etf"),
            support_level=sr.get("support_level"),
            resistance_level=sr.get("resistance_level"),
            atr=sr.get("atr"),
            suggested_stop=sr.get("suggested_stop"),
            reward_target=sr.get("reward_target"),
            risk_reward_ratio=sr.get("risk_reward_ratio"),
            timeframe_alignment=timeframe.get("timeframe_alignment"),
            short_term_signal=timeframe.get("short_term_signal"),
            medium_term_signal=timeframe.get("medium_term_signal"),
            long_term_signal=timeframe.get("long_term_signal"),
            signal_strength=timeframe.get("signal_strength"),
            quantitative_score=unified_score,
        )

    except Exception as e:
        logger.warning(
            "Failed to calculate quantitative metrics for %s: %s", ticker, str(e)
        )
        return None


def _normalize_score(score: float, max_score: float) -> float:
    if max_score == 0:
        return 0.0
    return min(1.0, score / max_score)


def enhance_with_quantitative_scores(
    stocks: list["TrendingStock"],
    curr_date: str,
    max_stocks: int = 50,
) -> list["TrendingStock"]:
    if not stocks:
        return []

    settings = get_settings()
    weights = settings.quantitative_weights

    sorted_stocks = sorted(stocks, key=lambda s: s.score, reverse=True)
    stocks_to_process = sorted_stocks[:max_stocks]
    remaining_stocks = sorted_stocks[max_stocks:]

    clear_run_cache()

    results: dict[str, QuantitativeMetrics | None] = {}

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ticker = {
            executor.submit(
                calculate_single_stock_metrics, stock.ticker, curr_date
            ): stock.ticker
            for stock in stocks_to_process
        }

        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                results[ticker] = future.result()
            except Exception as e:
                logger.warning("Quantitative scoring failed for %s: %s", ticker, str(e))
                results[ticker] = None

    max_news_score = max((s.score for s in stocks_to_process), default=1.0) or 1.0

    for stock in stocks_to_process:
        metrics = results.get(stock.ticker)
        stock.quantitative_metrics = metrics

        news_normalized = _normalize_score(stock.score, max_news_score)

        if metrics is not None:
            stock.conviction_score = (
                weights.news_sentiment_weight * news_normalized
                + weights.quantitative_weight * metrics.quantitative_score
            )
        else:
            stock.conviction_score = news_normalized * weights.news_sentiment_weight

    for stock in remaining_stocks:
        stock.quantitative_metrics = None
        stock.conviction_score = None

    enhanced_stocks = sorted(
        stocks_to_process,
        key=lambda s: s.conviction_score if s.conviction_score is not None else 0.0,
        reverse=True,
    )

    clear_run_cache()

    return enhanced_stocks + remaining_stocks
