# Modified for A-share position management; see repository NOTICE.
"""Deterministic A-share market, position, rule, and decision-matrix context."""

from __future__ import annotations

import re
import time
from datetime import date
from enum import Enum
from typing import Any

import pandas as pd
import requests
import yfinance as yf

_CODE_RE = re.compile(r"^(?P<code>\d{6})(?:\.(?:SH|SS|SZ|BJ))?$", re.IGNORECASE)
_UA = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://quote.eastmoney.com/",
}


class PositionAction(str, Enum):
    ADD = "Add"
    SLIGHT_ADD = "Slight Add"
    HOLD = "Hold"
    REDUCE = "Reduce"
    EXIT = "Exit"


ACTION_ZH = {
    PositionAction.ADD.value: "加仓",
    PositionAction.SLIGHT_ADD.value: "小幅加仓",
    PositionAction.HOLD.value: "不动",
    PositionAction.REDUCE.value: "减仓",
    PositionAction.EXIT.value: "退出",
}


def is_a_share_symbol(symbol: str) -> bool:
    if not isinstance(symbol, str):
        return False
    match = _CODE_RE.fullmatch(symbol.strip())
    if not match:
        return False
    code = match.group("code")
    return code.startswith(("0", "2", "3", "4", "5", "6", "8", "9"))


def _exchange(code: str) -> str:
    if code.startswith(("4", "8", "92")):
        return "BJ"
    if code.startswith(("5", "6", "9")):
        return "SH"
    return "SZ"


def canonical_a_share_symbol(symbol: str) -> str:
    match = _CODE_RE.fullmatch(symbol.strip()) if isinstance(symbol, str) else None
    if not match:
        raise ValueError(f"Not a mainland A-share symbol: {symbol!r}")
    code = match.group("code")
    suffix = symbol.strip().upper().rsplit(".", 1)[1] if "." in symbol else ""
    if suffix == "SS":
        suffix = "SH"
    exchange = suffix if suffix in {"SH", "SZ", "BJ"} else _exchange(code)
    return f"{code}.{exchange}"


def yahoo_a_share_symbol(symbol: str) -> str:
    canonical = canonical_a_share_symbol(symbol)
    code, exchange = canonical.split(".")
    return f"{code}.SS" if exchange == "SH" else f"{code}.{exchange}"


def _eastmoney_secid(symbol: str) -> str:
    canonical = canonical_a_share_symbol(symbol)
    code, exchange = canonical.split(".")
    market = "1" if exchange == "SH" else "0"
    return f"{market}.{code}"


def _tencent_symbol(symbol: str) -> str:
    canonical = canonical_a_share_symbol(symbol)
    code, exchange = canonical.split(".")
    return f"{exchange.lower()}{code}"


