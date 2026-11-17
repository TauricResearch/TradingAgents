"""
metaapi_client.py
=================
Read-only market-data feed for the AI Co-Pilot dashboard, backed by MetaApi.

Design goals
------------
* **Zero price discrepancy** - every candle, quote and orderbook snapshot comes
  straight from the same MetaApi bridge the MT5 terminal uses (connect with an
  *investor / read-only* password). The dashboard never places orders.
* **Sync facade over an async SDK** - ``metaapi-cloud-sdk`` is asyncio-only, but
  Streamlit runs a synchronous script. :class:`MetaApiFeed` owns a dedicated
  asyncio event loop in a daemon thread and exposes plain synchronous methods.
* **Never crash the dashboard** - every network call is wrapped; on failure the
  feed degrades to a deterministic offline simulator (``offline`` mode) so the
  UI still renders on Streamlit Community Cloud with no credentials configured.

Typical use::

    feed = MetaApiFeed()
    feed.configure(token=..., account_id=..., offline=False)
    df = feed.fetch_frame("EURUSD", "15m", 240)     # OHLCV + EMA50/200 + RSI14 + ATR14
    px = feed.quote("EURUSD")                        # {"bid":..., "ask":...}
    book = feed.orderbook("EURUSD")                  # {"bids":[...], "asks":[...]}
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

LOGGER = logging.getLogger("copilot.metaapi")

# User-facing timeframe -> MetaApi timeframe code.
TIMEFRAMES: Dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}

# Minutes per timeframe, used by the offline simulator.
_TF_MINUTES: Dict[str, int] = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440,
}


class DataFeedError(RuntimeError):
    """Raised when market data cannot be retrieved (surfaced neatly in the UI)."""


# --------------------------------------------------------------------------- #
# Async plumbing
# --------------------------------------------------------------------------- #
class _AsyncRunner:
    """Owns a private asyncio event loop in a daemon thread.

    Lets synchronous (Streamlit) code drive an asyncio-only SDK without blocking
    the script thread and without touching Streamlit internals.
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_forever, name="copilot-async", daemon=True)
        self._thread.start()

    def _run_forever(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro: Any, timeout: float = 30.0) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def close(self) -> None:
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:  # pragma: no cover - best effort shutdown
            pass


# --------------------------------------------------------------------------- #
# Symbol metadata
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SymbolSpec:
    """Minimal instrument metadata for position sizing.

    ``value_per_price_unit_per_lot`` is the P&L (in account currency, assumed USD)
    produced by a *one unit* move in price for a *one lot* position. For a
    USD-quoted FX major 1 lot = 100,000 units -> 100,000 per 1.0 price move.
    """

    value_per_price_unit_per_lot: float = 100_000.0
    digits: int = 5
    min_lot: float = 0.01
    max_lot: float = 0.02
    lot_step: float = 0.01


# Sensible defaults; override per deployment if your broker differs.
_SYMBOL_SPECS: Dict[str, SymbolSpec] = {
    "EURUSD": SymbolSpec(100_000.0, 5),
    "GBPUSD": SymbolSpec(100_000.0, 5),
    "AUDUSD": SymbolSpec(100_000.0, 5),
    "NZDUSD": SymbolSpec(100_000.0, 5),
    "USDCAD": SymbolSpec(100_000.0, 5),
    "USDCHF": SymbolSpec(100_000.0, 5),
    "USDJPY": SymbolSpec(100_000.0, 3),
    "XAUUSD": SymbolSpec(100.0, 2),
    "XAGUSD": SymbolSpec(5_000.0, 3),
    "BTCUSD": SymbolSpec(1.0, 2),
    "ETHUSD": SymbolSpec(1.0, 2),
}


def symbol_spec(symbol: str) -> SymbolSpec:
    """Return the :class:`SymbolSpec` for ``symbol`` (case-insensitive)."""
    return _SYMBOL_SPECS.get(symbol.upper(), SymbolSpec())


