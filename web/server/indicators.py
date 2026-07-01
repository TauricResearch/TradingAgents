"""Market indicator definitions and checks for the dashboard."""

from __future__ import annotations

import contextlib
import io
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import pandas as pd
import requests
import yfinance as yf

from . import storage

log = logging.getLogger(__name__)

IndicatorKind = Literal[
    "vix",
    "fear_greed",
    "red_days",
    "s5fi",
    "green_streak",
    "price_vs_moving_averages",
    "ticker_price",
]

CNN_FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
REQUEST_TIMEOUT = 15
MA_WATCHLIST: tuple[tuple[str, str], ...] = (
    ("^GSPC", "S&P 500"),
    ("QQQ", "QQQ"),
    ("IBIT", "IBIT"),
    ("TA125", "TA125"),
)
MA_WINDOWS: tuple[int, ...] = (50, 150, 200)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass(frozen=True)
class IndicatorDefinition:
    id: str
    kind: IndicatorKind
    name: str
    description: str
    threshold: float
    comparator: Literal["above", "below", "at_least", "within"]
    unit: str
    enabled: bool = True
    source: Literal["builtin", "custom"] = "builtin"
    ticker: str | None = None  # only for ticker_price kind
    triggered: bool = False    # one-shot state


DEFAULT_INDICATORS: list[IndicatorDefinition] = [
    IndicatorDefinition(
        id="vix",
        kind="vix",
        name="VIX",
        description="Triggered when the CBOE Volatility Index is above the threshold.",
        threshold=30,
        comparator="above",
        unit="index",
    ),
    IndicatorDefinition(
        id="fear_greed",
        kind="fear_greed",
        name="Fear & Greed",
        description="Triggered when CNN Fear & Greed drops below the threshold.",
        threshold=10,
        comparator="below",
        unit="score",
    ),
    IndicatorDefinition(
        id="red_days",
        kind="red_days",
        name="Consecutive red days",
        description="Triggered when the S&P 500 has enough consecutive down sessions.",
        threshold=3,
        comparator="at_least",
        unit="days",
    ),
    IndicatorDefinition(
        id="s5fi",
        kind="s5fi",
        name="S5FI breadth",
        description="Triggered when fewer than this percent of S&P 500 stocks are above their 50-day MA.",
        threshold=20,
        comparator="below",
        unit="%",
    ),
    IndicatorDefinition(
        id="green_streak",
        kind="green_streak",
        name="Consecutive green days",
        description="Triggered when the S&P 500 has an extended green-session streak.",
        threshold=11,
        comparator="at_least",
        unit="days",
    ),
    IndicatorDefinition(
        id="price_vs_moving_averages",
        kind="price_vs_moving_averages",
        name="Price near 50/150/200-day MA",
        description="Triggered when SPY proxies are within the configured percent of key moving averages.",
        threshold=0.01,
        comparator="within",
        unit="ratio",
    ),
]


def _config_path():
    return storage.data_dir() / "indicators.json"


def _definition_to_dict(defn: IndicatorDefinition) -> dict[str, Any]:
    result = {
        "id": defn.id,
        "kind": defn.kind,
        "name": defn.name,
        "description": defn.description,
        "threshold": defn.threshold,
        "comparator": defn.comparator,
        "unit": defn.unit,
        "enabled": defn.enabled,
        "source": defn.source,
    }
    if defn.ticker is not None:
        result["ticker"] = defn.ticker
    result["triggered"] = defn.triggered
    return result


def _definition_from_dict(data: dict[str, Any]) -> IndicatorDefinition:
    return IndicatorDefinition(
        id=str(data["id"]),
        kind=str(data.get("kind", "vix")),  # type: ignore[arg-type]
        name=str(data.get("name", data["id"])),
        description=str(data.get("description", "")),
        threshold=float(data.get("threshold", 0)),
        comparator=str(data.get("comparator", "above")),  # type: ignore[arg-type]
        unit=str(data.get("unit", "")),
        enabled=bool(data.get("enabled", True)),
        source=str(data.get("source", "custom")),  # type: ignore[arg-type]
        ticker=data.get("ticker"),
        triggered=bool(data.get("triggered", False)),
    )


def read_indicators() -> list[IndicatorDefinition]:
    payload = storage.read_json(_config_path())
    if not payload:
        write_indicators(DEFAULT_INDICATORS)
        return DEFAULT_INDICATORS
    return [_definition_from_dict(item) for item in payload.get("indicators", [])]


