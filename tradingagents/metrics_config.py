"""Schema for configurable report metrics.

Each key maps to a report section/metric that can be toggled on or off.
When a metric is False, it is omitted from the generated report output.
"""

from typing_extensions import TypedDict


class AnalystMetrics(TypedDict, total=False):
    market_report: bool
    sentiment_report: bool
    news_report: bool
    fundamentals_report: bool


class ResearchMetrics(TypedDict, total=False):
    bull_history: bool
    bear_history: bool
    judge_decision: bool


class TradingMetrics(TypedDict, total=False):
    trader_investment_plan: bool


class RiskMetrics(TypedDict, total=False):
    aggressive_history: bool
    conservative_history: bool
    neutral_history: bool


class PortfolioMetrics(TypedDict, total=False):
    final_trade_decision: bool


class MetricsConfig(TypedDict, total=False):
    analysts: AnalystMetrics
    research: ResearchMetrics
    trading: TradingMetrics
    risk: RiskMetrics
    portfolio: PortfolioMetrics


# All metrics enabled by default
DEFAULT_METRICS_CONFIG: MetricsConfig = {
    "analysts": {
        "market_report": True,
        "sentiment_report": True,
        "news_report": True,
        "fundamentals_report": True,
    },
    "research": {
        "bull_history": True,
        "bear_history": True,
        "judge_decision": True,
    },
    "trading": {
        "trader_investment_plan": True,
    },
    "risk": {
        "aggressive_history": True,
        "conservative_history": True,
        "neutral_history": True,
    },
    "portfolio": {
        "final_trade_decision": True,
    },
}


def is_metric_enabled(config: MetricsConfig, section: str, metric: str) -> bool:
    """Check if a specific metric is enabled in the config.

    Missing sections or metrics default to True (enabled).
    """
    section_cfg = config.get(section, {})
    return section_cfg.get(metric, True)


def list_all_metrics() -> list[str]:
    """Return all available metric keys as 'section.metric' strings."""
    return [
        f"{section}.{metric}"
        for section, metrics in DEFAULT_METRICS_CONFIG.items()
        for metric in metrics
    ]


def parse_metrics_flag(flag: str) -> MetricsConfig:
    """Parse a --metrics flag value into a MetricsConfig.

    Format: comma-separated 'section.metric' items.
    Only the listed metrics are enabled; all others are disabled.

    Example: "analysts.market_report,risk.aggressive_history"

    Raises ValueError for unknown metric keys.
    """
    import copy

    valid = set(list_all_metrics())
    enabled = set()
    for item in flag.split(","):
        item = item.strip()
        if not item:
            continue
        if item not in valid:
            raise ValueError(
                f"Unknown metric '{item}'. Available: {', '.join(sorted(valid))}"
            )
        enabled.add(item)

    config: MetricsConfig = copy.deepcopy(DEFAULT_METRICS_CONFIG)
    for section, metrics in config.items():
        for metric in metrics:
            metrics[metric] = f"{section}.{metric}" in enabled
    return config