# --------------------------------------------------------------------------- #
# Indicators
# --------------------------------------------------------------------------- #
def add_indicators(df: pd.DataFrame, ema_fast: int = 50, ema_slow: int = 200, rsi_period: int = 14) -> pd.DataFrame:
    """Attach EMA(fast), EMA(slow), RSI(rsi_period) and ATR(14) columns."""
    if df.empty:
        return df
    out = df.copy()
    out[f"ema{ema_fast}"] = out["close"].ewm(span=ema_fast, adjust=False).mean()
    out[f"ema{ema_slow}"] = out["close"].ewm(span=ema_slow, adjust=False).mean()

    delta = out["close"].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / rsi_period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out[f"rsi{rsi_period}"] = (100 - (100 / (1 + rs))).fillna(50.0)

    prev_close = out["close"].shift(1)
    true_range = pd.concat(
        [(out["high"] - out["low"]), (out["high"] - prev_close).abs(), (out["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    out["atr14"] = true_range.ewm(alpha=1 / 14, adjust=False).mean()
    return out


def rsi_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return add_indicators(df, rsi_period=period)[f"rsi{period}"]


# --------------------------------------------------------------------------- #
# The feed
# --------------------------------------------------------------------------- #
@dataclass
class _Config:
    token: str = ""
    account_id: str = ""
    platform: str = "mt5"
    offline: bool = False

    def key(self) -> Tuple[str, str, str, bool]:
        return (self.token, self.account_id, self.platform, self.offline)


class MetaApiFeed:
    """Synchronous, read-only market-data facade over MetaApi (offline-capable)."""

    def __init__(self) -> None:
        self._runner = _AsyncRunner()
        self._api: Any = None
        self._account: Any = None
        self._conn: Any = None
        self._cfg = _Config()
        self._lock = threading.RLock()
        self._last_error: str = ""
        # Cached specs returned by MetaApi (falls back to the local table).
        self._specs: Dict[str, SymbolSpec] = {}
        # Offline simulator state: symbol -> last price.
        self._sim_price: Dict[str, float] = {}
        self._connected = False

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    @property
    def offline(self) -> bool:
        return self._cfg.offline or not (self._cfg.token and self._cfg.account_id)

    @property
    def connected(self) -> bool:
        return self._connected or self.offline

    @property
    def last_error(self) -> str:
        return self._last_error

    def configure(self, token: str = "", account_id: str = "", platform: str = "mt5", offline: bool = False) -> None:
        """Point the feed at an account. Reconnects only when something changed."""
        new_cfg = _Config((token or "").strip(), (account_id or "").strip(), platform or "mt5", bool(offline))
        with self._lock:
            if new_cfg.key() == self._cfg.key():
                return
            self._cfg = new_cfg
            self._last_error = ""
            if new_cfg.offline or not (new_cfg.token and new_cfg.account_id):
                self._connected = True  # offline simulator is "connected"
                return
            try:
                self._runner.run(self._connect(), timeout=60.0)
                self._connected = True
            except Exception as exc:  # noqa: BLE001 - surface, don't crash
                self._connected = False
                self._last_error = str(exc)
                LOGGER.warning("MetaApi connection failed: %s", exc)

    def disconnect(self) -> None:
        with self._lock:
            self._connected = False
            if self._conn is not None:
                try:
                    self._runner.run(self._conn.close(), timeout=15.0)
                except Exception:  # noqa: BLE001
                    pass
            self._conn = None

    def close(self) -> None:
        self.disconnect()
        self._runner.close()

    async def _connect(self) -> None:
        from metaapi_cloud_sdk import MetaApi  # lazy import

        self._api = MetaApi(token=self._cfg.token)
        self._account = await self._api.metatrader_account_api.get_account(self._cfg.account_id)
        if self._account.state not in ("DEPLOYED",):
            await self._account.deploy()
        await self._account.wait_connected()
        self._conn = self._account.get_rpc_connection()
        await self._conn.connect()
        await self._conn.wait_synchronized({"timeoutInSeconds": 60})

    # ------------------------------------------------------------------ #
    # Account
    # ------------------------------------------------------------------ #
    def account_snapshot(self) -> Dict[str, Any]:
        """Return balance / equity / currency. In offline mode a demo balance."""
        if self.offline or self._conn is None:
            return {"balance": 2500.0, "equity": 2500.0, "currency": "USD", "offline": True}
        try:
            info = self._runner.run(self._conn.get_account_information(), timeout=20.0) or {}
            return {
                "balance": float(info.get("balance", 0.0)),
                "equity": float(info.get("equity", 0.0)),
                "currency": str(info.get("currency", "USD")),
                "offline": False,
            }
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            LOGGER.warning("account_snapshot failed: %s", exc)
            return {"balance": 0.0, "equity": 0.0, "currency": "USD", "offline": True, "error": str(exc)}

    # ------------------------------------------------------------------ #
    # Candles
    # ------------------------------------------------------------------ #
    def fetch_frame(self, symbol: str, timeframe: str, count: int = 240) -> pd.DataFrame:
        """Return an OHLCV frame (oldest first) enriched with EMA50/200, RSI14, ATR14."""
        tf = TIMEFRAMES.get(timeframe, timeframe)
        if self.offline or self._conn is None:
            frame = _simulate_candles(symbol, tf, count)
        else:
            try:
                frame = self._runner.run(self._fetch_candles(symbol, tf, count), timeout=30.0)
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
                LOGGER.warning("fetch_frame(%s,%s) failed: %s", symbol, timeframe, exc)
                frame = _simulate_candles(symbol, tf, count)
        frame.attrs["offline"] = self.offline
        return add_indicators(frame)

    async def _fetch_candles(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        minutes = _TF_MINUTES.get(timeframe, 15)
        start = datetime.now(timezone.utc) - timedelta(minutes=minutes * (count + 5))
        raw = await self._conn.get_historical_candles(symbol, timeframe, start, limit=count)
        rows = [
            {
                "time": pd.to_datetime(c["time"], utc=True),
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
                "volume": float(c.get("tickVolume", c.get("volume", 0.0)) or 0.0),
            }
            for c in raw
        ]
        frame = pd.DataFrame(rows)
        if frame.empty:
            raise DataFeedError(f"No candles returned for {symbol} {timeframe}.")
        return frame.sort_values("time").reset_index(drop=True)

    # ------------------------------------------------------------------ #
    # Quote & orderbook
    # ------------------------------------------------------------------ #
    def quote(self, symbol: str) -> Dict[str, Any]:
        """Best bid/ask for ``symbol`` (indicative in offline mode)."""
        if self.offline or self._conn is None:
            mid = _simulate_price(symbol)
            half = _simulated_spread(symbol)
            return {
                "symbol": symbol, "bid": round(mid - half, 6), "ask": round(mid + half, 6),
                "spread": round(2 * half, 6), "time": datetime.now(timezone.utc).isoformat(), "offline": True,
            }
        try:
            px = self._runner.run(self._conn.get_symbol_price(symbol), timeout=15.0) or {}
            bid, ask = float(px.get("bid", 0.0)), float(px.get("ask", 0.0))
            return {
                "symbol": symbol, "bid": bid, "ask": ask, "spread": round(ask - bid, 8),
                "time": datetime.now(timezone.utc).isoformat(), "offline": False,
            }
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            LOGGER.warning("quote(%s) failed: %s", symbol, exc)
            return {"symbol": symbol, "bid": 0.0, "ask": 0.0, "spread": 0.0,
                    "time": datetime.now(timezone.utc).isoformat(), "offline": True, "error": str(exc)}

    def orderbook(self, symbol: str, depth: int = 8) -> Dict[str, Any]:
        """Bid/ask ladder. Real depth when the broker streams it, else indicative.

        MetaApi only exposes full market depth for terminals that stream it, so we
        fall back to a deterministic ladder built around the live top-of-book.
        """
        q = self.quote(symbol)
        if not self.offline and self._conn is not None:
            try:
                book = self._runner.run(self._conn.get_book(symbol), timeout=15.0)
                bids = _book_side(book, "bids", depth)
                asks = _book_side(book, "asks", depth)
                if bids and asks:
                    return {"symbol": symbol, "bids": bids, "asks": asks,
                            "indicative": False, "offline": False}
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("get_book(%s) unavailable: %s", symbol, exc)
        bids, asks = _indicative_ladder(q, symbol, depth)
        return {"symbol": symbol, "bids": bids, "asks": asks, "indicative": True, "offline": q.get("offline", False)}

    # ------------------------------------------------------------------ #
    # Specs & bars summary
    # ------------------------------------------------------------------ #
    def spec(self, symbol: str) -> SymbolSpec:
        with self._lock:
            cached = self._specs.get(symbol.upper())
        if cached is not None:
            return cached
        if not self.offline and self._conn is not None:
            try:
                raw = self._runner.run(self._conn.get_symbol_specification(symbol), timeout=15.0) or {}
                contract = float(raw.get("contractSize", 0.0) or 0.0)
                if contract > 0:
                    min_volume = float(raw.get("minVolume", 0.01) or 0.01)
                    spec = SymbolSpec(
                        value_per_price_unit_per_lot=contract,
                        digits=int(raw.get("digits", 5) or 5),
                        min_lot=max(0.01, min_volume),
                        max_lot=float(raw.get("maxVolume", 100.0) or 100.0),
                    )
                    with self._lock:
                        self._specs[symbol.upper()] = spec
                    return spec
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("spec(%s) unavailable: %s", symbol, exc)
        return symbol_spec(symbol)


# --------------------------------------------------------------------------- #
# Offline simulator (deterministic per symbol+minute)
# --------------------------------------------------------------------------- #
_BASE_PRICES: Dict[str, float] = {
    "EURUSD": 1.0850, "GBPUSD": 1.2650, "AUDUSD": 0.6600, "NZDUSD": 0.6100,
    "USDCAD": 1.3600, "USDCHF": 0.8850, "USDJPY": 150.00,
    "XAUUSD": 2350.0, "XAGUSD": 28.00, "BTCUSD": 64000.0, "ETHUSD": 3200.0,
}


def _base_price(symbol: str) -> float:
    return _BASE_PRICES.get(symbol.upper(), 100.0)


def _seed(symbol: str) -> int:
    return abs(hash(symbol.upper())) % (2**31)


def _simulated_spread(symbol: str) -> float:
    base = _base_price(symbol)
    return max(base * 0.00005, 10 ** -symbol_spec(symbol).digits)


def _simulate_price(symbol: str) -> float:
    """Slow-moving pseudo-random walk keyed to the current minute."""
    rng = random.Random(_seed(symbol) + int(time.time() // 60))
    drift = math.sin(rng.random() * math.tau) * 0.0008
    return _base_price(symbol) * (1.0 + drift)


def _simulate_candles(symbol: str, timeframe: str, count: int) -> pd.DataFrame:
    """Deterministic OHLCV candles so the dashboard renders without credentials."""
    minutes = _TF_MINUTES.get(timeframe, 15)
    rng = random.Random(_seed(symbol) + minutes)
    base = _base_price(symbol)
    vol_scale = base * 0.0009
    price = base * (1.0 + rng.uniform(-0.01, 0.01))
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = now - timedelta(minutes=minutes * (count - 1))
    rows: List[Dict[str, Any]] = []
    for i in range(count):
        drift = math.sin(i / 24.0) * vol_scale * 0.35
        shock = rng.gauss(0.0, vol_scale)
        open_p = price
        close_p = max(open_p + drift + shock, base * 0.5)
        high_p = max(open_p, close_p) + abs(rng.gauss(0.0, vol_scale * 0.4))
        low_p = min(open_p, close_p) - abs(rng.gauss(0.0, vol_scale * 0.4))
        rows.append({
            "time": start + timedelta(minutes=minutes * i),
            "open": round(open_p, 6), "high": round(high_p, 6),
            "low": round(low_p, 6), "close": round(close_p, 6),
            "volume": round(abs(rng.gauss(120, 60)), 2),
        })
        price = close_p
    return pd.DataFrame(rows)


def _book_side(book: Any, side: str, depth: int) -> List[List[float]]:
    levels = (book or {}).get(side) or []
    out: List[List[float]] = []
    for level in levels[:depth]:
        try:
            out.append([float(level["price"]), float(level.get("volume", 0.0) or 0.0)])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _indicative_ladder(quote: Dict[str, Any], symbol: str, depth: int) -> Tuple[List[List[float]], List[List[float]]]:
    """Deterministic ladder around the live top-of-book (used when depth is absent)."""
    tick = max(_base_price(symbol) * 0.00005, 10 ** -symbol_spec(symbol).digits)
    bid0, ask0 = float(quote.get("bid", 0.0)), float(quote.get("ask", 0.0))
    rng = random.Random(_seed(symbol) + 7)
    bids, asks = [], []
    for i in range(depth):
        bids.append([round(bid0 - i * tick, 6), round(0.01 * (depth - i) + rng.uniform(0, 0.02), 3)])
        asks.append([round(ask0 + i * tick, 6), round(0.01 * (depth - i) + rng.uniform(0, 0.02), 3)])
    return bids, asks


__all__ = [
    "MetaApiFeed",
    "DataFeedError",
    "SymbolSpec",
    "symbol_spec",
    "add_indicators",
    "rsi_series",
    "TIMEFRAMES",
]
