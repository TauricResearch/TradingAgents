"""Explainable discovery of currently active equities by market region."""

from dataclasses import dataclass
from typing import Callable, Iterable

import pandas as pd
import yfinance as yf


DISCOVERY_REGIONS = {
    "us": ("AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "TSLA", "AVGO", "AMD", "JPM", "LLY", "NFLX", "ORCL", "PLTR"),
    "europe": ("AZN.L", "HSBA.L", "SHEL.L", "ULVR.L", "SAP.DE", "SIE.DE", "ALV.DE", "AIR.PA", "MC.PA", "OR.PA", "SU.PA", "ASML.AS", "INGA.AS", "NESN.SW", "NOVN.SW", "ENEL.MI", "ISP.MI", "SAN.MC"),
    "canada": ("SHOP.TO", "RY.TO", "TD.TO", "CNR.TO", "SU.TO"),
    "latin_america": ("VALE", "PBR", "ITUB", "NU", "MELI"),
    "japan": ("7203.T", "6758.T", "9984.T", "8035.T", "6861.T"),
    "china_hong_kong": ("0700.HK", "9988.HK", "3690.HK", "600519.SS", "601318.SS"),
    "india": ("RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"),
    "australia": ("BHP.AX", "CBA.AX", "CSL.AX", "WBC.AX", "RIO.AX"),
    "south_korea": ("005930.KS", "000660.KS", "035420.KS", "035720.KS"),
}
DISCOVERY_REGION_LABELS = {
    "us": "Estados Unidos", "europe": "Europa", "canada": "Canada",
    "latin_america": "Latinoamerica", "japan": "Japon",
    "china_hong_kong": "China y Hong Kong", "india": "India",
    "australia": "Australia", "south_korea": "Corea del Sur",
}
DEFAULT_DISCOVERY_UNIVERSE = tuple(
    symbol for region in DISCOVERY_REGIONS.values() for symbol in region
)


@dataclass(frozen=True)
class DiscoveryConfig:
    lookback_days: int = 20
    candidate_limit: int = 10
    minimum_history_days: int = 5
    momentum_weight: float = 0.55
    volume_weight: float = 0.30
    volatility_weight: float = 0.15


@dataclass(frozen=True)
class StockCandidate:
    symbol: str
    score: float
    latest_price: float
    return_percent: float
    relative_volume: float
    volatility_percent: float
    reasons: tuple[str, ...]


HistoryLoader = Callable[[str], pd.DataFrame]


def symbols_for_regions(regions: Iterable[str]) -> tuple[str, ...]:
    """Return a stable, de-duplicated universe for selected regions."""
    symbols = [symbol for region in regions for symbol in DISCOVERY_REGIONS.get(region, ())]
    return tuple(dict.fromkeys(symbols))


def _load_history(symbol: str, lookback_days: int) -> pd.DataFrame:
    return yf.Ticker(symbol).history(period=f"{max(lookback_days * 3, 60)}d")


def _is_equity_symbol(symbol: str) -> bool:
    """Reject common non-equity Yahoo symbol forms from the discovery universe."""
    return bool(symbol) and not any(marker in symbol for marker in ("^", "=", "-"))


def _bounded_percentile(value: float, low: float, high: float) -> float:
    if high <= low:
        return 50.0
    return max(0.0, min(100.0, (value - low) / (high - low) * 100.0))


def _candidate_from_history(
    symbol: str, history: pd.DataFrame, config: DiscoveryConfig
) -> StockCandidate | None:
    if not isinstance(history, pd.DataFrame) or not {"Close", "Volume"}.issubset(history.columns):
        return None

    clean = history[["Close", "Volume"]].dropna()
    if len(clean) < config.minimum_history_days + 1:
        return None

    window = clean.tail(config.lookback_days + 1)
    if len(window) < config.minimum_history_days + 1:
        return None

    closes = window["Close"].astype(float)
    volumes = window["Volume"].astype(float)
    latest_price = float(closes.iloc[-1])
    if latest_price <= 0:
        return None

    return_percent = float((latest_price / closes.iloc[0] - 1.0) * 100.0)
    prior_volumes = volumes.iloc[:-1]
    median_volume = float(prior_volumes.median())
    relative_volume = float(volumes.iloc[-1] / median_volume) if median_volume > 0 else 1.0
    daily_returns = closes.pct_change().dropna()
    volatility_percent = float(daily_returns.std(ddof=0) * 100.0)

    momentum_score = _bounded_percentile(return_percent, -10.0, 10.0)
    volume_score = _bounded_percentile(relative_volume, 0.5, 3.0)
    volatility_score = _bounded_percentile(volatility_percent, 0.5, 6.0)
    score = (
        momentum_score * config.momentum_weight
        + volume_score * config.volume_weight
        + volatility_score * config.volatility_weight
    )

    reasons = []
    if return_percent >= 3:
        reasons.append(f"momentum positivo ({return_percent:+.1f}% en el periodo)")
    elif return_percent <= -3:
        reasons.append(f"movimiento bajista ({return_percent:+.1f}% en el periodo)")
    if relative_volume >= 1.5:
        reasons.append(f"volumen relativo elevado ({relative_volume:.1f}x)")
    if volatility_percent >= 3:
        reasons.append(f"volatilidad elevada ({volatility_percent:.1f}%)")
    if not reasons:
        reasons.append("actividad de mercado estable, sin catalizador cuantitativo dominante")

    return StockCandidate(
        symbol=symbol,
        score=round(max(0.0, min(100.0, score)), 2),
        latest_price=round(latest_price, 4),
        return_percent=round(return_percent, 4),
        relative_volume=round(relative_volume, 4),
        volatility_percent=round(volatility_percent, 4),
        reasons=tuple(reasons),
    )


def discover_trending_stocks(
    symbols: Iterable[str] | None = None,
    config: DiscoveryConfig | None = None,
    history_loader: HistoryLoader | None = None,
) -> list[StockCandidate]:
    """Return ranked active equities from the configured US/EU universe."""
    config = config or DiscoveryConfig()
    selected_symbols = symbols or DEFAULT_DISCOVERY_UNIVERSE
    loader = history_loader or (lambda symbol: _load_history(symbol, config.lookback_days))
    candidates = []
    for symbol in selected_symbols:
        if not _is_equity_symbol(symbol):
            continue
        try:
            candidate = _candidate_from_history(symbol, loader(symbol), config)
        except Exception:
            candidate = None
        if candidate is not None:
            candidates.append(candidate)
    return sorted(candidates, key=lambda item: (-item.score, item.symbol))[: config.candidate_limit]