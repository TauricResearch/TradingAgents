import json
import logging
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
from langchain_core.messages import HumanMessage
from tradingagents.agents.utils.json_utils import extract_json
from tradingagents.report_paths import get_market_dir
from tradingagents.portfolio.report_store import ReportStore
from tradingagents.dataflows.finnhub import get_company_news

logger = logging.getLogger(__name__)

def load_scan_candidates(scan_date: str) -> list[dict]:
    """Read macro_scan_summary.md for scan_date, extract stocks_to_investigate.
    Falls back to report_store.load_scan() if .md absent."""
    from tradingagents.portfolio.store_factory import create_report_store

    try:
        scan_dir = get_market_dir(scan_date)
        summary_path = scan_dir / "macro_scan_summary.md"
        if summary_path.exists():
            content = summary_path.read_text(encoding="utf-8")
            data = extract_json(content)
            if isinstance(data, dict) and "stocks_to_investigate" in data:
                return data["stocks_to_investigate"]
    except Exception as e:
        logger.warning(f"Error reading macro_scan_summary.md for {scan_date}: {e}")

    try:
        store = create_report_store()
        scan_data = store.load_scan(scan_date)
        if scan_data and isinstance(scan_data, dict) and "stocks_to_investigate" in scan_data:
            return scan_data["stocks_to_investigate"]
    except Exception as e:
        logger.warning(f"Error loading scan from ReportStore for {scan_date}: {e}")

    return []

def fetch_price_trend(ticker: str, start_date: str, end_date: str) -> tuple[float | None, float | None, float | None, float | None, int | None, list[str]]:
    """Download [ticker, SPY] via yf.download().
    Returns (terminal_return, spy_return, mfe_pct, mae_pct, days_to_peak, top_move_dates).
    - mfe_pct: Maximum Favorable Excursion (peak return vs entry)
    - mae_pct: Maximum Adverse Excursion (worst drawdown from entry)
    - days_to_peak: Integer number of days from start_date to Highest_High
    - top_move_dates: up to 3 dates with largest single-day absolute price moves
    Returns (None, None, None, None, None, []) if < 2 trading days or download fails.
    """
    def _local_safe_pct(closes: pd.Series, days_back: int) -> float | None:
        if len(closes) < days_back + 1:
            return None
        base = closes.iloc[-(days_back + 1)]
        current = closes.iloc[-1]
        if base == 0:
            return None
        return (current - base) / base * 100

    try:
        hist = yf.download(
            [ticker, "SPY"],
            start=start_date,
            end=end_date,
            auto_adjust=True,
            progress=False
        )
        if hist.empty or len(hist) < 2:
            return None, None, None, None, None, []

        if isinstance(hist.columns, pd.MultiIndex):
            closes = hist["Close"]
        else:
            closes = hist

        if ticker not in closes.columns or "SPY" not in closes.columns:
             return None, None, None, None, None, []

        stock_closes = closes[ticker].dropna()
        spy_closes = closes["SPY"].dropna()

        if len(stock_closes) < 2 or len(spy_closes) < 2:
            return None, None, None, None, None, []

        # Terminal returns
        terminal_return = _local_safe_pct(stock_closes, len(stock_closes) - 1)
        spy_return = _local_safe_pct(spy_closes, len(spy_closes) - 1)

        # MFE / MAE
        entry_price = stock_closes.iloc[0]
        if entry_price == 0:
            return None, None, None, None, None, []

        peak_price = stock_closes.max()
        worst_price = stock_closes.min()

        mfe_pct = (peak_price - entry_price) / entry_price * 100
        mae_pct = (worst_price - entry_price) / entry_price * 100

        # Days to peak
        start_datetime = stock_closes.index[0]
        peak_datetime = stock_closes.idxmax()
        days_to_peak = (peak_datetime - start_datetime).days

        # Top move dates
        stock_returns = stock_closes.pct_change().dropna()
        abs_returns = stock_returns.abs()
        top_moves = abs_returns.nlargest(3)
        top_move_dates = [d.strftime("%Y-%m-%d") for d in top_moves.index]

        return terminal_return, spy_return, mfe_pct, mae_pct, days_to_peak, top_move_dates

    except Exception as e:
        logger.warning(f"Error fetching price data for {ticker}: {e}")
        return None, None, None, None, None, []

