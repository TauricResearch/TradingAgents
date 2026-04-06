"""Typed discovery configuration — single source of truth for all discovery consumers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class FilterConfig:
    """Filter-stage settings (from discovery.filters.*)."""

    min_average_volume: int = 500_000
    volume_lookback_days: int = 10
    filter_same_day_movers: bool = True
    intraday_movement_threshold: float = 10.0
    filter_recent_movers: bool = True
    recent_movement_lookback_days: int = 7
    recent_movement_threshold: float = 10.0
    recent_mover_action: str = "filter"
    # Volume / compression detection
    volume_cache_key: str = "default"
    min_market_cap: int = 0
    compression_atr_pct_max: float = 2.0
    compression_bb_width_max: float = 6.0
    compression_min_volume_ratio: float = 1.3
    # Fundamental Risk Filters
    min_z_score: float = 1.81  # Default below 1.81 indicates distress
    min_f_score: int = 4  # Default below 4 is poor
    filter_fundamental_risk: bool = True


@dataclass
class EnrichmentConfig:
    """Enrichment-stage settings (from discovery.enrichment.*)."""

    batch_news_vendor: str = "google"
    batch_news_batch_size: int = 150
    news_lookback_days: float = 0.5
    context_max_snippets: int = 2
    context_snippet_max_chars: int = 140
    earnings_lookforward_days: int = 30


@dataclass
class RankerConfig:
    """Ranker settings (from discovery root level)."""

    max_candidates_to_analyze: int = 200
    analyze_all_candidates: bool = False
    final_recommendations: int = 15
    min_score_threshold: int = 55
    return_target_pct: float = 5.0
    holding_period_days: str = "1-7"
    truncate_ranking_context: bool = False
    max_news_chars: int = 500
    max_insider_chars: int = 300
    max_recommendations_chars: int = 300


@dataclass
class ChartConfig:
    """Console price chart settings (from discovery root level)."""

    enabled: bool = True
    library: str = "plotille"
    windows: List[str] = field(default_factory=lambda: ["1d", "7d", "1m", "6m", "1y"])
    lookback_days: int = 30
    width: int = 60
    height: int = 12
    max_tickers: int = 10
    show_movement_stats: bool = True


@dataclass
class LoggingConfig:
    """Tool execution logging settings (from discovery root level)."""

    log_tool_calls: bool = True
    log_tool_calls_console: bool = False
    log_prompts_console: bool = False  # Show LLM prompts in console (always saved to log file)
    tool_log_max_chars: int = 10_000
    tool_log_exclude: List[str] = field(default_factory=lambda: ["validate_ticker"])


@dataclass
class DiscoveryConfig:
    """
    Consolidated discovery configuration.

    All defaults match ``default_config.py``.  Consumers should create an
    instance via ``DiscoveryConfig.from_config(raw_config)`` rather than
    reaching into the raw dict themselves.
    """

    # Nested configs
    filters: FilterConfig = field(default_factory=FilterConfig)
    enrichment: EnrichmentConfig = field(default_factory=EnrichmentConfig)
    ranker: RankerConfig = field(default_factory=RankerConfig)
    charts: ChartConfig = field(default_factory=ChartConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Flat settings at discovery root level
    deep_dive_max_workers: int = 1
    discovery_mode: str = "hybrid"

    @classmethod
    def from_config(cls, raw_config: Dict[str, Any]) -> DiscoveryConfig:
        """Build a ``DiscoveryConfig`` from the raw application config dict."""
        disc = raw_config.get("discovery", {})

        # Default instances — used to read fallback values for fields that
        # use default_factory (which aren't available as class-level attrs).
        _fd = FilterConfig()
        _ed = EnrichmentConfig()
        _rd = RankerConfig()
        _cd = ChartConfig()
        _ld = LoggingConfig()

        # Filters — nested under "filters" key, fallback to root for old configs
        f = disc.get("filters", disc)
        filters = FilterConfig(
            min_average_volume=f.get("min_average_volume", _fd.min_average_volume),
            volume_lookback_days=f.get("volume_lookback_days", _fd.volume_lookback_days),
            filter_same_day_movers=f.get("filter_same_day_movers", _fd.filter_same_day_movers),
            intraday_movement_threshold=f.get(
                "intraday_movement_threshold", _fd.intraday_movement_threshold
            ),
            filter_recent_movers=f.get("filter_recent_movers", _fd.filter_recent_movers),
            recent_movement_lookback_days=f.get(
                "recent_movement_lookback_days", _fd.recent_movement_lookback_days
            ),
            recent_movement_threshold=f.get(
                "recent_movement_threshold", _fd.recent_movement_threshold
            ),
            recent_mover_action=f.get("recent_mover_action", _fd.recent_mover_action),
            volume_cache_key=f.get("volume_cache_key", _fd.volume_cache_key),
            min_market_cap=f.get("min_market_cap", _fd.min_market_cap),
            compression_atr_pct_max=f.get("compression_atr_pct_max", _fd.compression_atr_pct_max),
            compression_bb_width_max=f.get(
                "compression_bb_width_max", _fd.compression_bb_width_max
            ),
            compression_min_volume_ratio=f.get(
                "compression_min_volume_ratio", _fd.compression_min_volume_ratio
            ),
            min_z_score=f.get("min_z_score", _fd.min_z_score),
            min_f_score=f.get("min_f_score", _fd.min_f_score),
            filter_fundamental_risk=f.get("filter_fundamental_risk", _fd.filter_fundamental_risk),
        )

        # Enrichment — nested under "enrichment" key, fallback to root
        e = disc.get("enrichment", disc)
        enrichment = EnrichmentConfig(
            batch_news_vendor=e.get("batch_news_vendor", _ed.batch_news_vendor),
            batch_news_batch_size=e.get("batch_news_batch_size", _ed.batch_news_batch_size),
            news_lookback_days=e.get("news_lookback_days", _ed.news_lookback_days),
            context_max_snippets=e.get("context_max_snippets", _ed.context_max_snippets),
            context_snippet_max_chars=e.get(
                "context_snippet_max_chars", _ed.context_snippet_max_chars
            ),
            earnings_lookforward_days=e.get(
                "earnings_lookforward_days", _ed.earnings_lookforward_days
            ),
        )

        # Ranker
        ranker = RankerConfig(
            max_candidates_to_analyze=disc.get(
                "max_candidates_to_analyze", _rd.max_candidates_to_analyze
            ),
            analyze_all_candidates=disc.get("analyze_all_candidates", _rd.analyze_all_candidates),
            final_recommendations=disc.get("final_recommendations", _rd.final_recommendations),
            min_score_threshold=disc.get("min_score_threshold", _rd.min_score_threshold),
            return_target_pct=disc.get("return_target_pct", _rd.return_target_pct),
            holding_period_days=disc.get("holding_period_days", _rd.holding_period_days),
            truncate_ranking_context=disc.get(
                "truncate_ranking_context", _rd.truncate_ranking_context
            ),
            max_news_chars=disc.get("max_news_chars", _rd.max_news_chars),
            max_insider_chars=disc.get("max_insider_chars", _rd.max_insider_chars),
            max_recommendations_chars=disc.get(
                "max_recommendations_chars", _rd.max_recommendations_chars
            ),
        )

        # Charts — keys prefixed with "price_chart_" at discovery root level
        charts = ChartConfig(
            enabled=disc.get("console_price_charts", _cd.enabled),
            library=disc.get("price_chart_library", _cd.library),
            windows=disc.get("price_chart_windows", _cd.windows),
            lookback_days=disc.get("price_chart_lookback_days", _cd.lookback_days),
            width=disc.get("price_chart_width", _cd.width),
            height=disc.get("price_chart_height", _cd.height),
            max_tickers=disc.get("price_chart_max_tickers", _cd.max_tickers),
            show_movement_stats=disc.get(
                "price_chart_show_movement_stats", _cd.show_movement_stats
            ),
        )

        # Logging
        logging_cfg = LoggingConfig(
            log_tool_calls=disc.get("log_tool_calls", _ld.log_tool_calls),
            log_tool_calls_console=disc.get("log_tool_calls_console", _ld.log_tool_calls_console),
            log_prompts_console=disc.get("log_prompts_console", _ld.log_prompts_console),
            tool_log_max_chars=disc.get("tool_log_max_chars", _ld.tool_log_max_chars),
            tool_log_exclude=disc.get("tool_log_exclude", _ld.tool_log_exclude),
        )

        return cls(
            filters=filters,
            enrichment=enrichment,
            ranker=ranker,
            charts=charts,
            logging=logging_cfg,
            deep_dive_max_workers=disc.get("deep_dive_max_workers", 1),
            discovery_mode=disc.get("discovery_mode", "hybrid"),
        )
