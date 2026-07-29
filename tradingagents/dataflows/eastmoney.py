"""
新浪财经 A 股数据适配器（原名「东方财富适配器」）。
================================================

通过 akshare 封装新浪财经公开 HTTP API，提供与 y_finance.py 完全一致的接口签名，
以便通过 interface.py 的供应商路由无缝接入 TradingAgents 分析流程。

.. note::
   2026-07-27 数据源从东方财富迁移至新浪财经。
   东方财富公开 API 端点 (push2his.eastmoney.com) 于 2026 年 7 月变更/关闭，
   返回 404 或 Connection reset。新浪财经 API 自 2015 年至今稳定运行，
   提供相同维度的 A 股数据。
   详见项目根目录 ``eastmoney修复说明.md``。

支持的数据维度：
- 历史日线 OHLCV（前复权/后复权/不复权）
- 技术指标（复用 stockstats 本地计算，akshare 只提供 OHLCV）
- 基本面概况（总市值、PE、PB、ROE 等）
- 实时行情快照

A 股代码格式：
- 上海交易所：6 位数字，如 600519（贵州茅台）→ 内部转为 sh600519
- 深圳交易所：6 位数字，如 000001（平安银行）→ 内部转为 sz000001
- 创业板：3 开头，如 300750（宁德时代）
- 科创板：688 开头，如 688981（中芯国际）

akshare license: MIT
新浪财经数据来源: https://finance.sina.com.cn
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

import pandas as pd
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# akshare stock_zh_a_daily 前复权模式
DEFAULT_ADJUST = "qfq"

# 单次请求最大重试次数
MAX_RETRIES = 1

# 请求超时（秒）
REQUEST_TIMEOUT = 15

# 新浪 stock_zh_a_daily 列名 → 项目标准列名映射
# 注意：新浪返回英文小写列名，与东财的中文列名不同
_COLUMN_MAP: dict[str, str] = {
    "date": "Date",
    "open": "Open",
    "close": "Close",
    "high": "High",
    "low": "Low",
    "volume": "Volume",
    "amount": "Amount",
    "outstanding_share": "OutstandingShare",
    "turnover": "TurnoverRate",
}

# 基本面字段映射（新浪 stock_zh_a_spot → 项目通用标签）
# 注意：新浪 spot 返回中文列名（与东财 spot_em 类似，但列名有差异）
_FUNDAMENTAL_FIELDS: list[tuple[str, str]] = [
    ("市盈率", "PE"),
    ("市净率", "PB"),
    ("总市值", "Market Cap"),
    ("流通市值", "Circulating Market Cap"),
    ("换手率", "Turnover Rate"),
    ("总股本", "Total Shares"),
    ("每股净资产", "Net Assets Per Share"),
    ("净资产收益率", "ROE"),
]


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _validate_a_symbol(symbol: str) -> str:
    """校验并规范化 A 股代码。

    接受 6 位数字字符串（如 "600519"、"000001"）。
    同时处理 LLM 可能附加的 yfinance 风格后缀（.SS/.SZ/.SH）。
    返回纯 6 位数字（akshare 接受此格式）。
    非 A 股格式抛 ValueError，由路由层降级到其他供应商。

    防御纵深：即使上游 prompt 已指示 LLM 不加后缀，
    LLM 在某些调用中仍可能附加——此处是最后一道防线。
    """
    s = symbol.strip()
    # 剥离 yfinance 风格后缀（LLM 可能在工具调用中附加）
    for suffix in (".SS", ".SZ", ".SH"):
        if s.upper().endswith(suffix):
            s = s[: -len(suffix)]
            break
    if len(s) != 6 or not s.isdigit():
        raise ValueError(
            f"'{symbol}' 不是有效的 A 股代码（需要 6 位数字，如 600519）"
        )
    return s


def _to_sina_symbol(symbol: str) -> str:
    """将 6 位 A 股代码转为新浪格式（sh600519 / sz000001）。

    - 上海（6/9 开头）→ sh+代码
    - 深圳（0/2/3 开头）→ sz+代码
    - 其他 → 原样返回
    """
    s = symbol.strip()
    if s.startswith(("6", "9")):
        return f"sh{s}"
    else:
        return f"sz{s}"


def _retry(func, max_retries=MAX_RETRIES, base_delay=2.0):
    """网络请求重试装饰器。

    东方财富 API 偶尔返回空或断开连接，重试可覆盖大部分瞬时故障。
    """
    import time

    last_exc = None
    for attempt in range(max_retries):
        try:
            result = func()
            if result is None:
                raise RuntimeError("akshare returned None")
            return result
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "eastmoney retry %d/%d after %.1fs: %s",
                    attempt + 1, max_retries, delay, exc,
                )
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def _format_date(date_str: str) -> str:
    """把用户输入的 YYYY-MM-DD 转为 akshare 的 YYYYMMDD 格式。"""
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y%m%d")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """重命名 akshare 中文列名为项目标准英文列名，保留未映射列在原位。"""
    if df.empty:
        return df
    rename = {k: v for k, v in _COLUMN_MAP.items() if k in df.columns}
    return df.rename(columns=rename)


def _format_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """格式化 OHLCV DataFrame：重命名列、数值精度处理。

    新浪 stock_zh_a_daily 返回的 date 列已经是 YYYY-MM-DD 字符串，
    无需 pd.to_datetime 再转。
    """
    df = _normalize_columns(df)
    # 数值列保留两位小数
    for col in ("Open", "High", "Low", "Close"):
        if col in df.columns:
            df[col] = df[col].apply(
                lambda x: round(float(x), 2) if pd.notna(x) else x
            )
    return df


# ---------------------------------------------------------------------------
# 公开接口（与 y_finance.py 一一对应）
# ---------------------------------------------------------------------------

def get_stock(
    symbol: Annotated[str, "A 股代码，6 位数字，如 600519（贵州茅台）"],
    start_date: Annotated[str, "开始日期，YYYY-MM-DD 格式"],
    end_date: Annotated[str, "结束日期，YYYY-MM-DD 格式"],
) -> str:
    """获取 A 股历史日线 OHLCV 数据，返回 CSV 字符串。

    .. code-block:: python

        csv_str = get_stock("600519", "2024-01-01", "2024-06-30")
        # -> "# Stock data for 600519 (贵州茅台) from 2024-01-01 to 2024-06-30\\n..."
    """
    import akshare as ak

    symbol = _validate_a_symbol(symbol)
    sina_symbol = _to_sina_symbol(symbol)
    start_fmt = _format_date(start_date)
    end_fmt = _format_date(end_date)

    def _fetch():
        # 2026-07-27: 东方财富 API 失效，切换至新浪 API
        # 旧: ak.stock_zh_a_hist(symbol="600519", period="daily", ...)
        # 新: ak.stock_zh_a_daily(symbol="sh600519", ...)
        # 新浪返回英文小写列名 (date/open/close/...)，与东财中文列名不同
        return ak.stock_zh_a_daily(
            symbol=sina_symbol,
            start_date=start_fmt,
            end_date=end_fmt,
            adjust=DEFAULT_ADJUST,
        )

    try:
        raw = _retry(_fetch)
    except Exception as exc:
        logger.error("Eastmoney get_stock failed for %s: %s", symbol, exc)
        return f"Error: 无法获取 {symbol} 在 {start_date} 至 {end_date} 的历史数据 ({exc})"

    if raw is None or raw.empty:
        return (
            f"# No data for {symbol} from {start_date} to {end_date}\n"
            f"# 该股票可能已退市、停牌，或代码无效\n"
        )

    df = _format_ohlcv(raw)

    # 补充股票名称（若 Sina 返回了 name 列）
    stock_name = ""
    if "name" in raw.columns:
        names = raw["name"].dropna().unique()
        if len(names) > 0:
            stock_name = f" ({names[0]})"
    elif "股票名称" in raw.columns:
        # 兼容：如果回退到东财格式
        names = raw["股票名称"].dropna().unique()
        if len(names) > 0:
            stock_name = f" ({names[0]})"

    # 保留关键列输出
    out_cols = [c for c in ("Date", "Open", "High", "Low", "Close", "Volume", "Amount", "ChangePct", "TurnoverRate") if c in df.columns]
    out = df[out_cols]

    header = (
        f"# Stock data for {symbol}{stock_name} from {start_date} to {end_date}\n"
        f"# Exchange: {'SSE' if symbol.startswith('6') else 'SZSE'}\n"
        f"# Total records: {len(out)}\n"
        f"# Adjust: {DEFAULT_ADJUST} (前复权)\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"# Source: 新浪财经 (via akshare, MIT)\n\n"
    )

    return header + out.to_csv(index=False)


def get_fundamentals(
    ticker: Annotated[str, "A 股代码，6 位数字"],
    curr_date: Annotated[str, "当前日期 YYYY-MM-DD（用于日志记录）"] = None,
) -> str:
    """获取 A 股基本面概况（总市值、PE、PB、ROE 等）。

    通过 akshare 的实时行情接口获取最新基本面数据快照。
    """
    import akshare as ak

    ticker = _validate_a_symbol(ticker)

    def _fetch():
        # 2026-07-27: 东方财富 spot_em API 失效，切换至新浪 spot API
        return ak.stock_zh_a_spot()

    try:
        df = _retry(_fetch)
    except Exception as exc:
        logger.warning(
            "Eastmoney get_fundamentals: spot unavailable for %s (%s), "
            "falling back to historical OHLCV summary",
            ticker, exc,
        )
        return _fundamentals_from_history(ticker, curr_date)

    if df is None or df.empty:
        return _fundamentals_from_history(ticker, curr_date)

    # 按代码匹配（Sina spot 用 "代码" 中文列名）
    code_col = "代码"
    name_col = "名称" if "名称" in df.columns else "name"
    match = df[df[code_col].astype(str) == ticker]
    if match.empty:
        return _fundamentals_from_history(ticker, curr_date)

    row = match.iloc[0]
    lines: list[str] = []

    for ak_field, label in _FUNDAMENTAL_FIELDS:
        value = row.get(ak_field)
        if value is not None and pd.notna(value) and str(value).strip() != "-":
            formatted = _format_fundamental_value(label, value)
            lines.append(f"{label}: {formatted}")

    # Sina spot API 只提供基础行情（价格/成交量），不提供 PE/PB/ROE，
    # 如果无基本面字段，自动降级到历史数据快照
    if not lines:
        logger.info(
            "Sina spot has no fundamental fields for %s, falling back to OHLCV snapshot", ticker
        )
        return _fundamentals_from_history(ticker, curr_date)

    name = row.get(name_col, ticker)
    header = (
        f"# Company Fundamentals for {ticker} ({name})\n"
        f"# Exchange: {'SSE' if ticker.startswith('6') else 'SZSE'}\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"# Source: 新浪财经 (via akshare, MIT)\n\n"
    )

    return header + "\n".join(lines)


def _format_fundamental_value(label: str, value) -> str:
    """格式化基本面数值（市值→亿，百分比→%）。"""
    try:
        v = float(value)
    except (ValueError, TypeError):
        return str(value)

    if "市值" in label or "Market Cap" in label:
        if abs(v) >= 1e8:
            return f"{v / 1e8:.2f} 亿"
    if "净利润" in label or "Net Profit" in label or "Revenue" in label or "总收入" in label:
        if abs(v) >= 1e8:
            return f"{v / 1e8:.2f} 亿"
        elif abs(v) >= 1e4:
            return f"{v / 1e4:.2f} 万"
    if "率" in label or "Margin" in label or "ROE" in label or "PE" in label or "PB" in label:
        return f"{v:.2f}"
    if "Change" in label or "涨跌" in label:
        return f"{v:.2f}%"

    return str(value)


# ---------------------------------------------------------------------------
# 技术指标
# ---------------------------------------------------------------------------

# A 股技术指标最佳实践说明（与 y_finance.py 的 best_ind_params 对齐）
BEST_IND_PARAMS: dict[str, str] = {
    "close_50_sma": (
        "50 SMA (A股): 中期趋势指标。"
        "A 股波动较大，50 日均线比美股中的 50 SMA 更具参考价值。"
        "当股价在 50 日线上方运行时视为多头排列。"
    ),
    "close_200_sma": (
        "200 SMA (A股): 长期趋势基准。"
        "A 股中 200 日线常用于牛熊分界——指数或个股站上 200 日线视为进入牛市区间。"
    ),
    "close_10_ema": (
        "10 EMA (A股): 短线交易参考。"
        "A 股短线资金活跃，10 日 EMA 比美股反应更快，适合 3-5 日波段操作。"
    ),
    "macd": (
        "MACD (A股): 动量指标。"
        "A 股中 MACD 金叉/死叉是最常用的中短期择时信号之一。"
        "注意 A 股 T+1 制度，信号确认需留一日的缓冲。"
    ),
    "macds": "MACD Signal (A股): MACD 信号线。",
    "macdh": "MACD Histogram (A股): MACD 柱状图。",
    "rsi": (
        "RSI (A股): 相对强弱指标。"
        "A 股极端情绪比美股更频繁——RSI > 85 超买、< 20 超卖，阈值可比美股适度放宽。"
    ),
    "boll": "Bollinger Middle (A股): 布林带中轨（20 SMA）。",
    "boll_ub": "Bollinger Upper Band (A股): 布林带上轨。",
    "boll_lb": "Bollinger Lower Band (A股): 布林带下轨。",
    "atr": (
        "ATR (A股): 平均真实波幅。"
        "A 股涨跌停制度下 ATR 用于动态止损——通常设为 2-3 倍 ATR 作为止损距离。"
    ),
    "vwma": "VWMA (A股): 成交量加权移动平均。A 股量价关系比美股更显著，VWMA 参考价值高。",
    "mfi": (
        "MFI (A股): 资金流量指标。"
        "A 股受资金面影响极大，MFI 结合成交量判断资金进出比单纯价格指标更有效。"
    ),
}


def get_indicator(
    symbol: Annotated[str, "A 股代码，6 位数字"],
    indicator: Annotated[str, "指标名称，如 macd, rsi, close_10_ema"],
    curr_date: Annotated[str, "当前交易日期，YYYY-MM-DD 格式"],
    look_back_days: Annotated[int, "回溯天数"],
) -> str:
    """获取 A 股技术指标数值。

    通过 akshare 获取 OHLCV，然后由 stockstats 在本地计算指标。
    这与 yfinance 路径的做法一致——数据获取和指标计算职责分离。
    """
    if indicator not in BEST_IND_PARAMS:
        supported = ", ".join(sorted(BEST_IND_PARAMS.keys()))
        raise ValueError(
            f"不支持的指标 '{indicator}'。支持的指标: {supported}"
        )

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_dt - relativedelta(days=look_back_days)
    before_str = before.strftime("%Y-%m-%d")

    # 获取 OHLCV 原始数据
    csv_str = get_stock(symbol, before_str, curr_date)

    if csv_str.startswith("Error:") or "No data" in csv_str[:20]:
        # 数据不可用——返回哨兵值而非崩溃，让 Agent 跳过该指标
        return (
            f"## {indicator} values from {before_str} to {curr_date}:\n\n"
            f"数据不可用: 无法获取 {symbol} 在指定区间的行情数据。\n"
            f"该股票可能在区间内停牌或代码无效。\n\n"
            f"{BEST_IND_PARAMS.get(indicator, 'No description available.')}"
        )

    return _calculate_indicator_from_csv(
        csv_str, indicator, symbol, before_str, curr_date
    )


def _fundamentals_from_history(ticker: str, curr_date: str | None = None) -> str:
    """当实时行情不可用时，从历史 K 线数据提取基本面快照作为降级方案。

    返回最近交易日的 OHLCV 摘要 + 价格变化统计，而非完整的 PE/PB/ROE 数据。
    """
    import akshare as ak

    today = datetime.now().strftime("%Y-%m-%d")
    lookback_start = (datetime.now() - relativedelta(days=60)).strftime("%Y-%m-%d")

    try:
        raw = ak.stock_zh_a_daily(
            symbol=_to_sina_symbol(ticker),
            start_date=_format_date(lookback_start),
            end_date=_format_date(today),
            adjust=DEFAULT_ADJUST,
        )
    except Exception as exc:
        logger.error("_fundamentals_from_history failed for %s: %s", ticker, exc)
        return (
            f"# Company Fundamentals for {ticker}\n"
            f"# 数据暂时不可用（实时行情和历史数据均获取失败）\n"
            f"# 请稍后重试或检查代码是否正确\n"
        )

    if raw is None or raw.empty:
        return f"# No historical data available for {ticker}\n"

    df = _format_ohlcv(raw)
    latest = df.iloc[-1] if not df.empty else None
    if latest is None:
        return f"# Insufficient data for {ticker}\n"

    # 计算基本统计
    closes = pd.to_numeric(df["Close"], errors="coerce").dropna()
    price_now = float(closes.iloc[-1]) if len(closes) > 0 else 0
    price_20d = float(closes.iloc[-20]) if len(closes) >= 20 else price_now
    price_60d = float(closes.iloc[0]) if len(closes) > 0 else price_now
    change_20d = ((price_now - price_20d) / price_20d * 100) if price_20d else 0
    change_60d = ((price_now - price_60d) / price_60d * 100) if price_60d else 0
    # 兼容 Sina (volume) 和东财 (成交量) 列名
    vol_col = "volume" if "volume" in raw.columns else "成交量"
    avg_vol = float(raw[vol_col].tail(20).mean()) if vol_col in raw.columns else 0

    name = ""
    if "name" in raw.columns:
        names = raw["name"].dropna().unique()
        if len(names) > 0:
            name = f" ({names[0]})"
    elif "股票名称" in raw.columns:
        names = raw["股票名称"].dropna().unique()
        if len(names) > 0:
            name = f" ({names[0]})"

    return (
        f"# Company Snapshot for {ticker}{name} (from OHLCV, real-time unavailable)\n"
        f"# Exchange: {'SSE' if ticker.startswith('6') else 'SZSE'}\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"# Source: 新浪财经 (via akshare, MIT)\n"
        f"# Note: 实时基本面(PE/PB/ROE)暂时不可用，以下为历史K线统计\n\n"
        f"Latest Price: {price_now:.2f}\n"
        f"Latest Date: {latest.get('Date', 'N/A')}\n"
        f"Latest Open: {latest.get('Open', 'N/A')}\n"
        f"Latest High: {latest.get('High', 'N/A')}\n"
        f"Latest Low: {latest.get('Low', 'N/A')}\n"
        f"Latest Volume: {latest.get('Volume', 'N/A')}\n"
        f"20-Day Change: {change_20d:+.2f}%\n"
        f"60-Day Change: {change_60d:+.2f}%\n"
        f"Avg Volume (20d): {avg_vol:.0f}\n"
    )


def _calculate_indicator_from_csv(
    csv_str: str,
    indicator: str,
    symbol: str,
    start_date: str,
    end_date: str,
) -> str:
    """从 CSV 中用 stockstats 本地计算指标值。

    替代方案：Alpha Vantage 是通过其 API 计算指标（alpha_vantage_indicator.py），
    而 yfinance 路径是通过 stockstats 本地计算（y_finance.py 的 _get_stock_stats_bulk）。
    本适配器采用 yfinance 路径的策略——本地计算，避免依赖外部指标 API。
    """
    from io import StringIO

    from stockstats import wrap

    try:
        # 解析 CSV（跳过 # 开头的注释行）
        lines = [line for line in csv_str.split("\n") if not line.startswith("#")]
        if not lines:
            return f"Error: CSV 中无数据行"

        df = pd.read_csv(StringIO("\n".join(lines)))
        if df.empty or "Close" not in df.columns and "Date" not in df.columns:
            return f"Error: CSV 缺少必要列（Date, Close）"

        # 确保有 Date 列
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

        # 映射列名为 stockstats 期望的小写格式
        col_map = {
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        }
        df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

        # 用 stockstats 计算指标
        stock_df = wrap(df)
        stock_df[indicator]  # 触发计算

        if "Date" in df.columns:
            stock_df["Date"] = df["Date"]

        # 提取日期-指标值对
        result_parts = []
        if "Date" in stock_df.columns and indicator in stock_df.columns:
            for _, row in stock_df.iterrows():
                date_str = (
                    row["Date"].strftime("%Y-%m-%d")
                    if hasattr(row["Date"], "strftime")
                    else str(row["Date"])[:10]
                )
                val = row[indicator]
                if pd.isna(val):
                    result_parts.append(f"{date_str}: N/A")
                else:
                    result_parts.append(f"{date_str}: {val:.4f}" if isinstance(val, float) else f"{date_str}: {val}")
        else:
            return f"Error: 无法计算 {indicator}，stockstats 输出格式异常"

        ind_string = "\n".join(result_parts)

        return (
            f"## {indicator} values from {start_date} to {end_date}:\n\n"
            + (ind_string if result_parts else "N/A: 无有效数据点\n")
            + "\n\n"
            + BEST_IND_PARAMS.get(indicator, "No description available.")
        )

    except Exception as exc:
        logger.error("Failed to calculate %s for %s: %s", indicator, symbol, exc)
        return (
            f"## {indicator} values from {start_date} to {end_date}:\n\n"
            f"计算失败: {exc}\n\n"
            f"{BEST_IND_PARAMS.get(indicator, 'No description available.')}"
        )


# ---------------------------------------------------------------------------
# 财务报表降级适配（A 股暂无逐表拆分接口，统一指向 get_fundamentals）
# ---------------------------------------------------------------------------

def get_income_statement(symbol: str, *args, **kwargs) -> str:
    """A 股暂无独立的利润表接口。请改用 get_fundamentals 获取 ROE/PE/PB 等核心指标。"""
    symbol = _validate_a_symbol(symbol)
    return (
        f"[Income Statement] A 股暂不支持独立利润表查询。"
        f"请使用 get_fundamentals('{symbol}') 获取 {symbol} 的 ROE、净利率、"
        f"营收增长率等核心盈利指标。"
    )


def get_balance_sheet(symbol: str, *args, **kwargs) -> str:
    """A 股暂无独立的资产负债表接口。请改用 get_fundamentals。"""
    symbol = _validate_a_symbol(symbol)
    return (
        f"[Balance Sheet] A 股暂不支持独立资产负债表查询。"
        f"请使用 get_fundamentals('{symbol}') 获取 {symbol} 的总市值、"
        f"市净率、资产负债率等核心财务指标。"
    )


def get_cashflow(symbol: str, *args, **kwargs) -> str:
    """A 股暂无独立的现金流表接口。请改用 get_fundamentals。"""
    symbol = _validate_a_symbol(symbol)
    return (
        f"[Cash Flow] A 股暂不支持独立现金流表查询。"
        f"请使用 get_fundamentals('{symbol}') 获取 {symbol} 的核心财务指标。"
    )


# ---------------------------------------------------------------------------
# 新闻
# ---------------------------------------------------------------------------

def get_news(symbol: str, start_date: str | None = None, end_date: str | None = None) -> str:
    """获取 A 股个股新闻，通过东方财富公开接口。

    签名与 alpha_vantage_news.get_news / yfinance_news.get_news_yfinance 一致，
    通过 interface.py 供应商路由统一调用。

    Args:
        symbol: 6 位 A 股代码，如 600519
        start_date: 起始日期 yyyy-mm-dd（可选，用于过滤）
        end_date: 结束日期 yyyy-mm-dd（可选，用于过滤）

    Returns:
        格式化的新闻文本。非 A 股代码抛 ValueError 由路由层降级到其他供应商。
    """
    try:
        import akshare as ak
    except ImportError:
        return "[News] akshare 未安装，无法获取 A 股新闻。"

    symbol = _validate_a_symbol(symbol)

    try:
        df = _retry(lambda: ak.stock_news_em(symbol=symbol))
    except Exception as exc:
        logger.warning("Failed to fetch news for %s: %s", symbol, exc)
        return f"[News] 获取 {symbol} 新闻失败: {exc}"

    if df is None or df.empty:
        return f"[News] {symbol} 暂无相关新闻。"

    # 按日期过滤
    if start_date or end_date:
        time_col = "发布时间"
        if time_col in df.columns:
            df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
            if start_date:
                df = df[df[time_col] >= pd.Timestamp(start_date)]
            if end_date:
                df = df[df[time_col] <= pd.Timestamp(end_date) + pd.Timedelta(days=1)]

    if df.empty:
        return f"[News] {symbol} 在 {start_date}~{end_date} 期间无相关新闻。"

    lines = [f"## {symbol} A 股新闻"]
    if start_date or end_date:
        lines[0] += f"（{start_date or '最早'} ~ {end_date or '最新'}）"
    lines.append("")

    for _, row in df.iterrows():
        title = str(row.get("新闻标题", ""))
        source = str(row.get("文章来源", ""))
        pub_time = str(row.get("发布时间", ""))[:19]  # 截到秒
        content = str(row.get("新闻内容", ""))

        lines.append(f"### {title}")
        lines.append(f"来源: {source} | 时间: {pub_time}")
        if content and content != "nan":
            # 截取前 300 字符，完整内容太长会撑爆 prompt
            truncated = content[:300] + ("..." if len(content) > 300 else "")
            lines.append(f"{truncated}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 情绪 / 资金流向（替代 Reddit + StockTwits）
# ---------------------------------------------------------------------------

def get_sentiment(symbol: str, curr_date: str | None = None) -> str:
    """获取 A 股个股资金流向，作为市场情绪代理指标。

    通过 akshare 拉取最近 120 个交易日的逐日资金流向数据，
    聚合近期（约 5 日）的主力/超大单/大单/中单/小单净流向，
    输出结构化文本供 LLM 分析。

    Reddit/StockTwits 不覆盖 A 股，本函数是 sentiment_analyst
    的 A 股替代数据源。

    Args:
        symbol: 6 位 A 股代码
        curr_date: 分析基准日期（可选，用于标注"近期"截止日）

    Returns:
        格式化的资金流向分析文本
    """
    try:
        import akshare as ak
    except ImportError:
        return "[Sentiment] akshare 未安装，无法获取 A 股资金流向。"

    symbol = _validate_a_symbol(symbol)
    market = "sh" if symbol.startswith(("6", "9")) else "sz"

    try:
        df = _retry(lambda: ak.stock_individual_fund_flow(stock=symbol, market=market))
    except Exception as exc:
        logger.warning("Failed to fetch fund flow for %s: %s", symbol, exc)
        return f"[Sentiment] 获取 {symbol} 资金流向失败: {exc}"

    if df is None or df.empty:
        return f"[Sentiment] {symbol} 暂无资金流向数据。"

    # 日期列规范化
    date_col = "日期" if "日期" in df.columns else df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.sort_values(date_col, ascending=False).head(20)  # 最近 20 个交易日

    # 资金流向列映射
    fund_cols = {
        "主力净流入-净额": "主力净流入",
        "超大单净流入-净额": "超大单净流入",
        "大单净流入-净额": "大单净流入",
        "中单净流入-净额": "中单净流入",
        "小单净流入-净额": "小单净流入",
    }

    lines = [f"## {symbol} 资金流向分析（近 {len(df)} 个交易日）"]
    if curr_date:
        lines[0] += f" | 截止: {curr_date}"
    lines.append("")

    # 汇总统计
    lines.append("### 近期净流入汇总（万元）")
    for col, label in fund_cols.items():
        if col in df.columns:
            total = df[col].sum()
            direction = "流入" if total > 0 else "流出"
            lines.append(f"- {label}: {total:+.0f} 万元（{direction}）")
    lines.append("")

    # 最近 5 日明细
    lines.append("### 最近 5 日逐日明细")
    recent = df.head(5)
    for _, row in recent.iterrows():
        d = row[date_col].strftime("%Y-%m-%d") if hasattr(row[date_col], "strftime") else str(row[date_col])[:10]
        parts = [d]
        for col, label in fund_cols.items():
            if col in row.index and pd.notna(row[col]):
                parts.append(f"{label}: {row[col]:+.0f}万")
        lines.append(" | ".join(parts))
    lines.append("")

    # 解读提示
    lines.append("### 分析要点")
    lines.append("- 主力资金（超大单+大单）连续净流入 → 机构看多信号")
    lines.append("- 主力资金连续净流出 + 小单净流入 → 散户接盘、机构出货")
    lines.append("- 关注资金流向与股价走势是否背离（价升量缩 = 上涨动力不足）")
    lines.append("- 以上为历史资金流向数据，不构成投资建议")

    return "\n".join(lines)
