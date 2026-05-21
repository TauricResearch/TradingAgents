from __future__ import annotations

from datetime import datetime, timedelta
import logging
import math
import re
import threading
import time
from types import SimpleNamespace

import pandas as pd
from pydantic import BaseModel, Field

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
from ..llm_clients import create_llm_client
from .stockstats_utils import load_ohlcv
from .y_finance import get_stock_stats_indicators_window

logger = logging.getLogger(__name__)

# Some AkShare endpoints rely on ``py_mini_racer`` to execute JS for request
# signing (for example THS fund-flow pages). That runtime is not safe to
# initialize concurrently in our current macOS / Python 3.13 environment and
# can crash the whole process inside ``libmini_racer``. LangGraph may invoke
# multiple tools in parallel, so we serialize AkShare calls at the module
# boundary to keep the process stable.
_AKSHARE_API_LOCK = threading.RLock()

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

POLICY_SUPPORTIVE_KEYWORDS = (
    "支持",
    "鼓励",
    "推进",
    "提振",
    "扩大",
    "优化",
    "减税",
    "降准",
    "降息",
    "补贴",
    "专项债",
    "稳增长",
)
POLICY_RESTRICTIVE_KEYWORDS = (
    "监管",
    "从严",
    "处罚",
    "整治",
    "问询",
    "规范",
    "风险提示",
    "暂停",
    "叫停",
    "收紧",
)
POLICY_TOPIC_KEYWORDS = (
    "证监会",
    "交易所",
    "国务院",
    "央行",
    "财政部",
    "发改委",
    "工信部",
    "住建部",
    "国资委",
    "商务部",
    "地产",
    "算力",
    "人工智能",
    "新能源",
    "半导体",
    "汽车",
)


class _NewsRelevanceDecision(BaseModel):
    relevant: bool = Field(description="Whether the article is materially relevant to the company.")
    confidence: int = Field(description="Integer confidence from 1 to 5.")
    reason: str = Field(description="Short explanation of why the article is or is not relevant.")


def _call_akshare_api(func, *args, retries: int = 2, retry_delay: float = 0.5, **kwargs):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            with _AKSHARE_API_LOCK:
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


def _get_a_share_news_aliases(ticker: str) -> list[str]:
    config = get_config()
    alias_map = config.get("a_share_news_aliases", {}) or {}
    normalized = normalize_ashare_symbol(ticker)
    plain = to_plain_symbol(normalized)
    aliases: list[str] = []
    for key in (normalized, plain):
        for value in alias_map.get(key, []) or []:
            clean = str(value).strip()
            if clean and clean not in aliases:
                aliases.append(clean)
    return aliases


def _get_a_share_news_keywords(ticker: str) -> list[str]:
    normalized = normalize_ashare_symbol(ticker)
    plain = to_plain_symbol(normalized)
    keywords: list[str] = [normalized, plain]

    profile_fetchers = [
        getattr(ak, "stock_profile_cninfo", None),
        getattr(ak, "stock_individual_info_em", None),
    ]
    for fetcher in profile_fetchers:
        if fetcher is None:
            continue
        try:
            profile_df = _call_akshare_api(fetcher, symbol=plain)
        except Exception:  # noqa: BLE001
            continue
        if profile_df.empty:
            continue
        for column in ["A股简称", "证券简称", "股票简称", "名称", "曾用简称", "公司名称"]:
            if column not in profile_df.columns:
                continue
            for value in profile_df[column].dropna().astype(str):
                for item in re.split(r"[>,，、/|\\s]+", value.replace(">>", ">")):
                    clean = item.strip()
                    if clean and clean not in keywords:
                        keywords.append(clean)
        if len(keywords) > 2:
            break

    for alias in _get_a_share_news_aliases(ticker):
        if alias not in keywords:
            keywords.append(alias)

    return keywords


def _match_keyword_news_rows(
    df: pd.DataFrame,
    keywords: list[str],
    text_columns: list[str],
) -> pd.DataFrame:
    if df.empty or not keywords:
        return pd.DataFrame()
    pattern = "|".join(re.escape(keyword) for keyword in keywords if keyword)
    if not pattern:
        return pd.DataFrame()

    mask = pd.Series(False, index=df.index)
    for column in text_columns:
        if column in df.columns:
            mask = mask | df[column].astype(str).str.contains(pattern, na=False, case=False)
    return df[mask]


def _fetch_keyword_news_df(
    ticker: str,
    start_date: str,
    end_date: str,
    keywords: list[str],
) -> pd.DataFrame:
    fetcher = getattr(ak, "stock_news_em", None)
    if fetcher is None:
        return pd.DataFrame()

    frames = []
    for keyword in keywords[:8]:
        try:
            df = _call_akshare_api(fetcher, symbol=keyword)
        except Exception:  # noqa: BLE001
            continue
        if df.empty or "发布时间" not in df.columns:
            continue
        working = df.copy()
        working["发布时间"] = parse_date_column(working["发布时间"])
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date) + timedelta(days=1) - timedelta(seconds=1)
        working = working[(working["发布时间"] >= start) & (working["发布时间"] <= end)]
        if working.empty:
            continue
        working["匹配关键词"] = keyword
        frames.append(working)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    dedupe_cols = [col for col in ["新闻标题", "发布时间"] if col in combined.columns]
    if dedupe_cols:
        combined = combined.drop_duplicates(subset=dedupe_cols)
    return combined.sort_values("发布时间", ascending=False)


def _collect_company_context_for_news(ticker: str) -> dict[str, object]:
    plain = to_plain_symbol(ticker)
    keywords = _get_a_share_news_keywords(ticker)
    industry_names: list[str] = []
    business_terms: list[str] = []
    profile_fetchers = [
        getattr(ak, "stock_profile_cninfo", None),
        getattr(ak, "stock_individual_info_em", None),
        getattr(ak, "stock_zyjs_ths", None),
    ]
    for fetcher in profile_fetchers:
        if fetcher is None:
            continue
        try:
            profile_df = _call_akshare_api(fetcher, symbol=plain)
        except Exception:  # noqa: BLE001
            continue
        if profile_df.empty:
            continue
        if not industry_names:
            industry_names = _extract_text_values(
                profile_df,
                ["所属行业", "行业", "申万行业", "所属东财行业"],
                limit=4,
            )
        if not business_terms:
            business_terms = _expand_delimited_values(
                _extract_text_values(
                    profile_df,
                    ["主营业务", "产品类型", "产品名称", "主营构成"],
                    limit=12,
                ),
                limit=12,
            )
        if industry_names or business_terms:
            break
    return {
        "keywords": keywords,
        "industry_names": industry_names,
        "business_terms": business_terms,
    }


