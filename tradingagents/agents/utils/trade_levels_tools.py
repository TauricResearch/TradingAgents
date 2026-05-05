import json
from datetime import datetime, timedelta
from io import StringIO
from typing import Annotated, Any, Dict, Optional

import pandas as pd
from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.agents.utils.tool_errors import tool_error_text


def _extract_csv(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        if not line.strip():
            continue
        lines.append(line)
    return "\n".join(lines)


def _asof_row(df: pd.DataFrame, asof: str) -> pd.Series:
    target = pd.to_datetime(asof).tz_localize(None)
    idx = pd.to_datetime(df.index).tz_localize(None)
    df = df.copy()
    df.index = idx
    eligible = df[df.index <= target]
    if eligible.empty:
        raise ValueError(f"no OHLCV rows available on or before {asof}")
    return eligible.iloc[-1]


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(period).mean()
    value = float(atr.dropna().iloc[-1])
    return value


def _rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    up = delta.clip(lower=0)
    down = (-delta).clip(lower=0)
    roll_up = up.rolling(period).mean()
    roll_down = down.rolling(period).mean()
    rs = roll_up / roll_down.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))
    series = rsi.dropna()
    if series.empty:
        return 50.0
    return float(series.iloc[-1])


def _sma(close: pd.Series, period: int) -> float:
    value = float(close.rolling(period).mean().dropna().iloc[-1])
    return value


def _sma_series(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period).mean()


def _round_price(x: Optional[float]) -> Optional[float]:
    if x is None:
        return None
    return float(round(float(x), 2))


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))



