from __future__ import annotations

from datetime import datetime, timedelta
import logging
import math
import re
import time
from types import SimpleNamespace

import pandas as pd

try:
    import akshare as ak
except ImportError:  # pragma: no cover - covered indirectly via patched tests
    ak = SimpleNamespace()

from .a_share_common import (
    format_date_for_api,
    get_ashare_exchange,
    get_date_range,
    get_previous_trade_date,
    normalize_ashare_symbol,
    parse_date_column,
    to_exchange_prefixed_symbol,
    to_plain_symbol,
    to_yfinance_symbol,
)
from .config import get_config
from .stockstats_utils import load_ohlcv
from .y_finance import get_stock_stats_indicators_window

logger = logging.getLogger(__name__)

IMPORTANT_FINANCIAL_METRICS = [
    "归母净利润",
    "扣非净利润",
    "营业总收入",
    "基本每股收益",
    "每股净资产",
    "每股经营性现金流",
    "销售毛利率",
    "净资产收益率",
    "资产负债率",
]

BALANCE_SHEET_COLUMNS = [
    "REPORT_DATE_NAME",
    "TOTAL_ASSETS",
    "TOTAL_LIABILITIES",
    "TOTAL_PARENT_EQUITY",
    "MONETARYFUNDS",
    "INVENTORY",
    "ACCOUNTS_RECE",
    "GOODWILL",
]

CASHFLOW_COLUMNS = [
    "REPORT_DATE_NAME",
    "NETCASH_OPERATE",
    "NETCASH_INVEST",
    "NETCASH_FINANCE",
    "CCE_ADD",
    "PAY_STAFF_CASH",
    "PAY_ALL_TAX",
]

INCOME_COLUMNS = [
    "REPORT_DATE_NAME",
    "TOTAL_OPERATE_INCOME",
    "OPERATE_PROFIT",
    "TOTAL_PROFIT",
    "NETPROFIT",
    "PARENT_NETPROFIT",
    "DEDUCT_PARENT_NETPROFIT",
    "BASIC_EPS",
]

INDICATOR_DESCRIPTIONS = {
    "close_50_sma": "50日简单移动平均线，用于识别中期趋势和动态支撑阻力。",
    "close_200_sma": "200日简单移动平均线，用于识别长期趋势和牛熊切换。",
    "close_10_ema": "10日指数移动平均线，用于捕捉更快的短期趋势变化。",
    "macd": "MACD 指标，用于识别趋势变化与动量。",
    "macds": "MACD 信号线，用于配合 MACD 判断金叉死叉。",
    "macdh": "MACD 柱状图，用于衡量动量强弱变化。",
    "rsi": "RSI 指标，用于识别超买超卖与背离。",
    "boll": "布林带中轨，衡量价格相对中枢。",
    "boll_ub": "布林带上轨，衡量价格上沿压力。",
    "boll_lb": "布林带下轨，衡量价格下沿支撑。",
    "atr": "ATR 波动率指标，用于仓位和止损参考。",
    "vwma": "成交量加权均线，用于结合量价确认趋势。",
    "mfi": "资金流量指标，用于衡量量价驱动的超买超卖。",
}

EVENT_TAG_RULES = [
    ("shareholder_change", ("减持", "增持", "持股变动", "股东变动", "权益变动")),
    ("buyback", ("回购", "回购股份")),
    ("lockup", ("解禁", "限售股", "限售股份上市流通")),
    ("earnings_preview", ("业绩预告", "业绩快报", "业绩修正", "预盈", "预亏")),
    ("financing", ("定增", "配股", "可转债", "募资", "融资", "发行股份")),
    ("pledge", ("质押", "解除质押")),
    ("litigation", ("诉讼", "仲裁", "立案", "处罚", "警示函")),
    ("risk_warning", ("风险提示", "ST", "*ST", "退市", "终止上市", "异常波动")),
    ("contract_order", ("中标", "合同", "订单", "框架协议")),
    ("restructuring", ("重组", "收购", "并购", "资产出售", "资产购买")),
    ("suspension", ("停牌", "复牌")),
    ("dividend", ("分红", "派息", "权益分派")),
]

POSITIVE_EVENT_TAGS = {"buyback", "contract_order", "earnings_preview", "dividend"}
NEGATIVE_EVENT_TAGS = {"risk_warning", "litigation", "pledge", "lockup"}
MIXED_EVENT_TAGS = {"shareholder_change", "financing", "restructuring", "suspension"}


def _call_akshare_api(func, *args, retries: int = 2, retry_delay: float = 0.5, **kwargs):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries:
                time.sleep(retry_delay * (attempt + 1))
                continue
            raise last_exc