def _heuristic_news_relevance_score(row: pd.Series, company_context: dict[str, object]) -> tuple[int, str]:
    keywords = [str(item) for item in company_context.get("keywords", [])]
    industry_names = [str(item) for item in company_context.get("industry_names", [])]
    business_terms = [str(item) for item in company_context.get("business_terms", [])]
    text_parts = [str(row.get(col, "")) for col in ["新闻标题", "新闻内容", "标题", "摘要", "内容"]]
    text = " ".join(text_parts)
    score = 0
    reasons: list[str] = []

    direct_hits = [keyword for keyword in keywords if keyword and keyword in text]
    if direct_hits:
        score += 6
        reasons.append(f"direct keyword hit: {', '.join(direct_hits[:3])}")

    industry_hits = [name for name in industry_names if name and name in text]
    if industry_hits:
        score += 2
        reasons.append(f"industry hit: {', '.join(industry_hits[:2])}")

    matched_business_terms = [term for term in business_terms if term and len(term) >= 2 and term in text]
    if matched_business_terms:
        score += min(4, len(matched_business_terms))
        reasons.append(f"business-term hit: {', '.join(matched_business_terms[:3])}")

    if any(token in text for token in ("新游", "版号", "上线", "测试", "影视", "短剧", "游戏")):
        score += 1
        reasons.append("generic entertainment/product catalyst wording")

    return score, "; ".join(reasons) if reasons else "no obvious match"


def _get_relevance_llm():
    config = get_config()
    if not config.get("a_share_news_use_llm_relevance", True):
        return None
    try:
        client = create_llm_client(
            provider=config["llm_provider"],
            model=config["quick_think_llm"],
            base_url=config.get("backend_url"),
            reasoning_effort=config.get("openai_reasoning_effort"),
            thinking_level=config.get("google_thinking_level"),
            effort=config.get("anthropic_effort"),
        )
        llm = client.get_llm()
        return llm.with_structured_output(_NewsRelevanceDecision)
    except Exception as exc:  # noqa: BLE001
        logger.warning("A-share news relevance LLM unavailable, falling back to heuristics: %s", exc)
        return None