@tool
def suggest_trade_levels(
    symbol: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many calendar days to look back for OHLCV"] = 180,
    swing_window: Annotated[int, "window (trading days) for swing high/low anchors"] = 20,
    atr_period: Annotated[int, "ATR period (trading days)"] = 14,
    rr: Annotated[float, "base risk-reward ratio for take profit (used when adaptive_rr is false)"] = 2.0,
    direction: Annotated[str, "auto|long|short"] = "auto",
    adaptive_rr: Annotated[bool, "if true, adjust RR using trend strength + volatility"] = True,
    confirmation: Annotated[bool, "if true, use breakout + retest confirmation entry rules in trend regime"] = True,
    account_size: Annotated[Optional[float], "optional portfolio/account notional to compute sizing"] = None,
    risk_per_trade_pct: Annotated[float, "risk per trade as % of account (e.g. 1.0)"] = 1.0,
    max_position_pct: Annotated[float, "max position size as % of account (e.g. 10.0)"] = 10.0,
) -> str:
    """Return technically anchored entry/stop-loss/take-profit suggestions as JSON.

    The tool pulls OHLCV via the existing vendor router (get_stock_data), then computes:
    - swing high/low anchors over a configurable window
    - ATR-based stop distance
    - a simple trend/bias heuristic (SMA50 vs SMA200 when available + RSI)
    - market regime (trend vs range) using trend strength + SMA50 slope + volatility
    - take-profit using fixed or adaptive risk-reward multiple
    - optional partial take profits and ATR trailing-stop guidance
    - optional position sizing given account_size and risk_per_trade_pct
    """
    try:
        datetime.strptime(curr_date, "%Y-%m-%d")
        start = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_days)).strftime("%Y-%m-%d")
        raw = route_to_vendor("get_stock_data", symbol, start, curr_date)
        csv = _extract_csv(raw)
        df = pd.read_csv(StringIO(csv), index_col=0, parse_dates=True)
        needed = {"High", "Low", "Close"}
        if not needed.issubset(set(df.columns)):
            raise ValueError(f"missing OHLCV columns: {sorted(list(needed - set(df.columns)))}")
        if len(df) < max(atr_period + 2, swing_window + 2, 210):
            df_sorted = df.sort_index()
        else:
            df_sorted = df.sort_index()

        row = _asof_row(df_sorted, curr_date)
        close = float(row["Close"])
        atr = _atr(df_sorted, atr_period)
        rsi = _rsi(df_sorted["Close"], 14)

        close_series = df_sorted["Close"]
        sma50_series = _sma_series(close_series, 50) if len(close_series) >= 55 else None
        sma200_series = _sma_series(close_series, 200) if len(close_series) >= 205 else None
        sma50 = float(sma50_series.dropna().iloc[-1]) if sma50_series is not None and not sma50_series.dropna().empty else None
        sma200 = float(sma200_series.dropna().iloc[-1]) if sma200_series is not None and not sma200_series.dropna().empty else None

        tail = df_sorted.tail(max(swing_window, atr_period, 30))
        swing_low = float(tail["Low"].tail(swing_window).min())
        swing_high = float(tail["High"].tail(swing_window).max())

        atr_pct = atr / close if close else 0.0
        range_pct = (swing_high - swing_low) / close if close else 0.0

        trend_strength = 0.0
        if sma50 is not None and sma200 is not None and close:
            trend_strength = abs(sma50 - sma200) / close
        elif sma50 is not None and close:
            trend_strength = abs(close - sma50) / close

        sma50_slope = 0.0
        if sma50_series is not None:
            s = sma50_series.dropna()
            if len(s) >= 12:
                sma50_slope = float((s.iloc[-1] - s.iloc[-11]) / s.iloc[-11])

        regime = "unknown"
        regime_confidence = 0.4
        if trend_strength >= 0.02 and abs(sma50_slope) >= 0.002:
            regime = "trend"
            regime_confidence = _clamp(0.6 + trend_strength * 5.0, 0.0, 1.0)
        elif range_pct <= max(0.08, 6.0 * atr_pct):
            regime = "range"
            regime_confidence = _clamp(0.55 + (0.08 - range_pct) * 3.0, 0.0, 1.0)

        bias = "neutral"
        if direction.lower() in ("long", "short"):
            bias = direction.lower()
        else:
            if sma50 is not None and sma200 is not None:
                if sma50 > sma200 and rsi < 80:
                    bias = "long"
                elif sma50 < sma200 and rsi > 20:
                    bias = "short"
            else:
                if rsi >= 60:
                    bias = "long"
                elif rsi <= 40:
                    bias = "short"

        rr_base = float(rr)
        rr_target = rr_base
        if adaptive_rr:
            rr_target = rr_base + (trend_strength * 20.0) - (atr_pct * 6.0)
            if regime == "range":
                rr_target = rr_base - 0.4 - (atr_pct * 3.0)
            rr_target = _clamp(rr_target, 1.2, 3.0)

        entry_price = close
        entry_condition = "Use the analysis-date close as the reference; enter on next session only after confirmation."
        stop_loss = None
        take_profit = None
        take_profit_1 = None
        take_profit_2 = None
        trailing_stop_atr_mult = None
        trailing_stop_rule = None

        if regime == "range":
            if bias == "long":
                entry_price = min(close, swing_low + 0.25 * atr)
                stop_loss = swing_low - 0.75 * atr
                risk = entry_price - stop_loss
                take_profit_1 = entry_price + 1.0 * risk
                take_profit_2 = min(swing_high - 0.25 * atr, entry_price + rr_target * risk)
                take_profit = take_profit_2
                entry_condition = (
                    f"Range mean-reversion long: enter near support {round(swing_low, 2)} "
                    f"(<= {round(swing_low + 0.25 * atr, 2)}), ideally with RSI <= 45; "
                    f"avoid chasing a breakout in a range."
                )
            elif bias == "short":
                entry_price = max(close, swing_high - 0.25 * atr)
                stop_loss = swing_high + 0.75 * atr
                risk = stop_loss - entry_price
                take_profit_1 = entry_price - 1.0 * risk
                take_profit_2 = max(swing_low + 0.25 * atr, entry_price - rr_target * risk)
                take_profit = take_profit_2
                entry_condition = (
                    f"Range mean-reversion short: enter near resistance {round(swing_high, 2)} "
                    f"(>= {round(swing_high - 0.25 * atr, 2)}), ideally with RSI >= 55; "
                    f"avoid shorting the bottom of a range."
                )
        else:
            if bias == "long":
                breakout_level = swing_high
                retest_floor = breakout_level - 0.5 * atr
                stop_loss = min(close - 1.5 * atr, swing_low - 0.2 * atr)
                if confirmation:
                    entry_price = breakout_level + 0.05 * atr
                    entry_condition = (
                        f"Trend long (confirmation): wait for close above {round(breakout_level, 2)}; "
                        f"then enter on a retest that holds >= {round(retest_floor, 2)} and reclaims the breakout area."
                    )
                else:
                    entry_price = close
                    entry_condition = (
                        f"Trend long: enter after a close above {round(breakout_level, 2)} "
                        f"or on a pullback holding above {round(sma50, 2) if sma50 is not None else 'SMA50'}."
                    )
                risk = entry_price - stop_loss
                take_profit_1 = entry_price + 1.0 * risk
                take_profit_2 = entry_price + rr_target * risk
                take_profit = take_profit_2
                trailing_stop_atr_mult = 2.0 if atr_pct < 0.03 else 2.5
                trailing_stop_rule = f"Trailing stop (trend): close - {trailing_stop_atr_mult}*ATR({atr_period})."
            elif bias == "short":
                breakdown_level = swing_low
                retest_ceiling = breakdown_level + 0.5 * atr
                stop_loss = max(close + 1.5 * atr, swing_high + 0.2 * atr)
                if confirmation:
                    entry_price = breakdown_level - 0.05 * atr
                    entry_condition = (
                        f"Trend short (confirmation): wait for close below {round(breakdown_level, 2)}; "
                        f"then enter on a retest that holds <= {round(retest_ceiling, 2)} and rejects the breakdown area."
                    )
                else:
                    entry_price = close
                    entry_condition = (
                        f"Trend short: enter after a close below {round(breakdown_level, 2)} "
                        f"or on a rejection near {round(sma50, 2) if sma50 is not None else 'SMA50'}."
                    )
                risk = stop_loss - entry_price
                take_profit_1 = entry_price - 1.0 * risk
                take_profit_2 = entry_price - rr_target * risk
                take_profit = take_profit_2
                trailing_stop_atr_mult = 2.0 if atr_pct < 0.03 else 2.5
                trailing_stop_rule = f"Trailing stop (trend): close + {trailing_stop_atr_mult}*ATR({atr_period})."

        sizing = None
        sizing_note = None
        if stop_loss is not None and account_size is not None and account_size > 0:
            risk_amount = account_size * (risk_per_trade_pct / 100.0)
            per_unit_risk = abs(entry_price - stop_loss)
            if per_unit_risk > 0:
                units = int(risk_amount // per_unit_risk)
                max_value = account_size * (max_position_pct / 100.0)
                if units * entry_price > max_value and entry_price > 0:
                    units = int(max_value // entry_price)
                sizing = {
                    "account_size": float(account_size),
                    "risk_per_trade_pct": float(risk_per_trade_pct),
                    "max_position_pct": float(max_position_pct),
                    "risk_amount": _round_price(risk_amount),
                    "per_unit_risk": _round_price(per_unit_risk),
                    "units": int(max(units, 0)),
                    "position_value": _round_price(max(units, 0) * entry_price),
                }
        else:
            sizing_note = (
                "Sizing formula: units = floor((account_size * risk_per_trade_pct) / abs(entry - stop)). "
                "Also cap by max_position_pct of account."
            )

        payload: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "asof": curr_date,
            "regime": regime,
            "regime_confidence": float(round(regime_confidence, 2)),
            "bias": bias,
            "entry_condition": entry_condition,
            "entry_price": _round_price(entry_price),
            "stop_loss": _round_price(stop_loss),
            "take_profit": _round_price(take_profit),
            "take_profit_1": _round_price(take_profit_1),
            "take_profit_2": _round_price(take_profit_2),
            "rr_target": float(round(rr_target, 2)),
            "trailing_stop_atr_mult": trailing_stop_atr_mult,
            "trailing_stop_rule": trailing_stop_rule,
            "position_sizing": sizing,
            "position_sizing_note": sizing_note,
            "anchors": {
                "swing_window": int(swing_window),
                "swing_low": _round_price(swing_low),
                "swing_high": _round_price(swing_high),
                "atr_period": int(atr_period),
                "atr": _round_price(atr),
                "atr_pct": float(round(atr_pct, 4)),
                "rsi_14": _round_price(rsi),
                "sma50": _round_price(sma50) if sma50 is not None else None,
                "sma200": _round_price(sma200) if sma200 is not None else None,
                "trend_strength": float(round(trend_strength, 4)),
                "sma50_slope_10d": float(round(sma50_slope, 4)),
                "range_pct": float(round(range_pct, 4)),
            },
            "levels_rationale": (
                "Entry uses the latest available close as a reference. "
                "Stop-loss uses swing/ATR anchors to reduce noise stops; "
                f"take-profit uses RR={rr_target:.2f} based on stop distance (with partial TP at 1R when available)."
                if bias in ("long", "short")
                else "Bias is neutral; do not force a trade when trend/edge is unclear."
            ),
        }
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        return tool_error_text(tool="suggest_trade_levels", error=exc)
