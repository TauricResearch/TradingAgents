"""yfinance-backed ETF tools: profile and top holdings.

Separate from ``y_finance.py`` (which handles stock OHLCV and company
financials) and ``yfinance_news.py`` (which handles news) so each
yfinance feature surface stays small. Covers US ETFs (SPY, QQQ, VOO, ...)
and HK ETFs (2800.HK, 3110.HK, ...).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

import yfinance as yf

from .stockstats_utils import yf_retry


def get_etf_profile(
    ticker: Annotated[str, "ETF ticker symbol, e.g. SPY, 2800.HK"],
) -> str:
    """ETF profile snapshot from yfinance.

    Surfaces ETF-relevant fields from ``Ticker.info`` (AUM, NAV, expense
    ratio, fund family, category) plus, when available, the ``funds_data``
    description, asset-class breakdown, and sector weightings. Any individual
    field can be missing (HK ETFs in particular often lack ``funds_data``)
    and the renderer degrades silently rather than raising.
    """
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        info = yf_retry(lambda: ticker_obj.info) or {}

        fields = [
            ("Name", info.get("longName") or info.get("shortName")),
            ("Quote Type", info.get("quoteType")),
            ("Category", info.get("category")),
            ("Fund Family", info.get("fundFamily")),
            ("Total Assets (AUM)", info.get("totalAssets")),
            ("NAV Price", info.get("navPrice")),
            ("Annual Expense Ratio", info.get("annualReportExpenseRatio")),
            ("Net Expense Ratio", info.get("netExpenseRatio")),
            ("Yield (TTM)", info.get("yield")),
            ("Trailing PE", info.get("trailingPE")),
            ("Beta (3Y)", info.get("beta3Year")),
            ("YTD Return", info.get("ytdReturn")),
            ("3Y Avg Return", info.get("threeYearAverageReturn")),
            ("5Y Avg Return", info.get("fiveYearAverageReturn")),
            ("52 Week High", info.get("fiftyTwoWeekHigh")),
            ("52 Week Low", info.get("fiftyTwoWeekLow")),
            ("Inception Date", info.get("fundInceptionDate")),
        ]

        lines = [
            f"# ETF Profile for {ticker.upper()}",
            "# Source: yfinance",
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]
        for label, value in fields:
            if value is not None and value != "":
                lines.append(f"- **{label}**: {value}")

        # Optional richer fields from funds_data — wrapped in try because not
        # all tickers expose it (HK ETFs frequently do not) and the attribute
        # is "lazy" in yfinance, so reading it can raise on its own.
        try:
            fd = ticker_obj.funds_data
            if fd is not None:
                if getattr(fd, "description", None):
                    desc = str(fd.description).strip()
                    if desc:
                        lines.append("")
                        lines.append("## Strategy")
                        lines.append(desc[:800] + ("…" if len(desc) > 800 else ""))
                ac = getattr(fd, "asset_classes", None)
                if ac:
                    lines.append("")
                    lines.append("## Asset Class Breakdown")
                    for k, v in ac.items():
                        if v:
                            lines.append(f"- {k}: {v:.2%}")
                sw = getattr(fd, "sector_weightings", None)
                if sw:
                    lines.append("")
                    lines.append("## Sector Weightings")
                    for k, v in sw.items():
                        if v:
                            lines.append(f"- {k}: {v:.2%}")
        except Exception:  # noqa: BLE001 — funds_data is opportunistic; never fatal
            pass

        return "\n".join(lines)

    except Exception as e:
        return f"Error retrieving ETF profile for {ticker}: {str(e)}"


def get_etf_holdings(
    ticker: Annotated[str, "ETF ticker symbol, e.g. SPY, 2800.HK"],
    top_n: Annotated[int, "Number of top holdings to return"] = 10,
) -> str:
    """Top-N ETF holdings from yfinance ``funds_data.top_holdings``.

    yfinance returns ~10 rows; ``top_n`` lets the caller crop further.
    When ``funds_data`` is unavailable (HK ETFs, very new listings) we
    return a friendly "no holdings disclosed" string so the analyst can
    move on rather than seeing a stack trace.
    """
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        try:
            fd = ticker_obj.funds_data
        except Exception as exc:  # noqa: BLE001
            return f"yfinance does not expose holdings for {ticker}: {exc}"

        holdings = getattr(fd, "top_holdings", None)
        if holdings is None or (hasattr(holdings, "empty") and holdings.empty):
            return f"No holdings disclosed for {ticker.upper()}"

        top = holdings.head(top_n).copy()
        # Convert decimal weight (0.062) → "6.20%" for analyst readability.
        # Capture the numeric percent values *before* stringifying so the
        # concentration block can compute its metrics from them.
        weights_pct: list[float] = []
        weight_col = next(
            (c for c in top.columns if "weight" in c.lower() or "percent" in c.lower()),
            None,
        )
        if weight_col:
            numeric = top[weight_col].astype(float) * 100
            weights_pct = numeric.tolist()
            top[weight_col] = numeric.round(2).astype(str) + "%"

        header = (
            f"# ETF Holdings for {ticker.upper()}\n"
            "# Source: yfinance funds_data.top_holdings\n"
            f"# Top {len(top)} positions\n"
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )
        from .etf_utils import concentration_summary
        return header + top.to_csv() + concentration_summary(weights_pct)

    except Exception as e:
        return f"Error retrieving ETF holdings for {ticker}: {str(e)}"


def get_top_holding_tickers(
    etf_ticker: str, top_n: int = 3
) -> list[tuple[str, str, float]]:
    """Structured top-N holdings for an ETF: ``[(ticker, name, weight_pct), ...]``.

    The drill-down tool feeds these tuples back through ``route_to_vendor``
    to fetch per-constituent fundamentals and news. Symbol formatting in
    yfinance is inconsistent (``9988.HK`` canonical, ``00939`` bare HK,
    ``HSBA.L`` London cross-listing), so we normalize bare 5-digit numerics
    to ``.HK`` and pass anything else through unchanged.

    Returns ``[]`` rather than raising when ``funds_data`` is unavailable
    so the orchestrator can emit a friendly "no constituents resolved"
    message instead of a stack trace.
    """
    try:
        ticker_obj = yf.Ticker(etf_ticker.upper())
        fd = getattr(ticker_obj, "funds_data", None)
        if fd is None:
            return []
        df = getattr(fd, "top_holdings", None)
        if df is None or (hasattr(df, "empty") and df.empty):
            return []
    except Exception:  # noqa: BLE001
        return []

    out: list[tuple[str, str, float]] = []
    for sym, row in df.head(top_n).iterrows():
        raw = str(sym).strip()
        # Bare 5-digit code (HK convention with leading zeros) → append .HK
        if raw.isdigit() and len(raw) <= 5:
            normalized = f"{raw.zfill(5)}.HK"
        else:
            normalized = raw
        name = str(row.get("Name", raw))
        weight = row.get("Holding Percent", 0.0)
        # yfinance is inconsistent: usually decimal (0.062) but occasionally
        # already percent (6.2). 1.5 is a safe threshold — no single holding
        # in a diversified fund exceeds 150%, and no decimal weight reaches 1.5.
        try:
            value = float(weight)
            weight_pct = value * 100 if value < 1.5 else value
        except (TypeError, ValueError):
            weight_pct = 0.0
        out.append((normalized, name, weight_pct))
    return out