def _llm_rerank_news_candidates(
    candidates: pd.DataFrame,
    ticker: str,
    company_context: dict[str, object],
) -> pd.DataFrame:
    llm = _get_relevance_llm()
    if llm is None or candidates.empty:
        return candidates

    company_label = ", ".join([str(item) for item in company_context.get("keywords", [])[:5]])
    industry_label = ", ".join([str(item) for item in company_context.get("industry_names", [])[:3]])
    business_label = ", ".join([str(item) for item in company_context.get("business_terms", [])[:6]])
    decisions: list[dict[str, object]] = []

    for idx, row in candidates.iterrows():
        title = str(row.get("新闻标题") or row.get("标题") or "")
        summary = str(row.get("新闻内容") or row.get("摘要") or row.get("内容") or "")
        prompt = (
            f"Ticker: {ticker}\n"
            f"Known company names / aliases: {company_label}\n"
            f"Industry labels: {industry_label}\n"
            f"Business clues: {business_label}\n"
            f"Article title: {title}\n"
            f"Article summary: {summary}\n\n"
            "Decide whether this article is materially relevant to the company. "
            "Mark relevant=true when the article is directly about the company, its products, "
            "its projects, its subsidiaries, its securities activity, or a clearly attributable catalyst. "
            "Mark relevant=false when the link is only broad sector noise or ambiguous macro chatter."
        )
        try:
            result = llm.invoke(prompt)
            decisions.append(
                {
                    "idx": idx,
                    "relevant": bool(result.relevant),
                    "confidence": int(result.confidence),
                    "reason": str(result.reason),
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("A-share news relevance LLM failed on one candidate, using heuristic fallback: %s", exc)
            return candidates

    decision_df = pd.DataFrame(decisions)
    if decision_df.empty:
        return candidates
    relevant = decision_df[decision_df["relevant"]].copy()
    if relevant.empty:
        return candidates.head(5)
    relevant = relevant.sort_values(["confidence"], ascending=False)
    ranked = candidates.loc[relevant["idx"].tolist()].copy()
    ranked["相关性说明"] = relevant["reason"].tolist()
    ranked["LLM相关性置信度"] = relevant["confidence"].tolist()
    return ranked


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


def _infer_a_share_board_profile(ticker: str) -> tuple[str, str, str]:
    normalized = normalize_ashare_symbol(ticker)
    plain = to_plain_symbol(normalized)
    if normalized.endswith(".BJ"):
        return (
            "Beijing Stock Exchange",
            "30%",
            "Beijing-board names can be materially more volatile and less liquid than the main boards.",
        )
    if plain.startswith(("688", "689")):
        return (
            "STAR Market (科创板)",
            "20%",
            "STAR names follow a wider daily limit regime and can move more sharply around theme and policy catalysts.",
        )
    if plain.startswith(("300", "301")):
        return (
            "ChiNext (创业板)",
            "20%",
            "ChiNext names follow a wider daily limit regime and often carry higher momentum as well as sharper drawdown risk.",
        )
    return (
        "Main Board",
        "10%",
        "Main-board names usually follow the standard A-share daily limit regime unless special treatment applies.",
    )


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
    company_context = _collect_company_context_for_news(ticker)
    keywords = [str(item) for item in company_context.get("keywords", [])]
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

    company_news_df = _fetch_keyword_news_df(ticker, start_date, end_date, keywords)
    if not company_news_df.empty:
        company_news_df = company_news_df.copy()
        heuristic_scores = []
        heuristic_reasons = []
        for _, row in company_news_df.iterrows():
            score, reason = _heuristic_news_relevance_score(row, company_context)
            heuristic_scores.append(score)
            heuristic_reasons.append(reason)
        company_news_df["HeuristicScore"] = heuristic_scores
        company_news_df["HeuristicReason"] = heuristic_reasons
        company_news_df = company_news_df.sort_values(["HeuristicScore", "发布时间"], ascending=[False, False])

        rerank_top_k = int(get_config().get("a_share_news_llm_rerank_top_k", 12))
        reranked_head = _llm_rerank_news_candidates(company_news_df.head(rerank_top_k), ticker, company_context)
        tail = company_news_df.iloc[rerank_top_k:]
        company_news_df = pd.concat([reranked_head, tail], ignore_index=True)
        if "LLM相关性置信度" in company_news_df.columns:
            company_news_df = company_news_df.sort_values(
                ["LLM相关性置信度", "HeuristicScore", "发布时间"],
                ascending=[False, False, False],
            )
        else:
            company_news_df = company_news_df.sort_values(["HeuristicScore", "发布时间"], ascending=[False, False])

        candidate_limit = int(get_config().get("a_share_news_candidate_limit", 30))
        company_news_df = company_news_df.head(candidate_limit)
        formatted_columns = [
            "发布时间",
            "文章来源",
            "匹配关键词",
            "HeuristicScore",
            "HeuristicReason",
            "LLM相关性置信度",
            "相关性说明",
            "新闻标题",
            "新闻内容",
            "新闻链接",
        ]
        formatted = company_news_df.loc[:, [col for col in formatted_columns if col in company_news_df.columns]].copy()
        if "新闻内容" in formatted.columns:
            formatted["新闻内容"] = formatted["新闻内容"].map(_safe_truncate)
        sections.append(_format_table(formatted, f"# A-share company news for {normalized}", rows=20))

    keyword_news_fetcher = getattr(ak, "stock_info_global_em", None)
    if keyword_news_fetcher is not None and keywords:
        try:
            df = _call_akshare_api(keyword_news_fetcher)
            if not df.empty and "发布时间" in df.columns:
                df["发布时间"] = parse_date_column(df["发布时间"])
                start = pd.Timestamp(start_date)
                end = pd.Timestamp(end_date) + timedelta(days=1) - timedelta(seconds=1)
                df = df[(df["发布时间"] >= start) & (df["发布时间"] <= end)]
                matched = _match_keyword_news_rows(
                    df,
                    keywords,
                    ["标题", "摘要", "内容"],
                )
                if not matched.empty:
                    matched = matched.copy()
                    matched["匹配关键词"] = matched.apply(
                        lambda row: next(
                            (
                                keyword for keyword in keywords
                                if keyword and keyword in " ".join(
                                    str(row.get(col, "")) for col in ["标题", "摘要", "内容"]
                                )
                            ),
                            "",
                        ),
                        axis=1,
                    )
                    heuristic_scores = []
                    heuristic_reasons = []
                    for _, row in matched.iterrows():
                        score, reason = _heuristic_news_relevance_score(row, company_context)
                        heuristic_scores.append(score)
                        heuristic_reasons.append(reason)
                    matched["HeuristicScore"] = heuristic_scores
                    matched["HeuristicReason"] = heuristic_reasons
                    matched = matched.sort_values(["HeuristicScore", "发布时间"], ascending=[False, False])
                    rerank_top_k = int(get_config().get("a_share_news_llm_rerank_top_k", 12))
                    reranked_head = _llm_rerank_news_candidates(matched.head(rerank_top_k), ticker, company_context)
                    tail = matched.iloc[rerank_top_k:]
                    matched = pd.concat([reranked_head, tail], ignore_index=True)
                    if "LLM相关性置信度" in matched.columns:
                        matched = matched.sort_values(
                            ["LLM相关性置信度", "HeuristicScore", "发布时间"],
                            ascending=[False, False, False],
                        )
                    formatted = matched.loc[:, [col for col in ["发布时间", "匹配关键词", "HeuristicScore", "HeuristicReason", "LLM相关性置信度", "相关性说明", "标题", "摘要", "链接"] if col in matched.columns]].copy()
                    if "摘要" in formatted.columns:
                        formatted["摘要"] = formatted["摘要"].map(lambda value: _safe_truncate(value, 180))
                    sections.append(
                        _format_table(
                            formatted,
                            f"## Keyword-linked company mentions ({', '.join(keywords[:6])})",
                            rows=20,
                        )
                    )
        except Exception:  # noqa: BLE001
            pass

    try:
        market_context = get_market_news(end_date, look_back_days=max((pd.Timestamp(end_date) - pd.Timestamp(start_date)).days, 3), limit=6)
    except Exception:  # noqa: BLE001
        market_context = ""
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


def _fetch_company_announcements_df(
    ticker: str,
    start_date: str,
    end_date: str,
    category: str = "全部",
) -> tuple[pd.DataFrame, list[str]]:
    normalized_symbol = normalize_ashare_symbol(ticker)
    plain_symbol = to_plain_symbol(ticker)
    fetcher = getattr(ak, "stock_notice_report", None)
    if fetcher is None:
        return pd.DataFrame(), [f"A-share announcements API unavailable for {normalized_symbol}"]

    frames = []
    errors = []
    for date_value in get_date_range(start_date, end_date):
        try:
            daily = _call_akshare_api(fetcher, symbol=category, date=format_date_for_api(date_value))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{date_value}: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")
            continue
        if daily.empty:
            continue

        code_col = next((col for col in ["代码", "证券代码", "股票代码"] if col in daily.columns), None)
        if code_col is not None:
            matched = daily[daily[code_col].astype(str).str.upper() == plain_symbol]
        else:
            title_col = next((col for col in ["公告标题", "标题", "名称"] if col in daily.columns), None)
            matched = daily if title_col is not None else pd.DataFrame()
        if not matched.empty:
            frames.append(matched)

    if not frames:
        return pd.DataFrame(), errors

    combined = pd.concat(frames, ignore_index=True)
    date_col = next((col for col in ["公告日期", "NOTICE_DATE", "日期", "date"] if col in combined.columns), None)
    if date_col:
        combined[date_col] = parse_date_column(combined[date_col])
        combined = combined.sort_values(date_col, ascending=False)
    title_col = next((col for col in ["公告标题", "标题", "名称"] if col in combined.columns), None)
    dedupe_cols = [col for col in [title_col, date_col] if col]
    if dedupe_cols:
        combined = combined.drop_duplicates(subset=dedupe_cols)
    return combined, errors


def get_company_announcements(ticker: str, start_date: str, end_date: str, category: str = "全部") -> str:
    normalized_symbol = normalize_ashare_symbol(ticker)
    combined, errors = _fetch_company_announcements_df(ticker, start_date, end_date, category)
    if combined.empty:
        if errors:
            return (
                f"{normalized_symbol} 在 {start_date} 到 {end_date} 之间未能稳定获取公告数据。\n\n"
                + "\n".join(errors[:5])
            )
        return f"{normalized_symbol} 在 {start_date} 到 {end_date} 之间没有匹配的公告。"

    date_col = next((col for col in ["公告日期", "NOTICE_DATE", "日期", "date"] if col in combined.columns), None)
    type_col = next((col for col in ["公告类型", "类型", "notice_type"] if col in combined.columns), None)
    title_col = next((col for col in ["公告标题", "标题", "名称"] if col in combined.columns), None)
    link_col = next((col for col in ["网址", "链接", "url"] if col in combined.columns), None)

    formatted = combined.loc[:, [col for col in [date_col, type_col, title_col, link_col] if col]].head(20).copy()
    if date_col and date_col in formatted.columns:
        formatted[date_col] = pd.to_datetime(formatted[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
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
        fallback_df, fallback_errors = _fetch_company_announcements_df(ticker, start_date, end_date, "全部")
        errors.extend(fallback_errors[:5])
        if not fallback_df.empty:
            any_hits = True
            working = fallback_df.copy()
            date_col = next((c for c in ["公告日期", "NOTICE_DATE", "日期", "date"] if c in working.columns), None)
            title_col = next((c for c in ["公告标题", "标题", "名称"] if c in working.columns), None)
            type_col = next((c for c in ["公告类型", "类型", "notice_type"] if c in working.columns), None)

            sections.append("## 公告回退事件流")
            sections.append(f"- Count: {len(working)}")
            latest_rows = working.head(8)
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


def get_news_source_status(ticker: str, start_date: str, end_date: str, curr_date: str) -> str:
    """Summarise whether A-share news inputs came from primary sources, fallbacks, or no data."""
    normalized = normalize_ashare_symbol(ticker)
    news_text = get_news(ticker, start_date, end_date)
    market_text = get_market_news(
        curr_date,
        look_back_days=max((pd.Timestamp(end_date) - pd.Timestamp(start_date)).days, 3),
        limit=6,
    )
    announcement_text = get_company_announcements(ticker, start_date, end_date)
    event_text = get_company_event_signals(ticker, start_date, end_date)
    caixin_text = get_caixin_news(ticker)

    sections = [f"# A-share news source status for {normalized}", ""]

    company_status = "unknown"
    company_evidence = ""
    if "## 券商研报（个股专项）" in news_text:
        company_status = "primary"
        company_evidence = "券商研报（个股专项）"
    elif f"# A-share company news for {normalized}" in news_text:
        company_status = "fallback"
        company_evidence = "东方财富个股新闻"
    elif news_text.startswith(f"# A-share news pack for {normalized}") and "# A-share market and policy news" in news_text:
        company_status = "market-context-only"
        company_evidence = "仅拼入市场/政策新闻，未见公司专项新闻段"
    elif news_text == f"No A-share news found for {normalized} between {start_date} and {end_date}":
        company_status = "no-data"
        company_evidence = "未找到公司新闻"
    sections.append(f"- Company news: {company_status}" + (f" | source={company_evidence}" if company_evidence else ""))

    market_status = "unknown"
    market_evidence = ""
    if market_text.startswith("# A-share market and policy news"):
        market_status = "available"
        market_evidence = "东方财富市场/政策快讯"
    elif "没有可用的市场快讯" in market_text or "未获取到 A 股市场与宏观快讯" in market_text:
        market_status = "no-data"
        market_evidence = _safe_truncate(market_text, 80)
    elif "API unavailable" in market_text:
        market_status = "unavailable"
        market_evidence = _safe_truncate(market_text, 80)
    sections.append(f"- Market / policy news: {market_status}" + (f" | source={market_evidence}" if market_evidence else ""))

    announcement_status = "unknown"
    announcement_evidence = ""
    if announcement_text.startswith(f"# A-share company announcements for {normalized}"):
        announcement_status = "available"
        announcement_evidence = "东方财富公告中心"
    elif "没有匹配的公告" in announcement_text:
        announcement_status = "no-data"
        announcement_evidence = "时间窗口内未匹配到公告"
    elif "未能稳定获取公告数据" in announcement_text:
        announcement_status = "retrieval-unstable"
        announcement_evidence = "公告接口返回不稳定"
    sections.append(f"- Company announcements: {announcement_status}" + (f" | source={announcement_evidence}" if announcement_evidence else ""))

    event_status = "unknown"
    event_evidence = ""
    if "## 公告回退事件流" in event_text:
        event_status = "fallback"
        event_evidence = "从通用公告流回退生成事件标签"
    elif event_text.startswith(f"# A-share company event signals for {normalized}"):
        event_status = "primary"
        event_evidence = "个股公告事件流"
    elif "没有可识别的事件信号" in event_text:
        event_status = "no-data"
        event_evidence = "没有可分类事件"
    elif "未能稳定获取事件信号" in event_text:
        event_status = "retrieval-unstable"
        event_evidence = "事件接口返回不稳定"
    sections.append(f"- Event signals: {event_status}" + (f" | source={event_evidence}" if event_evidence else ""))

    caixin_status = "optional-empty"
    caixin_evidence = ""
    if caixin_text.startswith(f"# 财新新闻 — {normalized}"):
        caixin_status = "available"
        caixin_evidence = "财新新闻"
    elif "未找到" in caixin_text:
        caixin_status = "optional-empty"
        caixin_evidence = "最近样本中未命中该股票"
    elif "未获取到财新新闻数据" in caixin_text:
        caixin_status = "retrieval-unstable"
        caixin_evidence = "财新新闻接口空返回"
    elif "API unavailable" in caixin_text:
        caixin_status = "unavailable"
        caixin_evidence = "环境里没有可用财新接口"
    sections.append(f"- Caixin supplement: {caixin_status}" + (f" | source={caixin_evidence}" if caixin_evidence else ""))

    sections.extend(
        [
            "",
            "## Interpretation",
            "- `primary` means the preferred source produced ticker-specific content.",
            "- `fallback` means the preferred source did not hold and a secondary source was used.",
            "- `market-context-only` means the company-specific news pack was empty but broader market / policy context was still available.",
            "- `retrieval-unstable` means the system hit an interface or structure problem, so missing content should not be read as evidence of absence.",
            "- `no-data` means the query window returned no matching content from that source family.",
        ]
    )
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


def get_unusual_trading_activity(ticker: str, start_date: str, end_date: str) -> str:
    """Summarise 龙虎榜 / unusual trading activity for an A-share ticker."""
    normalized = normalize_ashare_symbol(ticker)
    plain = to_plain_symbol(ticker)
    sections = [f"# A-share unusual trading activity for {normalized}", ""]
    errors = []

    detail_fetcher = getattr(ak, "stock_lhb_detail_em", None)
    if detail_fetcher is not None:
        try:
            detail_df = _call_akshare_api(
                detail_fetcher,
                start_date=format_date_for_api(start_date),
                end_date=format_date_for_api(end_date),
            )
            if not detail_df.empty and "代码" in detail_df.columns:
                matched = detail_df[detail_df["代码"].astype(str).str.upper() == plain].copy()
                if not matched.empty:
                    sections.append("## LHB appearances")
                    sample_columns = [
                        col for col in ["上榜日", "名称", "涨跌幅", "龙虎榜净买额", "换手率", "上榜原因", "解读"]
                        if col in matched.columns
                    ]
                    sample = matched.loc[:, sample_columns].head(10) if sample_columns else matched.head(10)
                    sections.append(sample.to_csv(index=False))
                    if "龙虎榜净买额" in matched.columns:
                        values = pd.to_numeric(matched["龙虎榜净买额"], errors="coerce").dropna()
                        if not values.empty:
                            sections.append(
                                f"Signal: total sampled LHB net amount={values.sum():.2f}, mean={values.mean():.2f}"
                            )
                    if "上榜原因" in matched.columns:
                        reasons = _extract_text_values(matched, ["上榜原因"], limit=5)
                        if reasons:
                            sections.append(f"Signal: repeated listing reasons include {', '.join(reasons)}")
                    sections.append("")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"lhb_detail: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")

    date_fetcher = getattr(ak, "stock_lhb_stock_detail_date_em", None)
    side_fetcher = getattr(ak, "stock_lhb_stock_detail_em", None)
    if date_fetcher is not None and side_fetcher is not None:
        try:
            date_df = _call_akshare_api(date_fetcher, symbol=plain)
            if not date_df.empty:
                date_column = next((col for col in date_df.columns if "日期" in str(col)), None)
                if date_column:
                    parsed_dates = pd.to_datetime(date_df[date_column], errors="coerce").dropna()
                    eligible = [
                        ts.strftime("%Y%m%d")
                        for ts in parsed_dates
                        if pd.Timestamp(start_date) <= ts <= pd.Timestamp(end_date)
                    ]
                    if eligible:
                        detail_date = sorted(eligible)[-1]
                        sections.append(f"## Seat detail snapshot ({detail_date})")
                        for flag in ["买入", "卖出"]:
                            try:
                                side_df = _call_akshare_api(side_fetcher, symbol=plain, date=detail_date, flag=flag)
                            except Exception as exc:  # noqa: BLE001
                                errors.append(f"lhb_side_{flag}: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")
                                continue
                            if side_df.empty:
                                continue
                            sample_columns = [
                                col for col in ["营业部名称", "买入金额", "卖出金额", "净额", "金额", "上榜日"]
                                if col in side_df.columns
                            ]
                            sample = side_df.loc[:, sample_columns].head(5) if sample_columns else side_df.head(5)
                            sections.append(f"### {flag}席位")
                            sections.append(sample.to_csv(index=False))
                        sections.append("")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"lhb_stock_detail_date: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")

    institution_fetcher = getattr(ak, "stock_lhb_stock_statistic_em", None)
    if institution_fetcher is not None:
        try:
            stats_df = _call_akshare_api(institution_fetcher, symbol="近一月")
            if not stats_df.empty and "代码" in stats_df.columns:
                matched = stats_df[stats_df["代码"].astype(str).str.upper() == plain].copy()
                if not matched.empty:
                    sections.append("## Recent LHB statistics")
                    sample_columns = [
                        col for col in [
                            "最近上榜日", "上榜次数", "龙虎榜净买额", "买方机构次数",
                            "卖方机构次数", "机构买入净额", "近1个月涨跌幅"
                        ]
                        if col in matched.columns
                    ]
                    sample = matched.loc[:, sample_columns].head(3) if sample_columns else matched.head(3)
                    sections.append(sample.to_csv(index=False))
                    sections.append("")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"lhb_stat: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")

    if len(sections) == 2:
        if errors:
            return f"未能稳定获取 {normalized} 的龙虎榜 / 异动席位信息。\n\n" + "\n".join(errors[:5])
        return f"未获取到 {normalized} 的龙虎榜 / 异动席位信息。"

    sections.append("## Interpretation")
    sections.append("- Use repeated appearances, net buy/sell direction, and seat concentration to judge whether short-term price action may be flow-driven.")
    sections.append("- Treat 龙虎榜 signals as short-horizon trading context rather than standalone fundamental evidence.")
    if errors:
        sections.append("")
        sections.append("## Data retrieval notes")
        sections.extend(f"- {item}" for item in errors[:5])
    return "\n".join(sections).strip()


def get_lhb_seat_profile_context(ticker: str, start_date: str, end_date: str) -> str:
    """Profile 龙虎榜 seat participation for a ticker over a date range."""
    normalized = normalize_ashare_symbol(ticker)
    plain = to_plain_symbol(ticker)
    sections = [f"# A-share LHB seat profile context for {normalized}", ""]
    errors = []

    date_fetcher = getattr(ak, "stock_lhb_stock_detail_date_em", None)
    side_fetcher = getattr(ak, "stock_lhb_stock_detail_em", None)
    if date_fetcher is None or side_fetcher is None:
        return f"A-share LHB seat-profile API unavailable for {normalized}."

    try:
        date_df = _call_akshare_api(date_fetcher, symbol=plain)
    except Exception as exc:  # noqa: BLE001
        return f"未能稳定获取 {normalized} 的龙虎榜席位画像。\n\n{type(exc).__name__}: {_safe_truncate(str(exc), 120)}"

    if date_df.empty:
        return f"未获取到 {normalized} 的龙虎榜席位画像。"

    date_column = next((col for col in date_df.columns if "日期" in str(col)), None)
    if date_column is None:
        return f"未获取到 {normalized} 的龙虎榜席位日期字段。"

    parsed_dates = pd.to_datetime(date_df[date_column], errors="coerce").dropna()
    eligible = [
        ts.strftime("%Y%m%d")
        for ts in parsed_dates
        if pd.Timestamp(start_date) <= ts <= pd.Timestamp(end_date)
    ]
    if not eligible:
        return f"{start_date} 到 {end_date} 之间没有可用的龙虎榜席位画像。"

    latest_date = sorted(eligible)[-1]
    sections.append(f"## Latest profiled date")
    sections.append(f"- {latest_date}")
    sections.append("")

    summary_rows = []
    top_seats: list[str] = []
    for flag in ["买入", "卖出"]:
        try:
            side_df = _call_akshare_api(side_fetcher, symbol=plain, date=latest_date, flag=flag)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"lhb_seat_{flag}: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")
            continue
        if side_df.empty:
            continue

        seat_col = next((col for col in ["营业部名称", "席位名称"] if col in side_df.columns), None)
        amount_candidates = ["净额", "买入金额", "卖出金额", "金额"]
        amount_col = _find_first_numeric_column(side_df, amount_candidates)
        if seat_col is None or amount_col is None:
            continue

        working = side_df.copy()
        working[amount_col] = pd.to_numeric(working[amount_col], errors="coerce")
        working = working.dropna(subset=[amount_col])
        if working.empty:
            continue

        working = working.sort_values(amount_col, ascending=False)
        top_sample = working.loc[:, [seat_col, amount_col]].head(5)
        sections.append(f"## {flag}席位画像")
        sections.append(top_sample.to_csv(index=False))

        institution_hits = int(working[seat_col].astype(str).str.contains("机构专用", na=False).sum())
        total_amount = float(working[amount_col].abs().sum())
        top3_amount = float(working[amount_col].abs().head(3).sum())
        concentration = top3_amount / total_amount if total_amount else 0.0
        summary_rows.append(
            {
                "Side": flag,
                "InstitutionSeats": institution_hits,
                "Top3ConcentrationPct": round(concentration * 100, 2),
                "SeatCount": int(len(working.index)),
            }
        )
        top_seats.extend(working[seat_col].astype(str).head(3).tolist())
        sections.append(
            f"Signal: {flag} side institution seats={institution_hits}, top3 concentration={concentration * 100:.2f}%."
        )
        sections.append("")

    if not summary_rows:
        if errors:
            return f"未能稳定获取 {normalized} 的龙虎榜席位画像。\n\n" + "\n".join(errors[:5])
        return f"未获取到 {normalized} 的龙虎榜席位画像。"

    summary_df = pd.DataFrame(summary_rows)
    sections.append("## Seat-profile summary")
    sections.append(summary_df.to_csv(index=False))

    buy_row = next((row for row in summary_rows if row["Side"] == "买入"), None)
    sell_row = next((row for row in summary_rows if row["Side"] == "卖出"), None)
    if buy_row and buy_row["InstitutionSeats"] > 0:
        sections.append("- Signal: institutional participation is visible on the buy side.")
    if sell_row and sell_row["InstitutionSeats"] > 0:
        sections.append("- Signal: institutional participation is visible on the sell side.")
    if any(row["Top3ConcentrationPct"] >= 60 for row in summary_rows):
        sections.append("- Signal: seat concentration is high, so short-horizon price action may be dominated by a few active participants.")
    else:
        sections.append("- Signal: seat concentration looks more dispersed, which lowers the odds of a single-seat squeeze dominating the move.")
    if top_seats:
        sections.append(f"- Signal: prominent seats include {', '.join(top_seats[:5])}.")

    if errors:
        sections.extend(["", "## Data retrieval notes"])
        sections.extend(f"- {item}" for item in errors[:5])
    return "\n".join(sections).strip()


