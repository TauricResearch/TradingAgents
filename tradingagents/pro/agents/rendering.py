"""Render a MarketSnapshot slice into a prompt block + its evidence trail.

The same pass that formats data for the LLM also produces the DataRefs and
SourceAttributions that will be attached to the agent's evidence (ADR-0015):
the citation trail is what the agent was shown, by construction — an agent
cannot cite data it never saw, and code (not the model) owns attribution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tradingagents.contracts import (
    DataRef,
    MarketSnapshot,
    MetricReading,
    SourceAttribution,
    SourceType,
)
from tradingagents.pro.agents.specs import AgentSpec

# Source-id prefix -> provenance category for attribution records.
_SOURCE_TYPES = (
    ("fred", SourceType.MACRO_RELEASE),
    ("coinmetrics", SourceType.ONCHAIN),
    ("blockchain_com", SourceType.ONCHAIN),
    ("fear_greed", SourceType.SOCIAL),
    ("binance", SourceType.MARKET_DATA),
    ("yfinance", SourceType.MARKET_DATA),
    ("gold_cross_asset", SourceType.MARKET_DATA),
    ("risk_engine", SourceType.MODEL),
    ("quant_engine", SourceType.MODEL),
    ("rl_advisor", SourceType.MODEL),
)

SNAPSHOT_SOURCE_ID = "snapshot"
INDICATOR_SOURCE_ID = "indicator_engine"
NEWS_SOURCE_PREFIX = "news"


def _source_type_for(source_id: str) -> SourceType:
    for prefix, source_type in _SOURCE_TYPES:
        if source_id.startswith(prefix):
            return source_type
    return SourceType.MARKET_DATA


@dataclass
class RenderedContext:
    """Prompt text plus the exact citation trail for what it contains."""

    text: str = ""
    data_refs: list[DataRef] = field(default_factory=list)
    sources: dict[str, SourceAttribution] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.data_refs

    def has_any(self, names: tuple[str, ...]) -> bool:
        """True if any named input was rendered (multi-line indicators match
        by prefix: primary 'MACD' matches ref 'MACD.macd')."""
        rendered = {r.name for r in self.data_refs}
        prefixes = {n.split(".")[0] for n in rendered}
        return any(n in rendered or n in prefixes for n in names)

    def add_source(self, source_id: str, name: str, source_type: SourceType | None = None):
        if source_id not in self.sources:
            self.sources[source_id] = SourceAttribution(
                id=source_id,
                type=source_type or _source_type_for(source_id),
                name=name,
            )


def render_context(
    snapshot: MarketSnapshot,
    spec: AgentSpec,
    extra_metrics: dict[str, MetricReading] | None = None,
) -> RenderedContext:
    """Build the deterministic data block one agent is allowed to see.

    ``extra_metrics`` carries pipeline-computed values (risk engine, quant
    features) that aren't part of the snapshot itself.
    """
    ctx = RenderedContext()
    lines: list[str] = []
    extras = extra_metrics or {}

    # --- indicators ---------------------------------------------------------
    for name in spec.indicators:
        readings = [
            r
            for r in snapshot.indicators
            if r.name == name and (spec.all_timeframes or r.timeframe == spec.timeframe)
        ]
        if not readings:
            ctx.missing.append(f"indicator:{name}")
            continue
        ctx.add_source(INDICATOR_SOURCE_ID, "Deterministic indicator engine",
                       SourceType.INDICATOR)
        for reading in readings:
            parts = ", ".join(f"{k}={v:.4f}" for k, v in reading.value.items())
            lines.append(f"[{reading.timeframe.value}] {reading.name}: {parts}")
            for key, value in reading.value.items():
                ref_name = reading.name if key == "value" else f"{reading.name}.{key}"
                ctx.data_refs.append(
                    DataRef(
                        name=ref_name,
                        value=value,
                        timeframe=reading.timeframe,
                        source=INDICATOR_SOURCE_ID,
                    )
                )

    # --- metrics (snapshot macro + onchain + pipeline extras) ---------------
    by_name: dict[str, MetricReading] = {m.name: m for m in [*snapshot.macro, *snapshot.onchain]}
    by_name.update(extras)
    for name in spec.metrics:
        metric = by_name.get(name)
        if metric is None:
            ctx.missing.append(f"metric:{name}")
            continue
        source_id = metric.source or SNAPSHOT_SOURCE_ID
        ctx.add_source(source_id, source_id.replace("_", " "))
        unit = f" {metric.unit}" if metric.unit else ""
        lines.append(f"{metric.name}: {metric.value:.6g}{unit}")
        ctx.data_refs.append(
            DataRef(name=metric.name, value=metric.value, source=source_id, as_of=metric.as_of)
        )

    # --- bars ----------------------------------------------------------------
    if spec.include_bars:
        bars = [
            b
            for b in snapshot.bars
            if spec.all_timeframes or b.timeframe == spec.timeframe
        ][-spec.include_bars :]
        if bars:
            ctx.add_source(SNAPSHOT_SOURCE_ID, "Market snapshot bars",
                           SourceType.MARKET_DATA)
            lines.append(f"Recent {bars[0].timeframe.value} bars (oldest first):")
            lines.append("start | open | high | low | close | volume")
            for b in bars:
                lines.append(
                    f"{b.start:%Y-%m-%d %H:%M} | {b.open:.4g} | {b.high:.4g} | "
                    f"{b.low:.4g} | {b.close:.4g} | {b.volume:.4g}"
                )
            ctx.data_refs.append(
                DataRef(
                    name="LAST_CLOSE",
                    value=bars[-1].close,
                    timeframe=bars[-1].timeframe,
                    source=SNAPSHOT_SOURCE_ID,
                )
            )
            ctx.data_refs.append(
                DataRef(name="BARS_SHOWN", value=len(bars), source=SNAPSHOT_SOURCE_ID)
            )
        else:
            ctx.missing.append("bars")

    # --- quote / session ------------------------------------------------------
    if spec.include_quote:
        if snapshot.quote is not None:
            q = snapshot.quote
            ctx.add_source(SNAPSHOT_SOURCE_ID, "Market snapshot bars",
                           SourceType.MARKET_DATA)
            lines.append(f"Quote: bid={q.bid} ask={q.ask} last={q.last}")
            ctx.data_refs.append(DataRef(name="LAST_PRICE", value=q.last,
                                         source=SNAPSHOT_SOURCE_ID, as_of=q.ts))
        else:
            ctx.missing.append("quote")
    if spec.include_session and snapshot.session is not None:
        ctx.add_source(SNAPSHOT_SOURCE_ID, "Market snapshot bars", SourceType.MARKET_DATA)
        lines.append(f"Trading session: {snapshot.session.value}")
        ctx.data_refs.append(
            DataRef(name="SESSION", value=snapshot.session.value, source=SNAPSHOT_SOURCE_ID)
        )

    # --- news ------------------------------------------------------------------
    if spec.include_news:
        items = snapshot.news[-spec.include_news :]
        if items:
            lines.append("Recent news items:")
            for i, item in enumerate(items, 1):
                source_id = f"{NEWS_SOURCE_PREFIX}:{item.source}"
                ctx.add_source(source_id, item.source, SourceType.NEWS)
                published = f" ({item.published_at:%Y-%m-%d})" if item.published_at else ""
                lines.append(f"{i}. [{item.source}]{published} {item.headline}")
                if item.summary:
                    lines.append(f"   {item.summary}")
                ctx.data_refs.append(
                    DataRef(
                        name=f"NEWS_{i}",
                        value=item.headline,
                        source=source_id,
                        as_of=item.published_at,
                    )
                )
        else:
            ctx.missing.append("news")

    ctx.text = "\n".join(lines)
    return ctx