def _safe_truncate(text: str, limit: int = 160) -> str:
    clean = " ".join(str(text).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def _find_first_numeric_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for column in candidates:
        if column in df.columns:
            values = pd.to_numeric(df[column], errors="coerce").dropna()
            if not values.empty:
                return column
    return None


def _describe_series_trend(values: pd.Series, label: str, positive_direction: str, negative_direction: str) -> str | None:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return None

    latest = float(numeric.iloc[0])
    summary = [f"latest {label}={latest:.2f}"]
    if len(numeric) >= 2:
        delta = float(numeric.iloc[0] - numeric.iloc[1])
        direction = positive_direction if delta > 0 else negative_direction if delta < 0 else "flat"
        summary.append(f"1-step delta={delta:.2f} ({direction})")
    if len(numeric) >= 3:
        mean_value = float(numeric.mean())
        summary.append(f"recent mean={mean_value:.2f}")

    positive_count = int((numeric > 0).sum())
    negative_count = int((numeric < 0).sum())
    if positive_count or negative_count:
        summary.append(f"sign distribution +:{positive_count} / -:{negative_count}")
    return ", ".join(summary)


def _classify_event_tag(text: str) -> str:
    title = str(text or "")
    for tag, keywords in EVENT_TAG_RULES:
        if any(keyword in title for keyword in keywords):
            return tag
    return "other"


def _tag_bias(tag: str, title: str) -> str:
    text = str(title or "")
    if tag == "shareholder_change":
        if "增持" in text:
            return "positive"
        if "减持" in text:
            return "negative"
        return "mixed"
    if tag == "earnings_preview":
        if any(keyword in text for keyword in ("预增", "扭亏", "增长", "上升", "预盈")):
            return "positive"
        if any(keyword in text for keyword in ("预亏", "下滑", "下降", "亏损")):
            return "negative"
        return "mixed"
    if tag in POSITIVE_EVENT_TAGS:
        return "positive"
    if tag in NEGATIVE_EVENT_TAGS:
        return "negative"
    if tag in MIXED_EVENT_TAGS:
        return "mixed"
    return "neutral"


def _format_table(df: pd.DataFrame, title: str, rows: int = 10) -> str:
    if df.empty:
        return f"{title}\n\n暂无数据。"
    return f"{title}\n\n{df.head(rows).to_csv(index=False)}"


def _extract_text_values(df: pd.DataFrame, candidates: list[str], limit: int = 10) -> list[str]:
    values: list[str] = []
    for column in candidates:
        if column not in df.columns:
            continue
        for value in df[column].dropna().astype(str):
            clean = value.strip()
            if clean and clean not in values:
                values.append(clean)
            if len(values) >= limit:
                return values
    return values


def _expand_delimited_values(values: list[str], limit: int = 10) -> list[str]:
    expanded: list[str] = []
    for value in values:
        for item in re.split(r"[;,，、/|]", value):
            clean = item.strip()
            if clean and clean not in expanded:
                expanded.append(clean)
            if len(expanded) >= limit:
                return expanded
    return expanded


def _round_numeric_frame(df: pd.DataFrame) -> pd.DataFrame:
    rounded = df.copy()
    for column in rounded.columns:
        if pd.api.types.is_numeric_dtype(rounded[column]):
            rounded[column] = rounded[column].round(4)
    return rounded


def _compute_window_return(df: pd.DataFrame, look_back_days: int, price_col: str = "Close") -> tuple[float | None, str | None]:
    if df.empty or price_col not in df.columns:
        return None, None
    working = df.copy()
    working["Date"] = pd.to_datetime(working["Date"], errors="coerce")
    working = working.dropna(subset=["Date", price_col]).sort_values("Date")
    if working.empty:
        return None, None
    latest_date = working["Date"].iloc[-1]
    start_cutoff = latest_date - pd.Timedelta(days=look_back_days)
    window = working[working["Date"] >= start_cutoff]
    if len(window) < 2:
        window = working.tail(min(len(working), look_back_days + 1))
    if len(window) < 2:
        return None, latest_date.strftime("%Y-%m-%d")
    start_price = float(window[price_col].iloc[0])
    end_price = float(window[price_col].iloc[-1])
    if start_price == 0:
        return None, latest_date.strftime("%Y-%m-%d")
    return (end_price - start_price) / start_price, latest_date.strftime("%Y-%m-%d")


def _resolve_a_share_benchmark(symbol: str) -> str:
    config = get_config()
    explicit = config.get("benchmark_ticker")
    if explicit:
        return explicit
    benchmark_map = config.get("benchmark_map", {})
    normalized = normalize_ashare_symbol(symbol)
    for suffix, benchmark in benchmark_map.items():
        if suffix and normalized.endswith(suffix.upper()):
            return benchmark
    return benchmark_map.get(".SH", "000300.SS")


def _filter_report_rows(df: pd.DataFrame, curr_date: str | None) -> pd.DataFrame:
    if df.empty or not curr_date:
        return df
    for column in ("REPORT_DATE", "NOTICE_DATE", "报告日期", "公告日期"):
        if column in df.columns:
            filtered = df.copy()
            filtered[column] = parse_date_column(filtered[column])
            cutoff = pd.Timestamp(curr_date)
            filtered = filtered[filtered[column] <= cutoff]
            return filtered.sort_values(column, ascending=False)
    return df


def _select_statement_columns(df: pd.DataFrame, preferred_columns: list[str]) -> pd.DataFrame:
    available = [column for column in preferred_columns if column in df.columns]
    if not available:
        return df.head(8)
    return df.loc[:, available].head(8)


def _latest_abstract_snapshot(abstract_df: pd.DataFrame, curr_date: str | None) -> pd.DataFrame:
    report_columns = [column for column in abstract_df.columns if str(column).isdigit()]
    if not report_columns:
        return pd.DataFrame()

    parsed_dates = {
        column: pd.to_datetime(str(column), format="%Y%m%d", errors="coerce")
        for column in report_columns
    }
    if curr_date:
        cutoff = pd.Timestamp(curr_date)
        eligible = [column for column, value in parsed_dates.items() if pd.notna(value) and value <= cutoff]
    else:
        eligible = report_columns

    if not eligible:
        eligible = report_columns

    latest_column = max(eligible, key=lambda column: parsed_dates[column])
    filtered = abstract_df[abstract_df["指标"].isin(IMPORTANT_FINANCIAL_METRICS)][["指标", latest_column]].copy()
    filtered.columns = ["指标", latest_column]
    return filtered


def _standardize_hist_df(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    renamed = df.rename(
        columns={
            "日期": "Date",
            "date": "Date",
            "开盘": "Open",
            "open": "Open",
            "最高": "High",
            "high": "High",
            "最低": "Low",
            "low": "Low",
            "收盘": "Close",
            "close": "Close",
            "成交量": "Volume",
            "volume": "Volume",
            "成交额": "Amount",
            "amount": "Amount",
            "振幅": "Amplitude",
            "涨跌幅": "PctChange",
            "涨跌额": "PriceChange",
            "换手率": "TurnoverPct",
        }
    ).copy()
    renamed["Date"] = pd.to_datetime(renamed["Date"], errors="coerce")
    renamed = renamed.dropna(subset=["Date"]).sort_values("Date")
    if "Volume" not in renamed.columns:
        renamed["Volume"] = pd.NA
    if "PctChange" not in renamed.columns:
        renamed["PctChange"] = renamed["Close"].pct_change() * 100
    if "PriceChange" not in renamed.columns:
        renamed["PriceChange"] = renamed["Close"].diff()
    renamed["Ticker"] = normalize_ashare_symbol(symbol)
    preferred = [
        "Date", "Ticker", "Open", "High", "Low", "Close", "Volume",
        "Amount", "Amplitude", "PctChange", "PriceChange", "TurnoverPct",
    ]
    return renamed[[column for column in preferred if column in renamed.columns]]


def _load_hist_df(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    plain_symbol = to_plain_symbol(symbol)
    tx_symbol = to_exchange_prefixed_symbol(symbol).lower()
    primary = getattr(ak, "stock_zh_a_hist", None)
    fallback = getattr(ak, "stock_zh_a_hist_tx", None)

    last_exc = None
    if primary is not None:
        try:
            df = _call_akshare_api(
                primary,
                symbol=plain_symbol,
                period="daily",
                start_date=format_date_for_api(start_date),
                end_date=format_date_for_api(end_date),
                adjust="qfq",
            )
            if not df.empty:
                return _standardize_hist_df(df, symbol)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc

    if fallback is not None:
        df = _call_akshare_api(
            fallback,
            symbol=tx_symbol,
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )
        return _standardize_hist_df(df, symbol)

    if last_exc:
        raise last_exc
    raise RuntimeError("AkShare A-share history APIs are unavailable.")


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    data = _load_hist_df(symbol, start_date, end_date)
    if data.empty:
        return f"No data found for A-share symbol '{normalize_ashare_symbol(symbol)}' between {start_date} and {end_date}"

    numeric_columns = [column for column in data.columns if column not in ("Date", "Ticker")]
    for column in numeric_columns:
        data[column] = pd.to_numeric(data[column], errors="coerce").round(4)

    header = f"# A-share stock data for {normalize_ashare_symbol(symbol)} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + data.to_csv(index=False)


def get_indicators(symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
    if indicator not in INDICATOR_DESCRIPTIONS:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: {list(INDICATOR_DESCRIPTIONS.keys())}"
        )
    # Reuse the existing yfinance/stockstats indicator path, which is already
    # stable in the upstream project. A-share tickers are converted to the
    # yfinance exchange suffixes expected by Yahoo Finance, e.g. ``600519.SH``
    # -> ``600519.SS``.
    yf_symbol = to_yfinance_symbol(symbol)
    result = get_stock_stats_indicators_window(
        yf_symbol,
        indicator,
        curr_date,
        look_back_days,
    )
    normalized = normalize_ashare_symbol(symbol)
    return result.replace(yf_symbol, normalized)


def get_fundamentals(ticker: str, curr_date: str | None = None) -> str:
    normalized = normalize_ashare_symbol(ticker)
    plain = to_plain_symbol(ticker)
    sections = []

    profile_fetcher = getattr(ak, "stock_profile_cninfo", None)
    fallback_profile_fetcher = getattr(ak, "stock_individual_info_em", None)
    intro_fetcher = getattr(ak, "stock_zyjs_ths", None)
    business_fetcher = getattr(ak, "stock_zygc_em", None)
    abstract_fetcher = getattr(ak, "stock_financial_abstract", None)

    if profile_fetcher is not None:
        try:
            profile_df = _call_akshare_api(profile_fetcher, symbol=plain)
            if not profile_df.empty:
                sections.append(_format_table(profile_df, f"# A-share company profile for {normalized}", rows=10))
        except Exception:  # noqa: BLE001
            profile_df = pd.DataFrame()
        else:
            profile_df = profile_df
    else:
        profile_df = pd.DataFrame()

    if profile_df.empty and fallback_profile_fetcher is not None:
        try:
            info_df = _call_akshare_api(fallback_profile_fetcher, symbol=plain)
            if not info_df.empty:
                sections.append(_format_table(info_df, f"# A-share company profile for {normalized}", rows=20))
        except Exception:  # noqa: BLE001
            pass

    if intro_fetcher is not None:
        try:
            intro_df = _call_akshare_api(intro_fetcher, symbol=plain)
            if not intro_df.empty:
                sections.append(_format_table(intro_df, "## 主营业务简介", rows=10))
        except Exception:  # noqa: BLE001
            pass

    if business_fetcher is not None:
        try:
            business_df = _call_akshare_api(business_fetcher, symbol=plain)
            business_df = _filter_report_rows(business_df, curr_date)
            if not business_df.empty:
                sections.append(_format_table(_round_numeric_frame(business_df), "## 主营构成", rows=10))
        except Exception:  # noqa: BLE001
            pass

    if abstract_fetcher is not None:
        try:
            abstract_df = _call_akshare_api(abstract_fetcher, symbol=plain)
            snapshot = _latest_abstract_snapshot(abstract_df, curr_date)
            if not snapshot.empty:
                sections.append(_format_table(snapshot, "## 最新关键财务摘要", rows=20))
        except Exception:  # noqa: BLE001
            pass

    if not sections:
        return f"No A-share fundamentals data found for {normalized}"
    return "\n\n".join(sections)


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    exchange_symbol = to_exchange_prefixed_symbol(ticker)
    if freq == "annual":
        fetcher = getattr(ak, "stock_balance_sheet_by_yearly_em", None)
    else:
        fetcher = getattr(ak, "stock_balance_sheet_by_report_em", None)
    if fetcher is None:
        return f"A-share balance-sheet API unavailable for {normalize_ashare_symbol(ticker)}"
    df = _call_akshare_api(fetcher, symbol=exchange_symbol)
    filtered = _filter_report_rows(df, curr_date)
    selected = _round_numeric_frame(_select_statement_columns(filtered, BALANCE_SHEET_COLUMNS))
    return _format_table(selected, f"# A-share balance sheet for {normalize_ashare_symbol(ticker)} ({freq})", rows=8)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    exchange_symbol = to_exchange_prefixed_symbol(ticker)
    if freq == "annual":
        fetcher = getattr(ak, "stock_cash_flow_sheet_by_quarterly_em", None)
    else:
        fetcher = getattr(ak, "stock_cash_flow_sheet_by_report_em", None)
    if fetcher is None:
        return f"A-share cash-flow API unavailable for {normalize_ashare_symbol(ticker)}"
    df = _call_akshare_api(fetcher, symbol=exchange_symbol)
    filtered = _filter_report_rows(df, curr_date)
    selected = _round_numeric_frame(_select_statement_columns(filtered, CASHFLOW_COLUMNS))
    return _format_table(selected, f"# A-share cash flow for {normalize_ashare_symbol(ticker)} ({freq})", rows=8)


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    exchange_symbol = to_exchange_prefixed_symbol(ticker)
    if freq == "annual":
        fetcher = getattr(ak, "stock_profit_sheet_by_quarterly_em", None)
    else:
        fetcher = getattr(ak, "stock_profit_sheet_by_report_em", None)
    if fetcher is None:
        return f"A-share income-statement API unavailable for {normalize_ashare_symbol(ticker)}"
    df = _call_akshare_api(fetcher, symbol=exchange_symbol)
    filtered = _filter_report_rows(df, curr_date)
    selected = _round_numeric_frame(_select_statement_columns(filtered, INCOME_COLUMNS))
    return _format_table(selected, f"# A-share income statement for {normalize_ashare_symbol(ticker)} ({freq})", rows=8)


def get_caixin_news(ticker: str, limit: int = 10) -> str:
    fetcher = getattr(ak, "stock_news_main_cx", None)
    if fetcher is None:
        return f"Caixin news API unavailable for {normalize_ashare_symbol(ticker)}"

    normalized = normalize_ashare_symbol(ticker)
    plain = to_plain_symbol(ticker)
    df = _call_akshare_api(fetcher)
    if df.empty:
        return f"未获取到财新新闻数据。"

    matched = df.copy()
    if "title" in matched.columns:
        mask = matched["title"].astype(str).str.contains(plain, na=False) | matched["title"].astype(str).str.contains(normalized, na=False)
        matched = matched[mask]
    if matched.empty:
        return f"财新新闻最近 100 条中未找到 {normalized} 相关资讯。"

    lines = [f"# 财新新闻 — {normalized}", ""]
    for _, row in matched.head(limit).iterrows():
        title = row.get("title") or row.get("标题") or "No title"
        summary = row.get("content") or row.get("摘要") or ""
        link = row.get("url") or row.get("链接") or ""
        lines.append(f"## {title}")
        if summary:
            lines.append(_safe_truncate(summary, 200))
        if link:
            lines.append(f"Link: {link}")
        lines.append("")
    return "\n".join(lines).strip()


def get_xueqiu_sentiment(ticker: str) -> str:
    normalized = normalize_ashare_symbol(ticker)
    fetchers = [
        ("热度榜", getattr(ak, "stock_hot_rank_em", None)),
        ("关注榜", getattr(ak, "stock_hot_follow_xq", None)),
        ("讨论榜", getattr(ak, "stock_hot_tweet_xq", None)),
        ("交易榜", getattr(ak, "stock_hot_deal_xq", None)),
    ]
    plain = to_plain_symbol(ticker)
    sections = [f"# 雪球情绪数据 — {normalized}", ""]
    hits = 0
    for label, fetcher in fetchers:
        if fetcher is None:
            continue
        try:
            df = _call_akshare_api(fetcher)
        except Exception:  # noqa: BLE001
            continue
        if df.empty:
            continue
        code_columns = [column for column in df.columns if "代码" in str(column) or "symbol" in str(column).lower()]
        name_columns = [column for column in df.columns if "名称" in str(column) or "name" in str(column).lower()]
        ranking_columns = [column for column in df.columns if "排名" in str(column) or "rank" in str(column).lower()]
        mask = pd.Series(False, index=df.index)
        for column in code_columns:
            mask = mask | (df[column].astype(str).str.contains(plain, na=False))
        matched = df[mask] if code_columns else pd.DataFrame()
        if matched.empty:
            continue
        hits += 1
        row = matched.iloc[0]
        rank = row[ranking_columns[0]] if ranking_columns else "N/A"
        name = row[name_columns[0]] if name_columns else plain
        sections.append(f"## {label}")
        sections.append(f"- 股票: {name}")
        sections.append(f"- 排名: {rank}")
        sections.append("")

    if hits == 0:
        return f"未在可用的雪球热度接口中找到 {normalized}。"
    return "\n".join(sections).strip()


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    normalized = normalize_ashare_symbol(ticker)
    plain = to_plain_symbol(ticker)
    sections = []

    research_fetcher = getattr(ak, "stock_research_report_em", None)
    if research_fetcher is not None:
        try:
            df = _call_akshare_api(research_fetcher, symbol=plain)
            if not df.empty:
                if "日期" in df.columns:
                    df["日期"] = parse_date_column(df["日期"])
                    start = pd.Timestamp(start_date)
                    end = pd.Timestamp(end_date) + timedelta(days=1) - timedelta(seconds=1)
                    df = df[(df["日期"] >= start) & (df["日期"] <= end)]
                if not df.empty:
                    fmt = df.copy()
                    if "东财评级" in fmt.columns and "报告名称" in fmt.columns:
                        fmt["新闻标题"] = "[" + fmt["东财评级"].fillna("研报") + "] " + fmt["报告名称"].fillna("")
                    selected_cols = [col for col in ["日期", "新闻标题", "机构", "行业评级", "报告名称"] if col in fmt.columns]
                    if selected_cols:
                        sections.append(_format_table(fmt[selected_cols], "## 券商研报（个股专项）", rows=20))
        except Exception:  # noqa: BLE001
            pass

    stock_news_fetcher = getattr(ak, "stock_news_em", None)
    if stock_news_fetcher is not None and not sections:
        try:
            df = _call_akshare_api(stock_news_fetcher, symbol=plain)
            if not df.empty and "发布时间" in df.columns:
                df["发布时间"] = parse_date_column(df["发布时间"])
                start = pd.Timestamp(start_date)
                end = pd.Timestamp(end_date) + timedelta(days=1) - timedelta(seconds=1)
                df = df[(df["发布时间"] >= start) & (df["发布时间"] <= end)]
                if not df.empty:
                    formatted = df.loc[:, [col for col in ["发布时间", "文章来源", "新闻标题", "新闻内容", "新闻链接"] if col in df.columns]].copy()
                    if "新闻内容" in formatted.columns:
                        formatted["新闻内容"] = formatted["新闻内容"].map(_safe_truncate)
                    sections.append(_format_table(formatted, f"# A-share company news for {normalized}", rows=20))
        except Exception:  # noqa: BLE001
            pass

    market_context = get_market_news(end_date, look_back_days=max((pd.Timestamp(end_date) - pd.Timestamp(start_date)).days, 3), limit=6)
    if market_context:
        sections.append(market_context)

    if not sections:
        return f"No A-share news found for {normalized} between {start_date} and {end_date}"

    return f"# A-share news pack for {normalized}\n\n" + "\n\n".join(sections)


def get_market_news(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    fetcher = getattr(ak, "stock_info_global_em", None)
    if fetcher is None:
        return "A-share market news API unavailable."
    df = _call_akshare_api(fetcher)
    if df.empty:
        return "未获取到 A 股市场与宏观快讯。"

    filtered = df.copy()
    if "发布时间" in filtered.columns:
        filtered["发布时间"] = parse_date_column(filtered["发布时间"])
        end = pd.Timestamp(curr_date) + timedelta(days=1) - timedelta(seconds=1)
        start = end - timedelta(days=look_back_days)
        filtered = filtered[(filtered["发布时间"] >= start) & (filtered["发布时间"] <= end)]
        filtered = filtered.sort_values("发布时间", ascending=False)
    if filtered.empty:
        return f"{curr_date} 前 {look_back_days} 天没有可用的市场快讯。"

    columns = [column for column in ["发布时间", "标题", "摘要", "链接"] if column in filtered.columns]
    formatted = filtered.loc[:, columns].head(limit).copy()
    if "摘要" in formatted.columns:
        formatted["摘要"] = formatted["摘要"].map(lambda value: _safe_truncate(value, 180))
    return _format_table(formatted, "# A-share market and policy news", rows=limit)


def get_company_announcements(ticker: str, start_date: str, end_date: str, category: str = "全部") -> str:
    normalized_symbol = normalize_ashare_symbol(ticker)
    plain_symbol = to_plain_symbol(ticker)
    fetcher = getattr(ak, "stock_notice_report", None)
    if fetcher is None:
        return f"A-share announcements API unavailable for {normalized_symbol}"

    frames = []
    errors = []
    for date_value in get_date_range(start_date, end_date):
        try:
            daily = _call_akshare_api(fetcher, symbol=category, date=format_date_for_api(date_value))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{date_value}: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")
            continue
        if daily.empty or "代码" not in daily.columns:
            continue
        matched = daily[daily["代码"].astype(str).str.upper() == plain_symbol]
        if not matched.empty:
            frames.append(matched)

    if not frames:
        if errors:
            return (
                f"{normalized_symbol} 在 {start_date} 到 {end_date} 之间未能稳定获取公告数据。\n\n"
                + "\n".join(errors[:5])
            )
        return f"{normalized_symbol} 在 {start_date} 到 {end_date} 之间没有匹配的公告。"

    combined = pd.concat(frames, ignore_index=True)
    combined["公告日期"] = parse_date_column(combined["公告日期"])
    combined = combined.sort_values("公告日期", ascending=False).drop_duplicates(subset=["公告标题", "公告日期"])
    formatted = combined.loc[:, [col for col in ["公告日期", "公告类型", "公告标题", "网址"] if col in combined.columns]].head(20).copy()
    if "公告日期" in formatted.columns:
        formatted["公告日期"] = formatted["公告日期"].dt.strftime("%Y-%m-%d")
    output = _format_table(formatted, f"# A-share company announcements for {normalized_symbol}", rows=20)
    if errors:
        output += "\n\n## Data retrieval notes\n\n" + "\n".join(f"- {item}" for item in errors[:5])
    return output


def get_company_event_signals(ticker: str, start_date: str, end_date: str) -> str:
    """Summarise announcement-derived event signals for A-share tickers."""
    normalized = normalize_ashare_symbol(ticker)
    plain = to_plain_symbol(ticker)
    fetcher = getattr(ak, "stock_individual_notice_report", None)
    if fetcher is None:
        return f"A-share event-signal API unavailable for {normalized}"

    categories = ["重大事项", "风险提示", "融资公告", "持股变动"]
    sections = [f"# A-share company event signals for {normalized}", ""]
    any_hits = False
    errors = []
    tag_counter: dict[str, int] = {}
    bias_counter = {"positive": 0, "negative": 0, "mixed": 0, "neutral": 0}
    event_examples: dict[str, list[str]] = {}

    for category in categories:
        try:
            df = _call_akshare_api(
                fetcher,
                security=plain,
                symbol=category,
                begin_date=start_date,
                end_date=end_date,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{category}: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")
            continue

        if df.empty:
            continue

        any_hits = True
        working = df.copy()
        date_col = next((c for c in ["公告日期", "NOTICE_DATE", "date"] if c in working.columns), None)
        title_col = next((c for c in ["公告标题", "title", "名称"] if c in working.columns), None)
        link_col = next((c for c in ["网址", "链接", "url"] if c in working.columns), None)
        type_col = next((c for c in ["公告类型", "类型", "notice_type"] if c in working.columns), None)

        if date_col:
            working[date_col] = parse_date_column(working[date_col])
            working = working.sort_values(date_col, ascending=False)

        sections.append(f"## {category}")
        sections.append(f"- Count: {len(working)}")
        latest_rows = working.head(5)
        for _, row in latest_rows.iterrows():
            line = []
            title_value = str(row.get(title_col, "")) if title_col else ""
            tag = _classify_event_tag(title_value)
            bias = _tag_bias(tag, title_value)
            tag_counter[tag] = tag_counter.get(tag, 0) + 1
            bias_counter[bias] = bias_counter.get(bias, 0) + 1
            event_examples.setdefault(tag, [])
            if title_value and len(event_examples[tag]) < 2:
                event_examples[tag].append(_safe_truncate(title_value, 60))
            if date_col and pd.notna(row.get(date_col)):
                line.append(pd.Timestamp(row[date_col]).strftime("%Y-%m-%d"))
            if type_col and row.get(type_col):
                line.append(str(row[type_col]))
            line.append(f"tag={tag}")
            line.append(f"bias={bias}")
            if title_col and row.get(title_col):
                line.append(_safe_truncate(row[title_col], 120))
            if link_col and row.get(link_col):
                line.append(str(row[link_col]))
            sections.append("- " + " | ".join(line))
        sections.append("")

    if not any_hits:
        if errors:
            return (
                f"{normalized} 在 {start_date} 到 {end_date} 之间未能稳定获取事件信号。\n\n"
                + "\n".join(errors[:5])
            )
        return f"{normalized} 在 {start_date} 到 {end_date} 之间没有可识别的事件信号。"

    sections.insert(
        2,
        "## Event summary\n"
        f"- Positive-biased events: {bias_counter.get('positive', 0)}\n"
        f"- Negative-biased events: {bias_counter.get('negative', 0)}\n"
        f"- Mixed events: {bias_counter.get('mixed', 0)}\n"
        f"- Neutral / other events: {bias_counter.get('neutral', 0)}"
    )
    if tag_counter:
        sections.insert(3, "## Dominant tags")
        tag_lines = []
        for tag, count in sorted(tag_counter.items(), key=lambda item: (-item[1], item[0])):
            examples = "; ".join(event_examples.get(tag, []))
            tag_lines.append(f"- {tag}: {count}" + (f" | examples: {examples}" if examples else ""))
        sections[4:4] = tag_lines + [""]

    if errors:
        sections.append("## Data retrieval notes")
        sections.extend(f"- {item}" for item in errors[:5])
    return "\n".join(sections).strip()


def get_market_activity(ticker: str, curr_date: str) -> str:
    """Combine fund flow, northbound holdings, and margin signals for A-shares."""
    normalized = normalize_ashare_symbol(ticker)
    plain = to_plain_symbol(ticker)
    exchange = get_ashare_exchange(ticker)
    market_code = exchange.lower()
    sections = [f"# A-share market activity signals for {normalized}", ""]
    errors = []

    fund_flow_fetcher = getattr(ak, "stock_individual_fund_flow", None)
    if fund_flow_fetcher is not None:
        try:
            df = _call_akshare_api(fund_flow_fetcher, stock=plain, market=market_code)
            if not df.empty:
                working = df.copy().head(5)
                sections.append("## Individual fund flow")
                sections.append(working.to_csv(index=False))
                main_flow_col = _find_first_numeric_column(working, ["主力净流入-净额", "主力净流入净额"])
                if main_flow_col:
                    values = pd.to_numeric(working[main_flow_col], errors="coerce").dropna()
                    if not values.empty:
                        pos = int((values > 0).sum())
                        neg = int((values < 0).sum())
                        latest = values.iloc[0]
                        sections.append(
                            f"Signal: recent main-fund-flow observations positive={pos}, negative={neg}, latest={latest:.2f}"
                        )
                        trend = _describe_series_trend(
                            values,
                            "main fund flow",
                            "buying pressure strengthening",
                            "selling pressure strengthening",
                        )
                        if trend:
                            sections.append(f"Trend: {trend}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"fund_flow: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")

    northbound_fetcher = getattr(ak, "stock_hsgt_individual_em", None)
    if northbound_fetcher is not None:
        try:
            df = _call_akshare_api(northbound_fetcher, symbol=plain)
            if not df.empty:
                working = df.copy().head(5)
                sections.append("## Northbound holding activity")
                sections.append(working.to_csv(index=False))
                northbound_col = _find_first_numeric_column(
                    working,
                    ["持股数量", "HOLD_SHARES", "持股市值", "HOLD_MARKET_CAP"],
                )
                if northbound_col:
                    values = pd.to_numeric(working[northbound_col], errors="coerce").dropna()
                    if len(values) >= 2:
                        delta = values.iloc[0] - values.iloc[1]
                        sections.append(f"Signal: northbound latest delta on {northbound_col} = {delta:.2f}")
                    trend = _describe_series_trend(
                        values,
                        f"northbound {northbound_col}",
                        "northbound accumulation",
                        "northbound reduction",
                    )
                    if trend:
                        sections.append(f"Trend: {trend}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"northbound: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")

    trade_date = get_previous_trade_date(curr_date)
    trade_date_compact = trade_date.replace("-", "")
    if exchange == "SZ":
        margin_fetcher = getattr(ak, "stock_margin_detail_szse", None)
        margin_kwargs = {"date": trade_date_compact}
    elif exchange == "SH":
        margin_fetcher = getattr(ak, "stock_margin_detail_sse", None)
        margin_kwargs = {"date": trade_date_compact}
    else:
        margin_fetcher = None
        margin_kwargs = {}

    if margin_fetcher is not None:
        try:
            df = _call_akshare_api(margin_fetcher, **margin_kwargs)
            if not df.empty:
                code_columns = [c for c in df.columns if "代码" in str(c) or "证券代码" in str(c)]
                matched = pd.DataFrame()
                for column in code_columns:
                    matched = df[df[column].astype(str).str.contains(plain, na=False)]
                    if not matched.empty:
                        break
                if not matched.empty:
                    sections.append("## Margin trading detail")
                    sections.append(matched.head(3).to_csv(index=False))
                    for col in ["融资余额", "融资买入额", "融券余额", "融券余量"]:
                        if col in matched.columns:
                            val = pd.to_numeric(matched[col], errors="coerce").dropna()
                            if not val.empty:
                                sections.append(f"Signal: latest {col} = {val.iloc[0]:.2f}")
                    financing_col = _find_first_numeric_column(matched, ["融资余额", "融资买入额"])
                    if financing_col:
                        trend = _describe_series_trend(
                            pd.to_numeric(matched[financing_col], errors="coerce"),
                            financing_col,
                            "leverage demand increasing",
                            "leverage demand easing",
                        )
                        if trend:
                            sections.append(f"Trend: {trend}")
                    short_col = _find_first_numeric_column(matched, ["融券余额", "融券余量"])
                    if short_col:
                        trend = _describe_series_trend(
                            pd.to_numeric(matched[short_col], errors="coerce"),
                            short_col,
                            "short exposure increasing",
                            "short exposure easing",
                        )
                        if trend:
                            sections.append(f"Trend: {trend}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"margin: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")

    if len(sections) == 2:
        if errors:
            return (
                f"未能稳定获取 {normalized} 的市场活动信号。\n\n"
                + "\n".join(errors[:5])
            )
        return f"未获取到 {normalized} 的市场活动信号。"

    if errors:
        sections.append("## Data retrieval notes")
        sections.extend(f"- {item}" for item in errors[:5])
    return "\n".join(sections).strip()


def get_sector_rotation_context(ticker: str, curr_date: str) -> str:
    """Summarise industry / concept board context for an A-share ticker."""
    normalized = normalize_ashare_symbol(ticker)
    plain = to_plain_symbol(ticker)
    sections = [f"# A-share sector rotation context for {normalized}", ""]
    errors = []

    profile_fetchers = [
        getattr(ak, "stock_profile_cninfo", None),
        getattr(ak, "stock_individual_info_em", None),
    ]
    industry_names: list[str] = []
    concept_names: list[str] = []

    for fetcher in profile_fetchers:
        if fetcher is None:
            continue
        try:
            profile_df = _call_akshare_api(fetcher, symbol=plain)
            if not profile_df.empty:
                if not industry_names:
                    industry_names = _extract_text_values(
                        profile_df,
                        ["所属行业", "行业", "申万行业", "所属东财行业"],
                        limit=5,
                    )
                if not concept_names:
                    concept_names = _expand_delimited_values(
                        _extract_text_values(
                            profile_df,
                            ["所属概念", "概念", "概念题材", "涉及概念"],
                            limit=10,
                        ),
                        limit=10,
                    )
            if industry_names or concept_names:
                break
        except Exception as exc:  # noqa: BLE001
            errors.append(f"profile: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")

    if industry_names:
        sections.append("## Industry tags")
        sections.extend(f"- {name}" for name in industry_names)
        sections.append("")

    if concept_names:
        sections.append("## Concept / theme tags")
        sections.extend(f"- {name}" for name in concept_names[:8])
        sections.append("")

    industry_board_fetcher = getattr(ak, "stock_board_industry_cons_em", None)
    if industry_board_fetcher is not None and industry_names:
        for industry_name in industry_names[:2]:
            try:
                df = _call_akshare_api(industry_board_fetcher, symbol=industry_name)
                if df.empty:
                    continue
                board_df = df.copy()
                sections.append(f"## Industry board sample: {industry_name}")
                sample_columns = [col for col in ["代码", "名称", "最新价", "涨跌幅", "成交额"] if col in board_df.columns]
                sample = board_df.loc[:, sample_columns].head(5) if sample_columns else board_df.head(5)
                sections.append(sample.to_csv(index=False))
                peer_names = _extract_text_values(board_df, ["名称", "股票名称"], limit=5)
                if peer_names:
                    sections.append(f"Signal: representative peers in {industry_name}: {', '.join(peer_names[:5])}")
                change_col = _find_first_numeric_column(board_df, ["涨跌幅", "涨跌额"])
                if change_col:
                    values = pd.to_numeric(board_df[change_col], errors="coerce").dropna().head(10)
                    if not values.empty:
                        sections.append(
                            f"Signal: {industry_name} board snapshot mean {change_col}={values.mean():.2f} across sampled constituents"
                        )
                sections.append("")
                break
            except Exception as exc:  # noqa: BLE001
                errors.append(f"industry_board: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")

    concept_board_fetcher = getattr(ak, "stock_board_concept_cons_em", None)
    if concept_board_fetcher is not None and concept_names:
        for concept_name in concept_names[:2]:
            try:
                df = _call_akshare_api(concept_board_fetcher, symbol=concept_name)
                if df.empty:
                    continue
                board_df = df.copy()
                sections.append(f"## Concept board sample: {concept_name}")
                sample_columns = [col for col in ["代码", "名称", "最新价", "涨跌幅", "成交额"] if col in board_df.columns]
                sample = board_df.loc[:, sample_columns].head(5) if sample_columns else board_df.head(5)
                sections.append(sample.to_csv(index=False))
                peer_names = _extract_text_values(board_df, ["名称", "股票名称"], limit=5)
                if peer_names:
                    sections.append(f"Signal: representative peers in {concept_name}: {', '.join(peer_names[:5])}")
                change_col = _find_first_numeric_column(board_df, ["涨跌幅", "涨跌额"])
                if change_col:
                    values = pd.to_numeric(board_df[change_col], errors="coerce").dropna().head(10)
                    if not values.empty:
                        sections.append(
                            f"Signal: {concept_name} board snapshot mean {change_col}={values.mean():.2f} across sampled constituents"
                        )
                sections.append("")
                break
            except Exception as exc:  # noqa: BLE001
                errors.append(f"concept_board: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")

    if len(sections) == 2:
        if errors:
            return (
                f"未能稳定获取 {normalized} 的行业 / 概念联动信息。\n\n"
                + "\n".join(errors[:5])
            )
        return f"未获取到 {normalized} 的行业 / 概念联动信息。"

    sections.append("## Rotation takeaways")
    if industry_names:
        sections.append(f"- Primary industry context: {industry_names[0]}")
    if concept_names:
        sections.append(f"- Active concept / theme context: {', '.join(concept_names[:3])}")
    sections.append("- Use this board context to judge whether the stock move is idiosyncratic or part of broader sector / theme rotation.")

    if errors:
        sections.append("")
        sections.append("## Data retrieval notes")
        sections.extend(f"- {item}" for item in errors[:5])
    return "\n".join(sections).strip()


def get_sector_strength_snapshot(curr_date: str, limit: int = 5) -> str:
    """Return a ranked snapshot of leading / lagging A-share industry and concept boards."""
    sections = [f"# A-share sector strength snapshot for {curr_date}", ""]
    errors = []

    def append_board_rankings(
        title: str,
        fetcher_name: str,
        name_candidates: list[str],
        change_candidates: list[str],
    ) -> None:
        fetcher = getattr(ak, fetcher_name, None)
        if fetcher is None:
            return
        try:
            df = _call_akshare_api(fetcher)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{fetcher_name}: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")
            return
        if df.empty:
            return

        working = df.copy()
        name_col = next((col for col in name_candidates if col in working.columns), None)
        change_col = _find_first_numeric_column(working, change_candidates)
        if name_col is None or change_col is None:
            return

        working[change_col] = pd.to_numeric(working[change_col], errors="coerce")
        working = working.dropna(subset=[change_col])
        if working.empty:
            return

        leaders = working.sort_values(change_col, ascending=False).head(limit)
        laggards = working.sort_values(change_col, ascending=True).head(limit)

        sections.append(f"## {title}")
        sections.append(f"Top leaders by {change_col}:")
        for _, row in leaders.iterrows():
            sections.append(f"- {row[name_col]}: {float(row[change_col]):.2f}")
        sections.append(f"Laggards by {change_col}:")
        for _, row in laggards.iterrows():
            sections.append(f"- {row[name_col]}: {float(row[change_col]):.2f}")
        leader_names = ", ".join(str(row[name_col]) for _, row in leaders.head(3).iterrows())
        laggard_names = ", ".join(str(row[name_col]) for _, row in laggards.head(3).iterrows())
        sections.append(f"Signal: leading boards currently include {leader_names}.")
        sections.append(f"Signal: weakest boards currently include {laggard_names}.")
        sections.append("")

    append_board_rankings(
        "Industry board strength",
        "stock_board_industry_name_em",
        ["板块名称", "名称"],
        ["涨跌幅", "涨跌额"],
    )
    append_board_rankings(
        "Concept board strength",
        "stock_board_concept_name_em",
        ["板块名称", "名称"],
        ["涨跌幅", "涨跌额"],
    )

    if len(sections) == 2:
        if errors:
            return "未能稳定获取 A 股板块强弱快照。\n\n" + "\n".join(errors[:5])
        return "未获取到可用的 A 股板块强弱快照。"

    if errors:
        sections.append("## Data retrieval notes")
        sections.extend(f"- {item}" for item in errors[:5])
    return "\n".join(sections).strip()


def get_relative_strength_context(ticker: str, curr_date: str, look_back_days: int = 20) -> str:
    """Summarise stock-relative strength versus benchmark and board context."""
    normalized = normalize_ashare_symbol(ticker)
    benchmark_symbol = _resolve_a_share_benchmark(ticker)
    sections = [f"# A-share relative strength context for {normalized}", ""]

    start_date = (pd.Timestamp(curr_date) - pd.Timedelta(days=max(look_back_days * 3, 60))).strftime("%Y-%m-%d")
    stock_df = _load_hist_df(ticker, start_date, curr_date)
    benchmark_df = load_ohlcv(benchmark_symbol, curr_date)
    stock_return, stock_latest = _compute_window_return(stock_df, look_back_days)
    benchmark_return, benchmark_latest = _compute_window_return(benchmark_df, look_back_days)

    if stock_return is not None:
        sections.append("## Stock vs benchmark")
        sections.append(f"- Stock return over ~{look_back_days} calendar days: {stock_return * 100:.2f}%")
        sections.append(f"- Stock latest available date: {stock_latest}")
        sections.append(f"- Benchmark symbol: {benchmark_symbol}")
        if benchmark_return is not None:
            alpha = stock_return - benchmark_return
            sections.append(f"- Benchmark return over ~{look_back_days} calendar days: {benchmark_return * 100:.2f}%")
            sections.append(f"- Benchmark latest available date: {benchmark_latest}")
            sections.append(f"- Relative strength alpha: {alpha * 100:.2f}%")
            if alpha > 0.03:
                sections.append("- Signal: stock is outperforming its market benchmark by a meaningful margin.")
            elif alpha < -0.03:
                sections.append("- Signal: stock is lagging its market benchmark by a meaningful margin.")
            else:
                sections.append("- Signal: stock is moving broadly in line with its market benchmark.")
        sections.append("")

    sector_text = get_sector_rotation_context(ticker, curr_date)
    strength_text = get_sector_strength_snapshot(curr_date)
    if "Rotation takeaways" in sector_text:
        sections.append("## Board-relative read")
        if "Industry tags" in sector_text:
            industry_line = next((line for line in sector_text.splitlines() if line.startswith("- Primary industry context:")), None)
            if industry_line:
                sections.append(industry_line)
        if "leading boards currently include" in strength_text:
            sections.append("- Compare the stock's own return and momentum to whether its industry / concept appears among current leading boards.")
        if "weakest boards currently include" in strength_text:
            sections.append("- If the stock is holding up despite weak board leadership, treat that as possible idiosyncratic strength.")
        sections.append("")

    if len(sections) == 2:
        return f"未获取到 {normalized} 的相对强弱信息。"

    sections.extend(["## Source Digests", "", sector_text, "", strength_text])
    return "\n".join(sections).strip()


def get_corporate_action_pressure_context(ticker: str, start_date: str, end_date: str) -> str:
    """Summarise A-share corporate-action pressure from announcement-derived events."""
    normalized = normalize_ashare_symbol(ticker)
    event_text = get_company_event_signals(ticker, start_date, end_date)
    lines = [line.strip() for line in event_text.splitlines() if line.strip().startswith("- ")]

    score_buckets = {
        "supply_pressure": {"tags": {"shareholder_change", "lockup", "financing"}, "score": 0, "events": []},
        "governance_pressure": {"tags": {"pledge", "litigation", "risk_warning", "suspension"}, "score": 0, "events": []},
        "positive_offsets": {"tags": {"buyback", "contract_order", "earnings_preview", "dividend"}, "score": 0, "events": []},
    }

    for line in lines:
        tag_match = re.search(r"tag=([a-z_]+)", line)
        bias_match = re.search(r"bias=([a-z_]+)", line)
        if not tag_match:
            continue
        tag = tag_match.group(1)
        bias = bias_match.group(1) if bias_match else "neutral"
        for bucket_name, bucket in score_buckets.items():
            if tag not in bucket["tags"]:
                continue
            weight = 1
            if bias == "negative" and bucket_name != "positive_offsets":
                weight = 2
            elif bias == "positive" and bucket_name == "positive_offsets":
                weight = 2
            bucket["score"] += weight
            if len(bucket["events"]) < 4:
                bucket["events"].append(line)

    supply_score = score_buckets["supply_pressure"]["score"]
    governance_score = score_buckets["governance_pressure"]["score"]
    positive_score = score_buckets["positive_offsets"]["score"]

    def describe_pressure(score: int) -> str:
        if score >= 5:
            return "high"
        if score >= 2:
            return "medium"
        return "low"

    sections = [
        f"# A-share corporate action pressure context for {normalized}",
        "",
        "## Pressure scorecard",
        f"- Supply / dilution pressure: {describe_pressure(supply_score)} (score={supply_score})",
        f"- Governance / legal pressure: {describe_pressure(governance_score)} (score={governance_score})",
        f"- Positive offset strength: {describe_pressure(positive_score)} (score={positive_score})",
        "",
        "## Interpretation",
    ]

    if supply_score >= 5:
        sections.append("- Supply-side events such as reductions, lock-up expiry, or financing appear concentrated and deserve extra caution.")
    elif supply_score >= 2:
        sections.append("- Some supply-side pressure is present, but it does not dominate the event set.")
    else:
        sections.append("- No heavy supply-side pressure signal stands out from recent corporate actions.")

    if governance_score >= 5:
        sections.append("- Governance / legal style events are dense enough to materially raise headline risk.")
    elif governance_score >= 2:
        sections.append("- Governance / legal risk exists and should be tracked alongside price action.")
    else:
        sections.append("- No major governance / legal overhang dominates the current announcement mix.")

    if positive_score >= 5:
        sections.append("- Positive offsets such as buybacks, contracts, dividends, or earnings signals are materially present.")
    elif positive_score >= 2:
        sections.append("- There are some positive corporate-action offsets, but they do not fully erase the risk side.")
    else:
        sections.append("- Positive corporate-action offsets are limited in the current lookback window.")

    sections.extend(["", "## Flagged events"])
    for title, key in [
        ("Supply / dilution flags", "supply_pressure"),
        ("Governance / legal flags", "governance_pressure"),
        ("Positive offset flags", "positive_offsets"),
    ]:
        sections.append(f"### {title}")
        if score_buckets[key]["events"]:
            sections.extend(score_buckets[key]["events"])
        else:
            sections.append("- No prominent events detected.")

    sections.extend(["", "## Source Digest", "", event_text])
    return "\n".join(sections).strip()


def get_decision_signal_summary(ticker: str, start_date: str, end_date: str, curr_date: str) -> str:
    """Build a concise A-share decision summary from events and activity signals."""
    normalized = normalize_ashare_symbol(ticker)
    event_text = get_company_event_signals(ticker, start_date, end_date)
    activity_text = get_market_activity(ticker, curr_date)
    sector_text = get_sector_rotation_context(ticker, curr_date)
    strength_text = get_sector_strength_snapshot(curr_date)
    relative_text = get_relative_strength_context(ticker, curr_date)
    action_pressure_text = get_corporate_action_pressure_context(ticker, start_date, end_date)

    def count_token(text: str, token: str) -> int:
        return text.count(token)

    positive = count_token(event_text, "bias=positive")
    negative = count_token(event_text, "bias=negative")
    mixed = count_token(event_text, "bias=mixed")

    catalysts = []
    risks = []
    dilution = []
    flow = []

    if "tag=contract_order" in event_text:
        catalysts.append("Recent contract / order announcements may support near-term sentiment.")
    if "tag=buyback" in event_text:
        catalysts.append("Buyback-related disclosures can signal management confidence.")
    if "tag=earnings_preview" in event_text:
        catalysts.append("Earnings-preview disclosures may act as a direct price catalyst.")

    if "tag=risk_warning" in event_text:
        risks.append("Risk-warning announcements increase downside and sentiment risk.")
    if "tag=litigation" in event_text:
        risks.append("Litigation / investigation related notices need extra caution.")
    if "tag=suspension" in event_text:
        risks.append("Suspension / resumption related events can impair exit flexibility.")
    if "tag=lockup" in event_text:
        risks.append("Lock-up expiry related items can create supply overhang.")

    if "tag=financing" in event_text:
        dilution.append("Financing-related announcements may imply dilution or capital-raising pressure.")
    if "tag=shareholder_change" in event_text and "bias=negative" in event_text:
        dilution.append("Shareholder reduction related events may pressure supply / sentiment.")

    if "Individual fund flow" in activity_text:
        flow.append("Individual fund-flow data is available and should be checked for persistence, not just one-day spikes.")
    if "Northbound holding activity" in activity_text:
        flow.append("Northbound holding changes are available and may help validate institutional appetite.")
    if "Margin trading detail" in activity_text:
        flow.append("Margin-trading detail is available; rising leverage can amplify both upside and downside.")
    if "buying pressure strengthening" in activity_text:
        flow.append("Main-fund-flow trend suggests incremental buying pressure rather than a one-day anomaly.")
    if "selling pressure strengthening" in activity_text:
        flow.append("Main-fund-flow trend suggests persistent selling pressure that deserves caution.")
    if "northbound accumulation" in activity_text:
        flow.append("Northbound positioning appears to be building, which can support institutional confirmation.")
    if "northbound reduction" in activity_text:
        flow.append("Northbound positioning appears to be trimming, which weakens external confirmation.")
    if "leverage demand increasing" in activity_text:
        flow.append("Margin-financing demand is rising, which can reinforce upside but also raise unwind risk.")
    if "short exposure increasing" in activity_text:
        flow.append("Short-side exposure is rising, which may reflect growing skepticism or hedging demand.")
    if "Rotation takeaways" in sector_text:
        flow.append("Sector / concept rotation context is available and should be used to separate stock-specific moves from board-wide moves.")
    if "board snapshot mean 涨跌幅" in sector_text:
        flow.append("Board snapshot performance is available, which helps judge whether relative strength is stock-specific or sector-driven.")
    if "leading boards currently include" in strength_text:
        flow.append("Broader board-strength rankings are available, which helps place the ticker inside the current rotation leaderboard.")
    if "outperforming its market benchmark" in relative_text:
        flow.append("Recent relative-strength alpha versus the market benchmark is positive, which supports momentum confirmation.")
    if "lagging its market benchmark" in relative_text:
        flow.append("Recent relative-strength alpha versus the market benchmark is negative, which tempers conviction.")
    if "Supply / dilution pressure: high" in action_pressure_text:
        dilution.append("Corporate-action pressure is elevated, especially around supply / dilution style events.")
    if "Governance / legal pressure: high" in action_pressure_text:
        risks.append("Corporate-action risk scorecard points to elevated governance or legal headline risk.")
    if "Positive offset strength: high" in action_pressure_text:
        catalysts.append("Positive corporate-action offsets are strong enough to partly cushion the pressure side.")

    bias_line = (
        f"Event balance over the lookback window: positive={positive}, negative={negative}, mixed={mixed}."
    )

    sections = [
        f"# A-share decision signal summary for {normalized}",
        "",
        "## Overall read",
        bias_line,
        (
            "Net event tone looks constructive."
            if positive > negative
            else "Net event tone looks cautious."
            if negative > positive
            else "Event tone looks mixed / balanced."
        ),
        "",
        "## Catalysts",
    ]
    sections.extend(f"- {item}" for item in (catalysts or ["No strong positive event catalyst was detected from the current rule set."]))
    sections.extend(["", "## Risks"])
    sections.extend(f"- {item}" for item in (risks or ["No major rule-based risk event was detected, but absence of evidence is not evidence of absence."]))
    sections.extend(["", "## Dilution / Supply Pressure"])
    sections.extend(f"- {item}" for item in (dilution or ["No obvious dilution / supply-pressure event was detected from the current rule set."]))
    sections.extend(["", "## Capital Flow / Activity"])
    sections.extend(f"- {item}" for item in (flow or ["No additional flow / activity signal was retrieved beyond the base price and news context."]))
    sections.extend(["", "## Source Digests", "", event_text, "", activity_text, "", sector_text, "", strength_text, "", relative_text, "", action_pressure_text])
    return "\n".join(sections).strip()