def get_capital_flow_regime_context(ticker: str, curr_date: str, window: int = 10) -> str:
    """Summarise medium-horizon capital-flow regime for an A-share ticker."""
    normalized = normalize_ashare_symbol(ticker)
    plain = to_plain_symbol(ticker)
    exchange = get_ashare_exchange(ticker)
    market_code = exchange.lower()
    sections = [f"# A-share capital flow regime context for {normalized}", ""]
    errors = []

    fund_flow_fetcher = getattr(ak, "stock_individual_fund_flow", None)
    if fund_flow_fetcher is not None:
        try:
            df = _call_akshare_api(fund_flow_fetcher, stock=plain, market=market_code)
            if not df.empty:
                working = df.copy().head(window)
                col = _find_first_numeric_column(working, ["主力净流入-净额", "主力净流入净额"])
                if col:
                    values = pd.to_numeric(working[col], errors="coerce").dropna()
                    if not values.empty:
                        pos = int((values > 0).sum())
                        neg = int((values < 0).sum())
                        sections.append("## Main fund-flow regime")
                        sections.append(f"- Positive sessions in sample: {pos}")
                        sections.append(f"- Negative sessions in sample: {neg}")
                        sections.append(f"- Sample mean: {values.mean():.2f}")
                        sections.append(f"- Sample sum: {values.sum():.2f}")
                        if pos - neg >= max(2, window // 4):
                            sections.append("- Signal: medium-horizon main-fund-flow regime looks supportive.")
                        elif neg - pos >= max(2, window // 4):
                            sections.append("- Signal: medium-horizon main-fund-flow regime looks weak.")
                        else:
                            sections.append("- Signal: medium-horizon main-fund-flow regime looks mixed.")
                        sections.append("")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"fund_flow_regime: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")

    northbound_fetcher = getattr(ak, "stock_hsgt_individual_em", None)
    if northbound_fetcher is not None:
        try:
            df = _call_akshare_api(northbound_fetcher, symbol=plain)
            if not df.empty:
                working = df.copy().head(window)
                col = _find_first_numeric_column(working, ["持股数量", "HOLD_SHARES", "持股市值", "HOLD_MARKET_CAP"])
                if col:
                    values = pd.to_numeric(working[col], errors="coerce").dropna()
                    if len(values) >= 2:
                        delta = float(values.iloc[0] - values.iloc[-1])
                        sections.append("## Northbound regime")
                        sections.append(f"- Window change on {col}: {delta:.2f}")
                        sections.append(f"- Latest value: {values.iloc[0]:.2f}")
                        if delta > 0:
                            sections.append("- Signal: northbound positioning has been building over the sampled window.")
                        elif delta < 0:
                            sections.append("- Signal: northbound positioning has been fading over the sampled window.")
                        else:
                            sections.append("- Signal: northbound positioning is broadly flat over the sampled window.")
                        sections.append("")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"northbound_regime: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")

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
                    financing_col = _find_first_numeric_column(matched, ["融资余额", "融资买入额"])
                    short_col = _find_first_numeric_column(matched, ["融券余额", "融券余量"])
                    sections.append("## Margin regime")
                    if financing_col:
                        val = pd.to_numeric(matched[financing_col], errors="coerce").dropna()
                        if not val.empty:
                            sections.append(f"- Latest {financing_col}: {val.iloc[0]:.2f}")
                            sections.append("- Signal: margin-financing should be read alongside price trend to judge leverage appetite.")
                    if short_col:
                        val = pd.to_numeric(matched[short_col], errors="coerce").dropna()
                        if not val.empty:
                            sections.append(f"- Latest {short_col}: {val.iloc[0]:.2f}")
                            sections.append("- Signal: short-side balance helps judge whether skepticism is materially elevated.")
                    sections.append("")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"margin_regime: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")

    if len(sections) == 2:
        if errors:
            return f"未能稳定获取 {normalized} 的资金面周期信息。\n\n" + "\n".join(errors[:5])
        return f"未获取到 {normalized} 的资金面周期信息。"

    if errors:
        sections.append("## Data retrieval notes")
        sections.extend(f"- {item}" for item in errors[:5])
    return "\n".join(sections).strip()