def fetch_news_summary(ticker: str, start_date: str, end_date: str, top_move_dates: list[str], n: int = 5) -> str:
    """Fetch n headlines, weighted toward largest-move dates.
    Strategy: 2 headlines from window start (initial catalyst context),
    3 headlines from dates nearest top_move_dates (outcome context).
    Returns bullet-list string."""

    headlines = []

    # 1. Fetch 2 headlines from the start of the window
    try:
        start_news_md = get_company_news(ticker, start_date, start_date)
        # Assuming get_company_news returns markdown list, extract lines starting with -
        if start_news_md:
            start_lines = [line for line in start_news_md.split('\n') if line.strip().startswith('-')]
            headlines.extend(start_lines[:2])
    except Exception as e:
        logger.warning(f"Failed to fetch start news for {ticker}: {e}")

    # 2. Fetch 3 headlines from top move dates
    try:
        top_news_lines = []
        for date_str in top_move_dates:
            news_md = get_company_news(ticker, date_str, date_str)
            if news_md:
                lines = [line for line in news_md.split('\n') if line.strip().startswith('-')]
                if lines:
                    top_news_lines.append(lines[0]) # Get best headline for each top move date

        headlines.extend(top_news_lines[:3])
    except Exception as e:
        logger.warning(f"Failed to fetch top move news for {ticker}: {e}")

    if not headlines:
        return "No specific headlines found."

    return "\n".join(headlines)

def generate_lesson(llm, candidate: dict, terminal_return: float | None,
                    spy_return: float | None, mfe_pct: float | None,
                    mae_pct: float | None, days_to_peak: int | None,
                    news_summary: str, horizon_days: int) -> dict | None:
    """Invoke quick_think LLM, parse JSON via extract_json(), return lesson dict.
    Returns None on parse failure (logs warning)."""
    if terminal_return is None or spy_return is None:
        return None

    prompt = f"""STOCK SELECTION REVIEW (0 TO {horizon_days} DAYS)
======================
Ticker:       {candidate.get('ticker')} | Sector: {candidate.get('sector')}
Original thesis: {candidate.get('thesis_angle')} — {candidate.get('rationale')}

THE TREND STORY
------------------
Terminal Return: {terminal_return:+.1f}% (SPY Benchmark: {spy_return:+.1f}%)
Optimal Sell Moment (MFE): {mfe_pct:+.1f}% (Reached on Day {days_to_peak})
Deepest Drawdown (MAE): {mae_pct:+.1f}%

TOP HEADLINES
-------------
{news_summary}

Return ONLY a JSON object with the following keys:
- "situation": 1-2 sentences describing the stock pattern/thesis type.
- "screening_advice": 1 sentence on whether the scanner should buy this setup again.
- "exit_advice": 1 sentence defining the optimal exit strategy based on the MFE/MAE (e.g., "Take profits at +20% or tighten trailing stops after 20 days").
- "sentiment": "positive" | "negative" | "neutral"
"""
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        data = extract_json(response.content if hasattr(response, 'content') else response)

        if not data or not isinstance(data, dict):
            logger.warning(f"LLM response parse failure: {response}")
            return None

        # Verify required keys
        if not all(k in data for k in ["situation", "screening_advice", "exit_advice", "sentiment"]):
            logger.warning(f"LLM response missing required keys: {data}")
            return None

        return data
    except Exception as e:
        logger.warning(f"Error generating lesson: {e}")
        return None

def reflect_on_scan(scan_date: str, reflect_date: str, llm, horizon_days: int) -> list[dict]:
    """Top-level: load candidates, fetch data, generate lessons, return list."""
    candidates = load_scan_candidates(scan_date)
    lessons = []

    for cand in candidates:
        ticker = cand.get("ticker")
        if not ticker:
            continue

        terminal_return, spy_return, mfe_pct, mae_pct, days_to_peak, top_move_dates = fetch_price_trend(ticker, scan_date, reflect_date)
        if terminal_return is None:
            continue

        news_summary = fetch_news_summary(ticker, scan_date, reflect_date, top_move_dates)

        lesson_data = generate_lesson(
            llm=llm,
            candidate=cand,
            terminal_return=terminal_return,
            spy_return=spy_return,
            mfe_pct=mfe_pct,
            mae_pct=mae_pct,
            days_to_peak=days_to_peak,
            news_summary=news_summary,
            horizon_days=horizon_days
        )

        if lesson_data:
            alpha = terminal_return - spy_return
            lesson = {
                "ticker": ticker,
                "scan_date": scan_date,
                "reflect_date": reflect_date,
                "horizon_days": horizon_days,
                "terminal_return_pct": round(terminal_return, 2),
                "spy_return_pct": round(spy_return, 2),
                "alpha_pct": round(alpha, 2),
                "mfe_pct": round(mfe_pct, 2) if mfe_pct is not None else None,
                "mae_pct": round(mae_pct, 2) if mae_pct is not None else None,
                "days_to_peak": days_to_peak,
                "news_summary": news_summary,
                "situation": lesson_data["situation"],
                "screening_advice": lesson_data.get("screening_advice", lesson_data.get("advice", "")),
                "exit_advice": lesson_data.get("exit_advice", ""),
                "sentiment": lesson_data["sentiment"],
                "created_at": datetime.now().isoformat()
            }
            lessons.append(lesson)

    return lessons