def write_indicators(indicators: list[IndicatorDefinition]) -> None:
    storage.write_json_atomic(
        _config_path(),
        {"indicators": [_definition_to_dict(defn) for defn in indicators]},
    )


def add_indicator(body: dict[str, Any]) -> IndicatorDefinition:
    kind = str(body.get("kind", "vix"))

    # Validate kind is supported
    supported_kinds = {d.kind for d in DEFAULT_INDICATORS} | {"ticker_price"}
    if kind not in supported_kinds:
        raise ValueError(f"unsupported indicator kind: {kind}")

    # For ticker_price, validate ticker is provided
    ticker = body.get("ticker")
    if kind == "ticker_price":
        if not ticker:
            raise ValueError("ticker is required for ticker_price alerts")
        ticker = str(ticker).upper()
        # Validate ticker exists
        try:
            yf.Ticker(ticker).fast_info["lastPrice"]
        except Exception:
            raise ValueError(f"Ticker '{ticker}' not found. Please check the symbol.")

    # Get base definition for defaults
    if kind == "ticker_price":
        # Create a base definition for ticker_price
        base = IndicatorDefinition(
            id="",
            kind="ticker_price",
            name=f"{ticker} Alert",
            description=f"Alert when {ticker} reaches the target price.",
            threshold=0,
            comparator="above",
            unit="price",
            ticker=ticker,
        )
    else:
        base = next(d for d in DEFAULT_INDICATORS if d.kind == kind)

    name = str(body.get("name") or base.name).strip()
    threshold = float(body.get("threshold", base.threshold))
    comparator = str(body.get("comparator", base.comparator))
    indicator_id = _slugify(str(body.get("id") or name or kind))

    rows = read_indicators()
    existing_ids = {row.id for row in rows}
    if indicator_id in existing_ids:
        suffix = 2
        while f"{indicator_id}-{suffix}" in existing_ids:
            suffix += 1
        indicator_id = f"{indicator_id}-{suffix}"

    # Check for duplicate ticker_price alerts
    if kind == "ticker_price":
        for row in rows:
            if (
                row.kind == "ticker_price"
                and row.ticker == ticker
                and row.comparator == comparator
                and row.threshold == threshold
            ):
                raise ValueError(f"Alert already exists for {ticker} {comparator} ${threshold}")

    row = IndicatorDefinition(
        id=indicator_id,
        kind=base.kind,
        name=name,
        description=str(body.get("description") or base.description),
        threshold=threshold,
        comparator=comparator,
        unit=base.unit,
        source="custom",
        enabled=bool(body.get("enabled", True)),
        ticker=ticker,
        triggered=False,
    )
    write_indicators([*rows, row])
    return row


def remove_indicator(indicator_id: str) -> bool:
    rows = read_indicators()
    next_rows = [row for row in rows if row.id != indicator_id]
    if len(next_rows) == len(rows):
        return False
    write_indicators(next_rows)
    return True


def update_indicator(indicator_id: str, body: dict[str, Any]) -> IndicatorDefinition | None:
    rows = read_indicators()
    for i, row in enumerate(rows):
        if row.id == indicator_id:
            new_threshold = body.get("threshold")
            if new_threshold is not None:
                try:
                    new_threshold = float(new_threshold)
                except (TypeError, ValueError):
                    raise ValueError("threshold must be a number") from None
            new_enabled = body.get("enabled")
            if new_enabled is not None:
                if not isinstance(new_enabled, bool):
                    raise ValueError("enabled must be a boolean")
            new_comparator = body.get("comparator")
            if new_comparator is not None:
                if new_comparator not in ("above", "below", "at_least", "within"):
                    raise ValueError("comparator must be one of: above, below, at_least, within")
            new_ticker = body.get("ticker")
            new_triggered = body.get("triggered")
            if new_triggered is not None:
                if not isinstance(new_triggered, bool):
                    raise ValueError("triggered must be a boolean")

            rows[i] = IndicatorDefinition(
                id=row.id,
                kind=row.kind,
                name=row.name,
                description=row.description,
                threshold=new_threshold if new_threshold is not None else row.threshold,
                comparator=new_comparator if new_comparator is not None else row.comparator,
                unit=row.unit,
                enabled=new_enabled if new_enabled is not None else row.enabled,
                source=row.source,
                ticker=new_ticker if new_ticker is not None else row.ticker,
                triggered=new_triggered if new_triggered is not None else row.triggered,
            )
            write_indicators(rows)
            return rows[i]
    return None