def get_trading_constraint_context(ticker: str, curr_date: str) -> str:
    """Summarise A-share board rules and special-treatment constraints."""
    normalized = normalize_ashare_symbol(ticker)
    plain = to_plain_symbol(normalized)
    board_label, price_limit, board_note = _infer_a_share_board_profile(normalized)
    sections = [f"# A-share trading constraint context for {normalized}", ""]
    errors = []

    short_name = ""
    profile_fetchers = [
        getattr(ak, "stock_profile_cninfo", None),
        getattr(ak, "stock_individual_info_em", None),
    ]
    for fetcher in profile_fetchers:
        if fetcher is None:
            continue
        try:
            profile_df = _call_akshare_api(fetcher, symbol=plain)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"profile: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")
            continue
        if profile_df.empty:
            continue
        names = _extract_text_values(profile_df, ["A股简称", "股票简称", "证券简称", "名称"], limit=1)
        if names:
            short_name = names[0]
            break

    is_st = bool(re.search(r"(^|[* ])ST", short_name.upper())) or "退" in short_name

    sections.append("## Board profile")
    if short_name:
        sections.append(f"- Security short name: {short_name}")
    sections.append(f"- Board: {board_label}")
    sections.append(f"- Daily price-limit regime: {price_limit}")
    sections.append(f"- Trade settlement reminder: T+1 sell constraint still applies to newly bought A-shares.")
    sections.append("")

    sections.append("## Constraint read")
    if is_st:
        sections.append("- Special treatment flag: ST / *ST detected from the security short name.")
        sections.append("- Constraint implication: ST / *ST names often face a tighter 5% daily price limit and elevated delisting / headline risk.")
    else:
        sections.append("- Special treatment flag: no ST / *ST signal detected from the fetched security short name.")
        sections.append(f"- Constraint implication: base board rule set appears to be the {price_limit} daily price-limit regime.")
    sections.append(f"- Board implication: {board_note}")
    sections.append("- Exit implication: A-share liquidity can deteriorate quickly near limit-up / limit-down states or suspension-style headlines.")

    if errors:
        sections.extend(["", "## Data retrieval notes"])
        sections.extend(f"- {item}" for item in errors[:5])
    return "\n".join(sections).strip()