def normalize_portfolio_context(context: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = dict(context or {})

    def number(name: str, default: float | None, minimum: float = 0) -> float | None:
        value = raw.get(name, default)
        if value in (None, ""):
            return None
        parsed = float(value)
        if parsed < minimum:
            raise ValueError(f"{name} must be >= {minimum}")
        return parsed

    position_pct = number("position_pct", 0.0)
    if position_pct is not None and position_pct > 100:
        raise ValueError("position_pct must be <= 100")
    return {
        "cost_basis": number("cost_basis", None),
        "position_pct": position_pct,
        "shares": int(number("shares", 0) or 0),
        "cash_available": number("cash_available", None),
        "holding_horizon_days": int(number("holding_horizon_days", 120, 1) or 120),
        "max_drawdown_pct": number("max_drawdown_pct", 12.0),
        "bought_today": bool(raw.get("bought_today", False)),
    }


def _get_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.get(
                url,
                params=params,
                headers=_UA,
                timeout=15,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.25 * (attempt + 1))
    raise RuntimeError(f"A-share vendor request failed: {last_error}") from last_error


def _fetch_bars(symbol: str, end_date: str, limit: int = 260) -> tuple[str, pd.DataFrame]:
    payload = _get_json(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        {
            "secid": _eastmoney_secid(symbol),
            "klt": "101",
            "fqt": "1",
            "lmt": str(limit),
            "end": end_date.replace("-", ""),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        },
    ).get("data") or {}
    rows = []
    for line in payload.get("klines") or []:
        parts = line.split(",")
        if len(parts) < 11:
            continue
        rows.append(
            {
                "date": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume_lots": float(parts[5]),
                "amount": float(parts[6]),
                "amplitude_pct": float(parts[7]),
                "return_pct": float(parts[8]),
                "change": float(parts[9]),
                "turnover_pct": float(parts[10]),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError(f"No Eastmoney A-share bars for {symbol}")
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame[frame["date"] <= pd.Timestamp(end_date)].reset_index(drop=True)
    if frame.empty:
        raise RuntimeError(f"No A-share bars for {symbol} on or before {end_date}")
    return str(payload.get("name") or canonical_a_share_symbol(symbol)), frame


def _fetch_yfinance_bars(symbol: str, end_date: str) -> tuple[str, pd.DataFrame]:
    history = yf.Ticker(yahoo_a_share_symbol(symbol)).history(period="1y", auto_adjust=False)
    if history.empty:
        raise RuntimeError(f"No fallback A-share bars for {symbol}")
    history = history.reset_index()
    date_column = history.columns[0]
    dates = pd.to_datetime(history[date_column], utc=True).dt.tz_convert(None)
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": history["Open"].astype(float),
            "close": history["Close"].astype(float),
            "high": history["High"].astype(float),
            "low": history["Low"].astype(float),
            "volume_lots": history["Volume"].astype(float) / 100,
            "amount": 0.0,
            "amplitude_pct": 0.0,
            "return_pct": history["Close"].pct_change().fillna(0) * 100,
            "change": history["Close"].diff().fillna(0),
            "turnover_pct": 0.0,
        }
    )
    frame = frame[frame["date"] <= pd.Timestamp(end_date)].reset_index(drop=True)
    if frame.empty:
        raise RuntimeError(f"No fallback A-share bars for {symbol} on or before {end_date}")
    return canonical_a_share_symbol(symbol), frame


def _fetch_tencent_bars(symbol: str, end_date: str, limit: int = 260) -> tuple[str, pd.DataFrame]:
    key = _tencent_symbol(symbol)
    payload = _get_json(
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        {"param": f"{key},day,,,{limit},qfq"},
    )
    data = (payload.get("data") or {}).get(key) or {}
    raw_rows = data.get("qfqday") or data.get("day") or []
    rows = []
    for parts in raw_rows:
        if len(parts) < 6:
            continue
        close = float(parts[2])
        previous = rows[-1]["close"] if rows else close
        rows.append(
            {
                "date": parts[0],
                "open": float(parts[1]),
                "close": close,
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume_lots": float(parts[5]),
                "amount": 0.0,
                "amplitude_pct": 0.0,
                "return_pct": (close / previous - 1) * 100 if previous else 0.0,
                "change": close - previous,
                "turnover_pct": 0.0,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError(f"No Tencent A-share bars for {symbol}")
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame[frame["date"] <= pd.Timestamp(end_date)].reset_index(drop=True)
    if frame.empty:
        raise RuntimeError(f"No Tencent A-share bars for {symbol} on or before {end_date}")
    return canonical_a_share_symbol(symbol), frame


def _fetch_quote(symbol: str) -> dict[str, Any]:
    try:
        data = _get_json(
            "https://push2.eastmoney.com/api/qt/stock/get",
            {
                "secid": _eastmoney_secid(symbol),
                "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f116,f117,f162,f167",
            },
        ).get("data") or {}
        if data:
            return {
                "code": data.get("f57"),
                "name": data.get("f58"),
                "close": _scaled(data.get("f43")),
                "previous_close": _scaled(data.get("f60")),
                "market_cap": data.get("f116"),
                "pe_ttm": _scaled(data.get("f162")),
                "pb": _scaled(data.get("f167")),
            }
    except Exception:
        pass
    return _fetch_tencent_quote(symbol)


def _fetch_tencent_quote(symbol: str) -> dict[str, Any]:
    response = requests.get(
        f"https://qt.gtimg.cn/q={_tencent_symbol(symbol)}",
        headers=_UA,
        timeout=15,
    )
    response.raise_for_status()
    text = response.content.decode("gbk", errors="ignore")
    fields = text.split('"')[1].split("~") if '"' in text else []
    if len(fields) < 53:
        raise RuntimeError(f"Invalid Tencent quote for {symbol}")

    def field(index: int) -> float | None:
        try:
            return float(fields[index]) if fields[index] else None
        except (IndexError, ValueError):
            return None

    return {
        "code": fields[2],
        "name": fields[1],
        "close": field(3),
        "previous_close": field(4),
        "market_cap": (field(44) * 100_000_000) if field(44) is not None else None,
        "pe_ttm": field(52),
        "pb": field(46),
        "dividend_yield": field(64),
        "turnover_pct": field(38),
    }


def _scaled(value: Any) -> float | None:
    if value in (None, "-", ""):
        return None
    return float(value) / 100.0


def _rsi(close: pd.Series, periods: int = 14) -> float | None:
    if len(close) <= periods:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / periods, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / periods, adjust=False).mean()
    value = 100 - 100 / (1 + gain / loss)
    return round(float(value.iloc[-1]), 2)


def _classify_valuation(pe_ttm: float | None, pb: float | None) -> str:
    if pe_ttm is None and pb is None:
        return "unknown"
    if pe_ttm is not None and pe_ttm <= 0:
        return "expensive"
    if (pe_ttm is not None and pe_ttm <= 12) or (pb is not None and pb <= 1.2):
        return "cheap"
    if (pe_ttm is None or pe_ttm <= 25) and (pb is None or pb <= 3):
        return "fair"
    return "expensive"


def _classify_trend(close: float, ma20: float | None, ma60: float | None, rsi: float | None) -> str:
    if ma20 is None or ma60 is None:
        return "neutral"
    if close > ma20 > ma60 and (rsi is None or rsi < 72):
        return "strong"
    if close < ma20 and close < ma60:
        return "weak"
    return "neutral"


def _classify_position(position_pct: float) -> str:
    if position_pct < 5:
        return "low"
    if position_pct <= 15:
        return "medium"
    return "high"


_MATRIX = {
    ("cheap", "strong", "low"): PositionAction.ADD,
    ("cheap", "strong", "medium"): PositionAction.SLIGHT_ADD,
    ("cheap", "strong", "high"): PositionAction.HOLD,
    ("cheap", "neutral", "low"): PositionAction.SLIGHT_ADD,
    ("cheap", "neutral", "medium"): PositionAction.HOLD,
    ("cheap", "neutral", "high"): PositionAction.HOLD,
    ("cheap", "weak", "low"): PositionAction.HOLD,
    ("cheap", "weak", "medium"): PositionAction.HOLD,
    ("cheap", "weak", "high"): PositionAction.REDUCE,
    ("fair", "strong", "low"): PositionAction.SLIGHT_ADD,
    ("fair", "strong", "medium"): PositionAction.HOLD,
    ("fair", "strong", "high"): PositionAction.HOLD,
    ("fair", "neutral", "low"): PositionAction.HOLD,
    ("fair", "neutral", "medium"): PositionAction.HOLD,
    ("fair", "neutral", "high"): PositionAction.REDUCE,
    ("fair", "weak", "low"): PositionAction.HOLD,
    ("fair", "weak", "medium"): PositionAction.REDUCE,
    ("fair", "weak", "high"): PositionAction.REDUCE,
    ("expensive", "strong", "low"): PositionAction.HOLD,
    ("expensive", "strong", "medium"): PositionAction.REDUCE,
    ("expensive", "strong", "high"): PositionAction.REDUCE,
    ("expensive", "neutral", "low"): PositionAction.HOLD,
    ("expensive", "neutral", "medium"): PositionAction.REDUCE,
    ("expensive", "neutral", "high"): PositionAction.REDUCE,
    ("expensive", "weak", "low"): PositionAction.HOLD,
    ("expensive", "weak", "medium"): PositionAction.REDUCE,
    ("expensive", "weak", "high"): PositionAction.EXIT,
}


def _matrix_action(valuation: str, trend: str, position: str) -> PositionAction:
    if valuation == "unknown":
        return PositionAction.HOLD
    return _MATRIX[(valuation, trend, position)]


def _trading_rules(code: str, name: str) -> dict[str, Any]:
    exchange = _exchange(code)
    is_st = "ST" in name.upper()
    if exchange == "BJ":
        limit_pct = 30
    elif code.startswith(("300", "301", "688")):
        limit_pct = 20
    elif is_st:
        limit_pct = 5
    else:
        limit_pct = 10
    return {
        "settlement": "T+1",
        "buy_lot_size": 100,
        "sell_odd_lot": "Odd lots may be sold only as a whole remainder.",
        "price_limit_pct": limit_pct,
        "price_limit_caveat": "IPO/no-limit periods and special regulatory arrangements override this.",
        "sell_tax": "Include current A-share stamp duty, commission, transfer fee, and slippage.",
    }


def _benchmark_environment(end_date: str) -> dict[str, Any]:
    benchmarks = {
        "SSE Composite": "000001.SH",
        "CSI 300": "000300.SH",
        "SZSE Component": "399001.SZ",
        "ChiNext": "399006.SZ",
    }
    output: dict[str, Any] = {}
    for label, symbol in benchmarks.items():
        try:
            try:
                _, bars = _fetch_bars(symbol, end_date, limit=25)
            except Exception:
                _, bars = _fetch_tencent_bars(symbol, end_date, limit=25)
            close = bars["close"]
            output[label] = {
                "close": round(float(close.iloc[-1]), 2),
                "20d_return_pct": (
                    round((float(close.iloc[-1]) / float(close.iloc[0]) - 1) * 100, 2)
                    if len(close) > 1
                    else None
                ),
            }
        except Exception as exc:
            output[label] = {"error": str(exc)}
    return output


def build_a_share_analysis_context(
    symbol: str,
    trade_date: str,
    portfolio_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    portfolio = normalize_portfolio_context(portfolio_context)
    source = "Eastmoney push2/push2his"
    try:
        name, bars = _fetch_bars(symbol, trade_date)
    except Exception as eastmoney_error:
        try:
            name, bars = _fetch_tencent_bars(symbol, trade_date)
            source = "Tencent Finance fallback (Eastmoney unavailable)"
        except Exception as tencent_error:
            try:
                name, bars = _fetch_yfinance_bars(symbol, trade_date)
                source = "Yahoo Finance fallback (Chinese vendors unavailable)"
            except Exception as fallback_error:
                fallback_error = RuntimeError(f"{tencent_error}; {fallback_error}")
                canonical = canonical_a_share_symbol(symbol)
                code = canonical[:6]
                portfolio_position = _classify_position(float(portfolio["position_pct"] or 0))
                return {
                    "mode": "a_share",
                    "symbol": canonical,
                    "name": canonical,
                    "trade_date": trade_date,
                    "source": "unavailable",
                    "data_error": f"{eastmoney_error}; {fallback_error}",
                    "market": {
                        "close": None,
                        "ma20": None,
                        "ma60": None,
                        "rsi14": None,
                        "turnover_pct": None,
                        "pe_ttm": None,
                        "pb": None,
                    },
                    "portfolio": portfolio,
                    "dimensions": {
                        "valuation": "unknown",
                        "trend": "neutral",
                        "position": portfolio_position,
                    },
                    "matrix_action": PositionAction.HOLD.value,
                    "matrix_action_zh": ACTION_ZH[PositionAction.HOLD.value],
                    "trading_rules": _trading_rules(code, canonical),
                    "china_market_environment": _benchmark_environment(trade_date),
                }
    latest = bars.iloc[-1]
    close_series = bars["close"]
    ma20 = float(close_series.rolling(20).mean().iloc[-1]) if len(bars) >= 20 else None
    ma60 = float(close_series.rolling(60).mean().iloc[-1]) if len(bars) >= 60 else None
    rsi14 = _rsi(close_series)

    # Point-in-time quote valuation is safe only for a current-date analysis.
    quote: dict[str, Any] = {}
    if trade_date == date.today().isoformat():
        try:
            quote = _fetch_quote(symbol)
            name = str(quote.get("name") or name)
        except Exception:
            quote = {}

    valuation = _classify_valuation(quote.get("pe_ttm"), quote.get("pb"))
    trend = _classify_trend(float(latest["close"]), ma20, ma60, rsi14)
    position = _classify_position(float(portfolio["position_pct"] or 0))
    action = _matrix_action(valuation, trend, position)

    return {
        "mode": "a_share",
        "symbol": canonical_a_share_symbol(symbol),
        "name": name,
        "trade_date": str(latest["date"].date()),
        "source": source,
        "market": {
            "close": round(float(latest["close"]), 3),
            "ma20": round(ma20, 3) if ma20 is not None else None,
            "ma60": round(ma60, 3) if ma60 is not None else None,
            "rsi14": rsi14,
            "turnover_pct": (
                round(float(quote["turnover_pct"]), 3)
                if quote.get("turnover_pct") is not None
                else round(float(latest["turnover_pct"]), 3)
            ),
            "pe_ttm": quote.get("pe_ttm"),
            "pb": quote.get("pb"),
        },
        "portfolio": portfolio,
        "dimensions": {
            "valuation": valuation,
            "trend": trend,
            "position": position,
        },
        "matrix_action": action.value,
        "matrix_action_zh": ACTION_ZH[action.value],
        "trading_rules": _trading_rules(canonical_a_share_symbol(symbol)[:6], name),
        "china_market_environment": _benchmark_environment(trade_date),
    }


def render_a_share_context(context: dict[str, Any] | None) -> str:
    if not context:
        return ""
    market = context["market"]
    portfolio = context["portfolio"]
    dimensions = context["dimensions"]
    rules = context["trading_rules"]
    benchmarks = context["china_market_environment"]
    benchmark_lines = "\n".join(
        f"- {name}: {values}" for name, values in benchmarks.items()
    )
    return f"""## A-share portfolio-management context

- Instrument: {context['name']} ({context['symbol']})
- Verified date/source: {context['trade_date']} / {context['source']}
- Price/technicals: close={market['close']}, MA20={market['ma20']}, MA60={market['ma60']}, RSI14={market['rsi14']}, turnover={market['turnover_pct']}%
- Point-in-time valuation: PE(TTM)={market['pe_ttm']}, PB={market['pb']} (unknown for historical runs to prevent look-ahead)
- Position: cost={portfolio['cost_basis']}, weight={portfolio['position_pct']}%, shares={portfolio['shares']}, cash={portfolio['cash_available']}, horizon={portfolio['holding_horizon_days']}d, max drawdown={portfolio['max_drawdown_pct']}%, bought today={portfolio['bought_today']}
- Three-dimensional matrix: valuation={dimensions['valuation']}, trend={dimensions['trend']}, position={dimensions['position']}
- Deterministic matrix baseline: {context['matrix_action']} ({context['matrix_action_zh']})
- Trading constraints: {rules}

### China market environment
{benchmark_lines}

Treat the matrix action as the baseline. A final action may deviate only when specific company evidence justifies it, and the deviation must be explained. Never use US FRED, Polymarket, Reddit, or StockTwits as A-share evidence."""
