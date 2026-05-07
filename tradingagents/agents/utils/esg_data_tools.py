"""ESG (Environmental, Social, Governance) data tools for analyst agents."""

from datetime import date, datetime, timedelta
from typing import Annotated, Any

from langchain_core.tools import tool
import pandas as pd
import yfinance as yf

from tradingagents.dataflows.stockstats_utils import yf_retry
from tradingagents.dataflows.yfinance_news import _extract_article_data


def _parse_trade_date(curr_date: str) -> date | None:
    try:
        return datetime.strptime(curr_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _is_historical_date(curr_date: str) -> bool:
    trade_date = _parse_trade_date(curr_date)
    return trade_date is not None and trade_date < date.today()


def _scalar_esg_value(value: Any) -> Any:
    """Convert yfinance ESG row/cell values into a concise scalar when possible."""
    if isinstance(value, pd.Series):
        non_empty = value.dropna()
        if len(non_empty) == 1:
            return non_empty.iloc[0]
        if "Value" in value.index and pd.notna(value["Value"]):
            return value["Value"]
        if len(non_empty) > 1:
            return non_empty.to_dict()
        return "N/A"
    if isinstance(value, pd.DataFrame):
        return value.to_dict()
    return value


@tool
def get_esg_scores(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """Retrieve current ESG scores and sustainability metrics for a company.

    Yahoo Finance does not expose point-in-time historical ESG ratings through
    yfinance. For historical analysis dates, this tool refuses to return current
    ESG scores to avoid look-ahead bias.
    """
    if _is_historical_date(curr_date):
        return (
            f"Point-in-time ESG scores are not available for {ticker} on {curr_date}. "
            "Yahoo Finance only exposes current sustainability scores, so this tool "
            "does not return them for historical analysis dates to avoid look-ahead bias."
        )

    try:
        stock = yf.Ticker(ticker)
        sustainability = stock.sustainability

        if sustainability is None or sustainability.empty:
            return f"No ESG sustainability data available for {ticker}. This may indicate the company is not covered by Yahoo Finance ESG ratings, or the data provider (Sustainalytics) has not assessed this company."

        report = f"ESG Sustainability Scores for {ticker}:\n"
        report += "=" * 50 + "\n\n"

        metrics = [
            ("totalEsg", "Total ESG Score"),
            ("environmentScore", "Environment Score"),
            ("socialScore", "Social Score"),
            ("governanceScore", "Governance Score"),
            ("highestControversy", "Highest Controversy Level"),
            ("peerGroup", "Peer Group"),
        ]

        matched = False
        for key, label in metrics:
            if key in sustainability.index:
                matched = True
                report += f"{label}: {_scalar_esg_value(sustainability.loc[key])}\n"
            elif key in sustainability.columns:
                matched = True
                report += f"{label}: {_scalar_esg_value(sustainability[key])}\n"

        if not matched:
            report += sustainability.to_string()

        report += "\n" + "=" * 50 + "\n"
        report += "Note: Lower ESG scores indicate lower ESG risk. Scores are based on Sustainalytics methodology."
        return report

    except Exception as e:
        return f"Error fetching ESG data for {ticker}: {str(e)}"


@tool
def get_esg_news(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """Retrieve ESG-related news and controversies for a company.

    yfinance returns a latest-news feed rather than a historical archive. The
    tool filters out articles published after ``curr_date`` and skips undated
    articles for historical runs, so old analyses do not consume future news.
    """
    try:
        stock = yf.Ticker(ticker)
        news = yf_retry(lambda: stock.get_news(count=20))

        if news is None or len(news) == 0:
            return f"No recent news available for {ticker}."

        trade_date = _parse_trade_date(curr_date)
        cutoff = datetime.combine(trade_date + timedelta(days=1), datetime.min.time()) if trade_date else None
        historical = _is_historical_date(curr_date)

        esg_keywords = [
            'esg', 'environment', 'sustainability', 'carbon', 'climate',
            'green', 'emissions', 'social', 'diversity', 'governance',
            'board', 'ethics', 'compliance', 'labor', 'worker', 'employee',
            'community', 'controversy', 'scandal', 'investigation', 'regulation'
        ]

        esg_news_items = []
        skipped_future = 0
        skipped_undated = 0
        for item in news:
            article = _extract_article_data(item)
            pub_date = article.get("pub_date")
            if pub_date is not None:
                pub_date = pub_date.replace(tzinfo=None)
                if cutoff and pub_date >= cutoff:
                    skipped_future += 1
                    continue
            elif historical:
                skipped_undated += 1
                continue

            title = article["title"].lower()
            summary = article["summary"].lower()

            if any(keyword in title or keyword in summary for keyword in esg_keywords):
                article_summary = article["summary"] or "No summary available"
                esg_news_items.append({
                    'title': article["title"],
                    'publisher': article["publisher"],
                    'link': article["link"],
                    'summary': article_summary[:200] + '...' if len(article_summary) > 200 else article_summary,
                })

        if len(esg_news_items) == 0:
            suffix = ""
            if skipped_future or skipped_undated:
                suffix = f" Filtered out {skipped_future} future-dated and {skipped_undated} undated article(s) for point-in-time safety."
            return f"No ESG-specific news found for {ticker} up to {curr_date}. General market news may still contain relevant information.{suffix}"

        report = f"ESG-Related News for {ticker} up to {curr_date}:\n"
        report += "=" * 50 + "\n\n"

        for i, item in enumerate(esg_news_items[:10], 1):
            report += f"{i}. {item['title']}\n"
            report += f"   Source: {item['publisher']}\n"
            report += f"   Summary: {item['summary']}\n"
            if item['link']:
                report += f"   Link: {item['link']}\n"
            report += "\n"

        report += "=" * 50 + "\n"
        report += f"Total ESG-related articles found: {len(esg_news_items)}\n"
        if skipped_future or skipped_undated:
            report += f"Filtered out {skipped_future} future-dated and {skipped_undated} undated article(s) for point-in-time safety.\n"

        return report

    except Exception as e:
        return f"Error fetching ESG news for {ticker}: {str(e)}"