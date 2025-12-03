import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import DiscoveryResult, TrendingStock


def save_discovery_result(
    result: DiscoveryResult,
    base_path: Optional[Path] = None,
) -> Path:
    if base_path is None:
        base_path = Path("results")

    timestamp = result.completed_at or result.started_at
    date_str = timestamp.strftime("%Y-%m-%d")
    time_str = timestamp.strftime("%H-%M-%S")

    result_dir = base_path / "discovery" / date_str / time_str
    result_dir.mkdir(parents=True, exist_ok=True)

    json_path = result_dir / "discovery_result.json"
    with open(json_path, "w") as f:
        json.dump(result.to_dict(), f, indent=2)

    md_path = result_dir / "discovery_summary.md"
    markdown_content = generate_markdown_summary(result)
    with open(md_path, "w") as f:
        f.write(markdown_content)

    return result_dir


def generate_markdown_summary(result: DiscoveryResult) -> str:
    lines = []

    lines.append("# Discovery Results")
    lines.append("")

    timestamp = result.completed_at or result.started_at
    lines.append(f"**Timestamp:** {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Lookback Period:** {result.request.lookback_period}")

    filters = _format_filters(result)
    lines.append(f"**Filters:** {filters}")
    lines.append(f"**Total Stocks Found:** {len(result.trending_stocks)}")
    lines.append("")

    lines.append("## Trending Stocks")
    lines.append("")
    lines.append("| Rank | Ticker | Company | Score | Mentions | Event |")
    lines.append("|------|--------|---------|-------|----------|-------|")

    for rank, stock in enumerate(result.trending_stocks, 1):
        lines.append(
            f"| {rank} | {stock.ticker} | {stock.company_name} | "
            f"{stock.score:.2f} | {stock.mention_count} | {stock.event_type.value} |"
        )

    lines.append("")

    lines.append("## Top 3 Detailed Analysis")
    lines.append("")

    top_stocks = result.trending_stocks[:3]
    for rank, stock in enumerate(top_stocks, 1):
        lines.extend(_format_stock_detail(rank, stock))

    return "\n".join(lines)


def _format_filters(result: DiscoveryResult) -> str:
    filter_parts = []

    if result.request.sector_filter:
        sector_values = [s.value for s in result.request.sector_filter]
        filter_parts.append(f"sector={','.join(sector_values)}")

    if result.request.event_filter:
        event_values = [e.value for e in result.request.event_filter]
        filter_parts.append(f"event={','.join(event_values)}")

    if filter_parts:
        return " ".join(filter_parts)
    return "None"


def _format_stock_detail(rank: int, stock: TrendingStock) -> list:
    lines = []

    lines.append(f"### {rank}. {stock.ticker} - {stock.company_name}")
    lines.append(f"- **Score:** {stock.score:.2f}")

    sentiment_label = _get_sentiment_label(stock.sentiment)
    lines.append(f"- **Sentiment:** {stock.sentiment:.2f} ({sentiment_label})")
    lines.append(f"- **Sector:** {stock.sector.value}")
    lines.append(f"- **Event Type:** {stock.event_type.value}")
    lines.append(f"- **Mentions:** {stock.mention_count}")
    lines.append("")

    lines.append("**News Summary:**")
    lines.append(stock.news_summary)
    lines.append("")

    if stock.source_articles:
        lines.append("**Top Sources:**")
        for article in stock.source_articles[:3]:
            lines.append(f"- [{article.title}] - {article.source}")
        lines.append("")

    return lines


def _get_sentiment_label(sentiment: float) -> str:
    if sentiment > 0.3:
        return "positive"
    elif sentiment < -0.3:
        return "negative"
    return "neutral"