def get_limit_move_sentiment_context(curr_date: str) -> str:
    """Summarise A-share limit-up / limit-down market temperature."""
    query_date = format_date_for_api(curr_date)
    sections = [f"# A-share limit-move sentiment context for {curr_date}", ""]
    errors = []

    limit_up_df = pd.DataFrame()
    limit_down_df = pd.DataFrame()
    limit_up_fetcher = getattr(ak, "stock_zt_pool_em", None)
    limit_down_fetcher = getattr(ak, "stock_dt_pool_em", None)

    if limit_up_fetcher is not None:
        try:
            limit_up_df = _call_akshare_api(limit_up_fetcher, date=query_date)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"limit_up: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")
    if limit_down_fetcher is not None:
        try:
            limit_down_df = _call_akshare_api(limit_down_fetcher, date=query_date)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"limit_down: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")

    up_count = len(limit_up_df.index) if not limit_up_df.empty else 0
    down_count = len(limit_down_df.index) if not limit_down_df.empty else 0

    if up_count:
        sections.append("## Limit-up pool")
        sections.append(f"- Count: {up_count}")
        sample_cols = [col for col in ["代码", "名称", "所属行业", "涨停原因类别", "连板数"] if col in limit_up_df.columns]
        sample = limit_up_df.loc[:, sample_cols].head(5) if sample_cols else limit_up_df.head(5)
        sections.append(sample.to_csv(index=False))
        reasons = _extract_text_values(limit_up_df, ["涨停原因类别", "所属概念", "所属行业"], limit=5)
        if reasons:
            sections.append(f"Signal: limit-up leadership themes include {', '.join(reasons[:5])}.")
        sections.append("")

    if down_count:
        sections.append("## Limit-down pool")
        sections.append(f"- Count: {down_count}")
        sample_cols = [col for col in ["代码", "名称", "所属行业", "跌停原因", "连续跌停"] if col in limit_down_df.columns]
        sample = limit_down_df.loc[:, sample_cols].head(5) if sample_cols else limit_down_df.head(5)
        sections.append(sample.to_csv(index=False))
        reasons = _extract_text_values(limit_down_df, ["跌停原因", "所属行业", "所属概念"], limit=5)
        if reasons:
            sections.append(f"Signal: limit-down stress themes include {', '.join(reasons[:5])}.")
        sections.append("")

    if up_count or down_count:
        sections.append("## Temperature read")
        if up_count >= max(down_count * 2, 10):
            sections.append("- Signal: speculative risk appetite looks hot, with limit-up breadth dominating limit-down stress.")
        elif down_count >= max(up_count * 2, 5):
            sections.append("- Signal: downside stress looks elevated, with limit-down breadth overwhelming upside momentum.")
        else:
            sections.append("- Signal: limit-up and limit-down breadth look mixed, suggesting a more selective tape.")
        sections.append(
            f"- Breadth snapshot: limit-up count={up_count}, limit-down count={down_count}, ratio={(up_count / max(down_count, 1)):.2f}."
        )
    elif errors:
        return "未能稳定获取 A 股涨跌停情绪信息。\n\n" + "\n".join(errors[:5])
    else:
        return "未获取到可用的 A 股涨跌停情绪信息。"

    if errors:
        sections.extend(["", "## Data retrieval notes"])
        sections.extend(f"- {item}" for item in errors[:5])
    return "\n".join(sections).strip()