def reset_indicator(indicator_id: str) -> IndicatorDefinition | None:
    """Reset a single indicator's triggered state to False (re-arm one-shot alert)."""
    rows = read_indicators()
    for i, row in enumerate(rows):
        if row.id == indicator_id:
            if not row.triggered:
                return row  # Already active, no change needed
            rows[i] = IndicatorDefinition(
                id=row.id,
                kind=row.kind,
                name=row.name,
                description=row.description,
                threshold=row.threshold,
                comparator=row.comparator,
                unit=row.unit,
                enabled=row.enabled,
                source=row.source,
                ticker=row.ticker,
                triggered=False,
            )
            write_indicators(rows)
            return rows[i]
    return None


def reset_indicators() -> list[IndicatorDefinition]:
    write_indicators(DEFAULT_INDICATORS)
    return DEFAULT_INDICATORS


def run_checks() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for defn in read_indicators():
        if not defn.enabled:
            results.append({"indicator": _definition_to_dict(defn), "result": None})
            continue
        try:
            value = _fetch_value(defn)
            triggered, message = _evaluate(defn, value)
            results.append(
                {
                    "indicator": _definition_to_dict(defn),
                    "result": {
                        "triggered": triggered,
                        "value": value,
                        "threshold": defn.threshold,
                        "message": message,
                        "checked_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("indicator check failed: %s", defn.id)
            results.append(
                {
                    "indicator": _definition_to_dict(defn),
                    "result": {
                        "triggered": False,
                        "value": None,
                        "threshold": defn.threshold,
                        "message": f"Error fetching data: {exc}",
                        "checked_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
                    },
                }
            )
    return results


def _fetch_value(defn: IndicatorDefinition) -> Any:
    if defn.kind == "vix":
        return _fetch_latest_close("^VIX", "5d")
    if defn.kind == "fear_greed":
        resp = requests.get(
            CNN_FEAR_GREED_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TradingAgents/1.0)"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return float(resp.json()["fear_and_greed"]["score"])
    if defn.kind == "red_days":
        return _count_streak(red=True, count=int(defn.threshold))
    if defn.kind == "green_streak":
        return _count_streak(red=False, count=int(defn.threshold))
    if defn.kind == "s5fi":
        return _fetch_s5fi()
    if defn.kind == "price_vs_moving_averages":
        return _fetch_price_vs_moving_averages()
    raise ValueError(f"unsupported indicator kind: {defn.kind}")


def _evaluate(defn: IndicatorDefinition, value: Any) -> tuple[bool, str]:
    if defn.kind == "vix":
        triggered = float(value) > defn.threshold
        return triggered, f"VIX is {float(value):.2f}, {'above' if triggered else 'below'} threshold {defn.threshold:.0f}."
    if defn.kind == "fear_greed":
        triggered = float(value) < defn.threshold
        return triggered, f"Fear & Greed is {float(value):.1f} ({_fear_label(float(value))}), threshold {defn.threshold:.0f}."
    if defn.kind == "red_days":
        triggered = int(value) >= int(defn.threshold)
        return triggered, f"{int(value)} consecutive red day(s); threshold is {int(defn.threshold)}."
    if defn.kind == "green_streak":
        triggered = int(value) >= int(defn.threshold)
        return triggered, f"{int(value)} consecutive green day(s); threshold is {int(defn.threshold)}."
    if defn.kind == "s5fi":
        triggered = float(value) < defn.threshold
        return triggered, f"S5FI is {float(value):.1f}% above 50-day MA; threshold is {defn.threshold:.0f}%."
    if defn.kind == "price_vs_moving_averages":
        hits = []
        for snapshot in value["snapshots"]:
            for window in MA_WINDOWS:
                average = snapshot["moving_averages"][window]
                distance = snapshot["distances"][window]
                if distance <= defn.threshold:
                    hits.append(
                        f"{snapshot['label']} close {snapshot['close']:.2f} is within {distance * 100:.2f}% of {window}-day MA ({average:.2f})"
                    )
        if hits:
            return True, "; ".join(hits) + "."
        nearest = value["nearest_match"]
        if nearest is None:
            return False, "No data available for watched moving-average tickers."
        return False, (
            f"Closest: {nearest['label']} is {nearest['distance_ratio'] * 100:.2f}% "
            f"from its {nearest['window']}-day MA; trigger is {defn.threshold * 100:.2f}%."
        )
    return False, "Unsupported indicator."


def _fetch_latest_close(symbol: str, period: str) -> float:
    hist = yf.Ticker(symbol).history(period=period, timeout=30)
    if hist.empty:
        raise ValueError(f"No data returned from yfinance for {symbol}.")
    return float(hist["Close"].iloc[-1])


def _count_streak(red: bool, count: int) -> int:
    hist = yf.Ticker("^GSPC").history(period="3mo")
    if hist.empty:
        raise ValueError("No S&P 500 data returned from yfinance.")
    closes = hist["Close"].tail(count + 5).tolist()
    streak = 0
    for i in range(len(closes) - 1, 0, -1):
        if (closes[i] < closes[i - 1]) if red else (closes[i] > closes[i - 1]):
            streak += 1
        else:
            break
    return streak


def _fetch_price_vs_moving_averages() -> dict[str, Any]:
    snapshots: list[dict[str, Any]] = []
    nearest_match: dict[str, Any] | None = None
    min_distance_ratio: float | None = None
    for ticker_symbol, label in MA_WATCHLIST:
        try:
            hist = yf.Ticker(ticker_symbol).history(period="2y")
            closes = hist["Close"].dropna()
            if len(closes) < max(MA_WINDOWS):
                raise ValueError(f"Only {len(closes)} sessions available.")
            close = float(closes.iloc[-1])
            moving_averages = {
                window: float(closes.rolling(window).mean().iloc[-1])
                for window in MA_WINDOWS
            }
        except Exception as exc:  # noqa: BLE001
            log.warning("Skipping %s moving average check: %s", ticker_symbol, exc)
            continue
        distances = {window: abs(close - avg) / avg for window, avg in moving_averages.items()}
        ticker_nearest_window = min(distances, key=distances.get)
        ticker_nearest = {
            "label": label,
            "ticker": ticker_symbol,
            "close": close,
            "window": ticker_nearest_window,
            "average": moving_averages[ticker_nearest_window],
            "distance_ratio": distances[ticker_nearest_window],
        }
        ticker_min = min(distances.values())
        if min_distance_ratio is None or ticker_min < min_distance_ratio:
            min_distance_ratio = ticker_min
        if nearest_match is None or ticker_nearest["distance_ratio"] < nearest_match["distance_ratio"]:
            nearest_match = ticker_nearest
        snapshots.append(
            {
                "ticker": ticker_symbol,
                "label": label,
                "close": close,
                "moving_averages": moving_averages,
                "distances": distances,
            }
        )
    return {
        "proximity_ratio": min_distance_ratio if min_distance_ratio is not None else float("inf"),
        "nearest_match": nearest_match,
        "snapshots": snapshots,
    }


def _fetch_s5fi() -> float:
    components = list(_get_sp500_components())
    with contextlib.redirect_stdout(io.StringIO()):
        raw = yf.download(
            tickers=components,
            period="3mo",
            auto_adjust=True,
            progress=False,
            threads=True,
            timeout=30,
        )
    closes: pd.DataFrame = raw["Close"]
    if closes.empty:
        raise ValueError("yf.download returned no S5FI data.")
    closes = closes.dropna(axis=1, thresh=50)
    last_close = closes.iloc[-1]
    last_sma50 = closes.rolling(50).mean().iloc[-1]
    valid = last_close.notna() & last_sma50.notna()
    total = int(valid.sum())
    if total == 0:
        raise ValueError("No valid S5FI tickers after SMA50 computation.")
    above = int((last_close[valid] > last_sma50[valid]).sum())
    return round(above / total * 100.0, 2)


_SP500_COMPONENTS: list[tuple[tuple[str, ...], datetime] | None] = [None]


def _get_sp500_components() -> tuple[str, ...]:
    cached = _SP500_COMPONENTS[0]
    if cached is not None and (datetime.now(UTC) - cached[1]).total_seconds() < 3600:
        return cached[0]
    resp = requests.get(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    tables = pd.read_html(pd.io.common.StringIO(resp.text), flavor="lxml")
    tickers = tuple(tables[0]["Symbol"].str.replace(".", "-", regex=False).tolist())
    _SP500_COMPONENTS[0] = (tickers, datetime.now(UTC))
    return tickers


def _fear_label(score: float) -> str:
    if score <= 20:
        return "Extreme Fear"
    if score <= 40:
        return "Fear"
    if score <= 60:
        return "Neutral"
    if score <= 80:
        return "Greed"
    return "Extreme Greed"


def _slugify(value: str) -> str:
    out = []
    for char in value.lower():
        if char.isalnum():
            out.append(char)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-") or "indicator"