def get_policy_signal_context(curr_date: str, look_back_days: int = 7, limit: int = 20) -> str:
    """Summarise recent China market-policy and regulatory signal flow."""
    fetcher = getattr(ak, "stock_info_global_em", None)
    if fetcher is None:
        return "A-share policy news API unavailable."

    try:
        df = _call_akshare_api(fetcher)
    except Exception as exc:  # noqa: BLE001
        return f"未能稳定获取 A 股政策与监管语境。\n\n{type(exc).__name__}: {_safe_truncate(str(exc), 120)}"
    if df.empty:
        return "未获取到可用的 A 股政策与监管语境。"

    filtered = df.copy()
    if "发布时间" in filtered.columns:
        filtered["发布时间"] = parse_date_column(filtered["发布时间"])
        end = pd.Timestamp(curr_date) + timedelta(days=1) - timedelta(seconds=1)
        start = end - timedelta(days=look_back_days)
        filtered = filtered[(filtered["发布时间"] >= start) & (filtered["发布时间"] <= end)]
        filtered = filtered.sort_values("发布时间", ascending=False)

    if filtered.empty:
        return f"{curr_date} 前 {look_back_days} 天没有可用的政策与监管快讯。"

    text_cols = [col for col in ["标题", "摘要"] if col in filtered.columns]
    if not text_cols:
        return "可用市场快讯中没有足够的政策文本字段。"

    working = filtered.head(limit).copy()
    combined = (
        working[text_cols].fillna("").astype(str).agg(" ".join, axis=1)
    )
    policy_mask = combined.map(
        lambda text: any(keyword in text for keyword in POLICY_TOPIC_KEYWORDS + POLICY_SUPPORTIVE_KEYWORDS + POLICY_RESTRICTIVE_KEYWORDS)
    )
    working = working.loc[policy_mask].copy()
    combined = combined.loc[policy_mask]

    if working.empty:
        return "近期市场快讯里没有明显的政策 / 监管主线。"

    supportive = int(combined.map(lambda text: any(keyword in text for keyword in POLICY_SUPPORTIVE_KEYWORDS)).sum())
    restrictive = int(combined.map(lambda text: any(keyword in text for keyword in POLICY_RESTRICTIVE_KEYWORDS)).sum())

    topic_counts: dict[str, int] = {}
    for text in combined:
        for keyword in POLICY_TOPIC_KEYWORDS:
            if keyword in text:
                topic_counts[keyword] = topic_counts.get(keyword, 0) + 1

    sections = [f"# A-share policy signal context for {curr_date}", ""]
    sections.append("## Policy / regulation headlines")
    sample_cols = [col for col in ["发布时间", "标题", "摘要", "链接"] if col in working.columns]
    sample = working.loc[:, sample_cols].head(min(limit, 8)).copy() if sample_cols else working.head(min(limit, 8))
    if "摘要" in sample.columns:
        sample["摘要"] = sample["摘要"].map(lambda value: _safe_truncate(value, 140))
    sections.append(sample.to_csv(index=False))
    sections.append("")

    sections.append("## Policy tone read")
    sections.append(f"- Supportive-policy headline count: {supportive}")
    sections.append(f"- Restrictive / regulatory-pressure headline count: {restrictive}")
    if supportive > restrictive:
        sections.append("- Signal: policy tone looks supportive on balance, which can help sector risk appetite and valuation tolerance.")
    elif restrictive > supportive:
        sections.append("- Signal: policy tone looks cautious / restrictive on balance, which can cap sentiment and increase compliance sensitivity.")
    else:
        sections.append("- Signal: policy tone looks mixed, so traders should avoid assuming a one-way macro tailwind.")

    if topic_counts:
        ordered_topics = sorted(topic_counts.items(), key=lambda item: item[1], reverse=True)[:5]
        sections.append(f"- Dominant policy topics: {', '.join(f'{topic}({count})' for topic, count in ordered_topics)}")
    return "\n".join(sections).strip()


def get_peer_comparison_context(ticker: str, curr_date: str, look_back_days: int = 20) -> str:
    """Compare an A-share ticker with a few industry/concept peers."""
    normalized = normalize_ashare_symbol(ticker)
    sections = [f"# A-share peer comparison context for {normalized}", ""]
    errors = []

    sector_text = get_sector_rotation_context(ticker, curr_date)
    peer_names: list[str] = []
    for line in sector_text.splitlines():
        if line.startswith("Signal: representative peers in "):
            peers = line.rsplit(": ", 1)[-1]
            peer_names.extend([item.strip() for item in peers.split(",") if item.strip()])
    peer_names = [name for name in peer_names if name][:4]

    start_date = (pd.Timestamp(curr_date) - pd.Timedelta(days=max(look_back_days * 3, 60))).strftime("%Y-%m-%d")
    target_df = _load_hist_df(ticker, start_date, curr_date)
    target_return, _ = _compute_window_return(target_df, look_back_days)

    if target_return is None:
        return f"未获取到 {normalized} 的同行对比信息。"

    sections.append("## Target return")
    sections.append(f"- {normalized} return over ~{look_back_days} calendar days: {target_return * 100:.2f}%")
    sections.append("")

    board_fetchers = [
        getattr(ak, "stock_board_industry_cons_em", None),
        getattr(ak, "stock_board_concept_cons_em", None),
    ]
    peer_map: dict[str, str] = {}
    for fetcher in board_fetchers:
        if fetcher is None:
            continue
        for line in sector_text.splitlines():
            if not line.startswith("## Industry board sample:") and not line.startswith("## Concept board sample:"):
                continue
            board_name = line.split(": ", 1)[1]
            try:
                board_df = _call_akshare_api(fetcher, symbol=board_name)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"peer_board_{board_name}: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")
                continue
            if board_df.empty:
                continue
            code_col = next((col for col in ["代码", "证券代码"] if col in board_df.columns), None)
            name_col = next((col for col in ["名称", "股票名称"] if col in board_df.columns), None)
            if code_col is None or name_col is None:
                continue
            for _, row in board_df.head(10).iterrows():
                name = str(row[name_col]).strip()
                code = str(row[code_col]).strip()
                if name and code and name not in peer_map and code != to_plain_symbol(ticker):
                    try:
                        peer_map[name] = normalize_ashare_symbol(code)
                    except ValueError:
                        continue

    comparison_rows = []
    for peer_name in peer_names:
        peer_symbol = peer_map.get(peer_name)
        if not peer_symbol:
            continue
        try:
            peer_df = _load_hist_df(peer_symbol, start_date, curr_date)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"peer_hist_{peer_symbol}: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")
            continue
        peer_return, _ = _compute_window_return(peer_df, look_back_days)
        if peer_return is None:
            continue
        comparison_rows.append(
            {
                "Peer": peer_name,
                "Ticker": peer_symbol,
                "ReturnPct": round(peer_return * 100, 2),
                "ExcessVsTargetPct": round((target_return - peer_return) * 100, 2),
            }
        )

    if comparison_rows:
        compare_df = pd.DataFrame(comparison_rows).sort_values("ReturnPct", ascending=False)
        sections.append("## Peer return comparison")
        sections.append(compare_df.to_csv(index=False))
        outperform = int((compare_df["ExcessVsTargetPct"] > 0).sum())
        underperform = int((compare_df["ExcessVsTargetPct"] < 0).sum())
        sections.append(
            f"Signal: target outperforms {outperform} sampled peers and lags {underperform} sampled peers over the window."
        )
        if outperform > underperform:
            sections.append("- Signal: peer-relative strength looks constructive.")
        elif underperform > outperform:
            sections.append("- Signal: peer-relative strength looks weak versus sampled peers.")
        else:
            sections.append("- Signal: peer-relative strength looks mixed versus sampled peers.")
    else:
        sections.append("## Peer return comparison")
        sections.append("- No comparable peer return rows were assembled from the sampled board constituents.")

    if errors:
        sections.extend(["", "## Data retrieval notes"])
        sections.extend(f"- {item}" for item in errors[:5])
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
    unusual_text = get_unusual_trading_activity(ticker, start_date, end_date)
    regime_text = get_capital_flow_regime_context(ticker, curr_date)
    constraint_text = get_trading_constraint_context(ticker, curr_date)
    limit_move_text = get_limit_move_sentiment_context(curr_date)
    policy_text = get_policy_signal_context(curr_date)
    peer_text = get_peer_comparison_context(ticker, curr_date)

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
    if "LHB appearances" in unusual_text:
        flow.append("龙虎榜 / unusual-trading records are available and may explain part of the move as short-horizon flow rather than medium-term fundamentals.")
    if "Seat detail snapshot" in unusual_text:
        flow.append("席位明细 is available, which helps judge whether the move reflects concentrated trading participation.")
    if "main-fund-flow regime looks supportive" in regime_text:
        flow.append("Medium-horizon main-fund-flow regime looks supportive rather than merely one-day positive.")
    if "main-fund-flow regime looks weak" in regime_text:
        flow.append("Medium-horizon main-fund-flow regime looks weak, which reduces confidence in a short-term bounce.")
    if "northbound positioning has been building" in regime_text:
        flow.append("Northbound positioning has been building over the sampled window, which supports persistence.")
    if "northbound positioning has been fading" in regime_text:
        flow.append("Northbound positioning has been fading over the sampled window, which weakens persistence.")
    if "Special treatment flag: ST / *ST detected" in constraint_text:
        risks.append("Special-treatment status is present, which raises regulatory, liquidity, and gap-risk sensitivity.")
    if "Daily price-limit regime: 20%" in constraint_text:
        risks.append("The stock sits in a 20% daily price-limit regime, so momentum and drawdown can both accelerate faster than the main board.")
    if "Daily price-limit regime: 30%" in constraint_text:
        risks.append("The stock sits in a 30% daily price-limit regime, which implies unusually high volatility and liquidity risk.")
    if "speculative risk appetite looks hot" in limit_move_text:
        flow.append("涨停 breadth is dominating跌停 stress, which points to a hot short-horizon tape.")
    if "downside stress looks elevated" in limit_move_text:
        risks.append("跌停 breadth is overwhelming limit-up momentum, which points to a fragile tape and weaker risk appetite.")
    if "policy tone looks supportive" in policy_text:
        catalysts.append("Policy / regulatory tone currently looks supportive, which can improve sector risk appetite and valuation tolerance.")
    if "policy tone looks cautious / restrictive" in policy_text:
        risks.append("Policy / regulatory tone currently looks cautious or restrictive, which can cap sentiment and raise compliance sensitivity.")
    if "peer-relative strength looks constructive" in peer_text:
        flow.append("Peer-relative strength is constructive, suggesting the move is not just generic sector beta.")
    if "peer-relative strength looks weak" in peer_text:
        flow.append("Peer-relative strength looks weak versus sampled peers, which limits conviction.")

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
    sections.extend(["", "## Source Digests", "", event_text, "", activity_text, "", sector_text, "", strength_text, "", relative_text, "", action_pressure_text, "", unusual_text, "", regime_text, "", constraint_text, "", limit_move_text, "", policy_text, "", peer_text])
    return "\n".join(sections).strip()
