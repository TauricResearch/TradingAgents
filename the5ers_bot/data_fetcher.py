"""
data_fetcher.py
===============
Native MetaTrader 5 data connector for the AI Co-Pilot dashboard.

Uses the 100% free ``MetaTrader5`` Python package: :meth:`MT5Client.initialize`
attaches to the **local** MetaTrader 5 terminal and every price, candle and account
figure is read straight from it. No token, no cloud, no API key.

Robustness
----------
``MetaTrader5`` ships Windows wheels only. If the package is missing (Linux, macOS,
CI) or the terminal is closed / not logged in, the client flips to a deterministic
**offline simulator** so the dashboard still renders and can be smoke-tested - it
never raises.

Typical use::

    client = MT5Client()                       # defaults to EURUSD/GBPUSD/USDJPY/XAUUSD
    client.initialize()                        # -> True on a live terminal, False otherwise
    frame = client.fetch_frame("EURUSD", "15m", 300)   # OHLCV + EMA50/200 + RSI14 + ATR14
    tick  = client.tick("EURUSD")              # {"bid":..., "ask":..., "spread":...}
    acct  = client.account_info()              # {"balance":..., "equity":...}
"""

from __future__ import annotations

import logging
import math
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

LOGGER = logging.getLogger("copilot.mt5")

# Default watchlist - the four instruments requested for the co-pilot.
DEFAULT_SYMBOLS: List[str] = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]

# User-facing timeframe -> ``MetaTrader5`` constant name.
TIMEFRAMES: Dict[str, str] = {
    "1m": "TIMEFRAME_M1",
    "5m": "TIMEFRAME_M5",
    "15m": "TIMEFRAME_M15",
    "30m": "TIMEFRAME_M30",
    "1h": "TIMEFRAME_H1",
    "4h": "TIMEFRAME_H4",
    "1d": "TIMEFRAME_D1",
}

# Minutes per timeframe (offline simulator).
_TF_MINUTES: Dict[str, int] = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}

# MT5 deal types that represent *trade* activity:
#   0 = DEAL_TYPE_BUY, 1 = DEAL_TYPE_SELL
# Everything else (balance/deposit, credit, charge, correction, bonus, commission,
# ...) is account plumbing, NOT trade P&L. Feeding those to the daily guardrail is
# what made a $5,000 funding deal look like a +$5,000 profit target hit.
_DEAL_TYPE_BUY = 0
_DEAL_TYPE_SELL = 1
_TRADE_DEAL_TYPES = (_DEAL_TYPE_BUY, _DEAL_TYPE_SELL)


def load_mt5() -> Any:
    """Import the ``MetaTrader5`` package, or ``None`` when it is unavailable.

    The package only exists on Windows; everywhere else (Linux CI, macOS) the
    connector degrades to the offline simulator.
    """
    try:
        import MetaTrader5 as mt5  # type: ignore

        return mt5
    except Exception as exc:  # noqa: BLE001 - ImportError on non-Windows
        LOGGER.info("MetaTrader5 package unavailable (%s) - using offline simulator.", exc)
        return None


# --------------------------------------------------------------------------- #
# Symbol metadata
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SymbolSpec:
    """Instrument metadata needed for position sizing.

    ``value_per_price_unit_per_lot`` is the P&L (account currency, USD assumed)
    from a *one unit* price move on a *one lot* position, derived from the broker's
    own tick value / tick size so it always matches the terminal.
    """

    symbol: str
    digits: int = 5
    point: float = 0.00001
    contract_size: float = 100_000.0
    tick_value: float = 1.0
    tick_size: float = 0.00001
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01

    @property
    def value_per_price_unit_per_lot(self) -> float:
        if self.tick_size and self.tick_size > 0 and self.tick_value:
            return float(self.tick_value) / float(self.tick_size)
        return float(self.contract_size or 100_000.0)


# Sensible fallbacks for the offline simulator / exotic broker symbol names.
_FALLBACK_SPECS: Dict[str, Dict[str, Any]] = {
    "EURUSD": {"digits": 5, "point": 0.00001, "contract_size": 100_000.0, "tick_value": 1.0, "tick_size": 0.00001},
    "GBPUSD": {"digits": 5, "point": 0.00001, "contract_size": 100_000.0, "tick_value": 1.0, "tick_size": 0.00001},
    "USDJPY": {"digits": 3, "point": 0.001, "contract_size": 100_000.0, "tick_value": 0.671, "tick_size": 0.001},
    "XAUUSD": {"digits": 2, "point": 0.01, "contract_size": 100.0, "tick_value": 1.0, "tick_size": 0.01},
}


# --------------------------------------------------------------------------- #
# Indicators
# --------------------------------------------------------------------------- #
def add_indicators(df: pd.DataFrame, ema_fast: int = 50, ema_slow: int = 200, rsi_period: int = 14) -> pd.DataFrame:
    """Attach ``ema{fast}``, ``ema{slow}``, ``rsi{period}`` and ``atr14`` columns."""
    if df is None or df.empty:
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


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
@dataclass
class _Config:
    path: str = ""
    login: int = 0
    password: str = ""
    server: str = ""


class MT5Client:
    """Synchronous, terminal-local MetaTrader 5 connector (offline-capable)."""

    def __init__(self, symbols: Optional[Sequence[str]] = None, magic: int = 20250101) -> None:
        self.symbols_requested: List[str] = list(symbols) if symbols else list(DEFAULT_SYMBOLS)
        self.magic = int(magic)
        self._mt5: Any = None
        self._initialized = False
        self._last_error: str = ""
        self._cfg = _Config()
        self._lock = threading.RLock()
        self._specs: Dict[str, SymbolSpec] = {}

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    @property
    def available(self) -> bool:
        """True when the ``MetaTrader5`` package could be imported."""
        if self._mt5 is None:
            self._mt5 = load_mt5()
        return self._mt5 is not None

    @property
    def connected(self) -> bool:
        """True when attached to a live, logged-in terminal."""
        return bool(self._initialized and self.available)

    @property
    def offline(self) -> bool:
        return not self.connected

    @property
    def last_error(self) -> str:
        return self._last_error

    def initialize(
        self,
        path: str = "",
        login: int = 0,
        password: str = "",
        server: str = "",
        timeout: int = 60_000,
    ) -> bool:
        """Attach to the local terminal. Safe to call repeatedly; returns success.

        ``path`` / ``login`` / ``password`` / ``server`` are optional - a plain
        ``mt5.initialize()`` is enough when the terminal is already open and logged in.
        """
        with self._lock:
            if not self.available:
                self._initialized = False
                self._last_error = "MetaTrader5 package not installed (Windows-only)."
                return False
            kwargs: Dict[str, Any] = {"timeout": timeout}
            if path:
                kwargs["path"] = path
            if login:
                kwargs["login"] = int(login)
            if password:
                kwargs["password"] = password
            if server:
                kwargs["server"] = server
            try:
                ok = bool(self._mt5.initialize(**kwargs))
                if not ok:
                    code, message = self._mt5.last_error()
                    self._last_error = f"initialize failed [{code}] {message}"
                    LOGGER.warning("MT5 initialize failed: %s", self._last_error)
                self._initialized = ok
                self._cfg = _Config(path or "", int(login or 0), password or "", server or "")
                if ok:
                    self._select_symbols()
                return ok
            except Exception as exc:  # noqa: BLE001
                self._initialized = False
                self._last_error = str(exc)
                LOGGER.warning("MT5 initialize raised: %s", exc)
                return False

    def shutdown(self) -> None:
        with self._lock:
            if self._initialized and self.available:
                try:
                    self._mt5.shutdown()
                except Exception:  # noqa: BLE001
                    pass
            self._initialized = False

    def close(self) -> None:
        self.shutdown()

    def _select_symbols(self) -> None:
        """Make sure every requested symbol is available in Market Watch."""
        for symbol in self.symbols_requested:
            resolved = self._resolve_symbol(symbol)
            if resolved:
                try:
                    self._mt5.symbol_select(resolved, True)
                except Exception:  # noqa: BLE001
                    pass

    def _resolve_symbol(self, symbol: str) -> Optional[str]:
        """Map a bare name to the broker's actual symbol (handles suffixes)."""
        if not self.available:
            return None
        try:
            if self._mt5.symbol_info(symbol) is not None:
                return symbol
            for candidate in self._mt5.symbols_get(f"*{symbol}*") or []:
                return candidate.name
        except Exception:  # noqa: BLE001
            return None
        return None

    # ------------------------------------------------------------------ #
    # Account / positions
    # ------------------------------------------------------------------ #
    def account_info(self) -> Dict[str, Any]:
        if not self.connected:
            return {
                "login": 0, "server": "offline-demo", "currency": "USD",
                "balance": 5_000.0, "equity": 5_000.0, "margin": 0.0,
                "margin_free": 5_000.0, "profit": 0.0, "offline": True,
            }
        try:
            info = self._mt5.account_info()
            if info is None:
                code, message = self._mt5.last_error()
                self._last_error = f"account_info failed [{code}] {message}"
                return {"offline": True, "error": self._last_error, "balance": 0.0, "equity": 0.0}
            return {
                "login": int(getattr(info, "login", 0)),
                "server": str(getattr(info, "server", "")),
                "currency": str(getattr(info, "currency", "USD")),
                "balance": float(getattr(info, "balance", 0.0)),
                "equity": float(getattr(info, "equity", 0.0)),
                "margin": float(getattr(info, "margin", 0.0)),
                "margin_free": float(getattr(info, "margin_free", 0.0)),
                "profit": float(getattr(info, "profit", 0.0)),
                "offline": False,
            }
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            LOGGER.warning("account_info raised: %s", exc)
            return {"offline": True, "error": str(exc), "balance": 0.0, "equity": 0.0}

    def positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.connected:
            return []
        try:
            raw = self._mt5.positions_get(symbol=symbol) if symbol else self._mt5.positions_get()
            if not raw:
                return []
            return [
                {
                    "ticket": int(p.ticket), "symbol": str(p.symbol),
                    "type": "BUY" if p.type == 0 else "SELL",
                    "volume": float(p.volume), "price_open": float(p.price_open),
                    "price_current": float(p.price_current), "sl": float(p.sl), "tp": float(p.tp),
                    "profit": float(p.profit), "comment": str(p.comment),
                }
                for p in raw
            ]
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            return []

    def _day_start(self, now: Optional[datetime] = None) -> datetime:
        now = now or datetime.now(timezone.utc)
        return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    @staticmethod
    def _trade_deals(deals: Sequence[Any]) -> List[Any]:
        """Keep only genuine trade deals, dropping deposits/withdrawals and fees.

        ``history_deals_get`` also returns balance operations (funding, credit,
        bonus, corrections) whose ``profit`` equals the deposited amount - those
        must never be mistaken for the day's trading P&L.
        """
        return [d for d in deals if int(getattr(d, "type", -1)) in _TRADE_DEAL_TYPES]

    def daily_pnl(self, now: Optional[datetime] = None) -> float:
        """Net **trade** P&L for the current UTC day: realized + floating (0.0 offline).

        This is a daily *net change*, not the account balance: funding/withdrawal
        deals are filtered out so the guardrail only ever sees trading profit/loss.
        """
        if not self.connected:
            return 0.0
        try:
            start = self._day_start(now)
            end = start + timedelta(days=1)
            deals = self._trade_deals(self._mt5.history_deals_get(start, end) or [])
            realized = sum(
                float(getattr(d, "profit", 0.0)) + float(getattr(d, "swap", 0.0))
                + float(getattr(d, "commission", 0.0))
                for d in deals
            )
            floating = sum(float(p.get("profit", 0.0)) for p in self.positions())
            return round(realized + floating, 2)
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            LOGGER.warning("daily_pnl raised: %s", exc)
            return 0.0

    def trades_today(self, now: Optional[datetime] = None) -> int:
        """Number of *trade* positions opened today (0 when offline).

        Only BUY/SELL entry deals count - balance operations are excluded so a
        funding deal is never counted as a trade against the 3-per-day cap.
        """
        if not self.connected:
            return 0
        try:
            start = self._day_start(now)
            end = start + timedelta(days=1)
            deals = self._trade_deals(self._mt5.history_deals_get(start, end) or [])
            entry_in = getattr(self._mt5, "DEAL_ENTRY_IN", 0)
            return sum(1 for d in deals if int(getattr(d, "entry", -1)) == int(entry_in))
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            return 0

    # ------------------------------------------------------------------ #
    # Market data
    # ------------------------------------------------------------------ #
    def tick(self, symbol: str) -> Dict[str, Any]:
        """Best bid/ask for ``symbol`` (indicative in offline mode)."""
        if not self.connected:
            mid = _simulate_price(symbol)
            half = _simulated_spread(symbol)
            digits = self.spec(symbol).digits
            return {
                "symbol": symbol, "bid": round(mid - half, digits), "ask": round(mid + half, digits),
                "spread": round(2 * half, digits), "time": datetime.now(timezone.utc).isoformat(),
                "offline": True,
            }
        try:
            resolved = self._resolve_symbol(symbol) or symbol
            info = self._mt5.symbol_info_tick(resolved)
            if info is None:
                raise RuntimeError("symbol_info_tick returned None")
            bid, ask = float(info.bid), float(info.ask)
            digits = self.spec(symbol).digits
            return {
                "symbol": symbol, "bid": round(bid, digits), "ask": round(ask, digits),
                "spread": round(ask - bid, digits),
                "time": datetime.fromtimestamp(int(info.time), tz=timezone.utc).isoformat(),
                "offline": False,
            }
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            LOGGER.warning("tick(%s) raised: %s", symbol, exc)
            return {"symbol": symbol, "bid": 0.0, "ask": 0.0, "spread": 0.0,
                    "time": datetime.now(timezone.utc).isoformat(), "offline": True, "error": str(exc)}

    def fetch_frame(self, symbol: str, timeframe: str, count: int = 300) -> pd.DataFrame:
        """OHLCV frame (oldest first) enriched with EMA50/200, RSI14 and ATR14."""
        if self.connected:
            frame = self._fetch_rates(symbol, timeframe, count)
            if frame is not None and not frame.empty:
                frame.attrs["offline"] = False
                return add_indicators(frame)
        offline = _simulate_candles(symbol, timeframe, count)
        offline.attrs["offline"] = True
        return add_indicators(offline)

    def _fetch_rates(self, symbol: str, timeframe: str, count: int) -> Optional[pd.DataFrame]:
        try:
            resolved = self._resolve_symbol(symbol) or symbol
            self._mt5.symbol_select(resolved, True)
            tf_const = getattr(self._mt5, TIMEFRAMES.get(timeframe, "TIMEFRAME_M15"))
            rates = self._mt5.copy_rates_from_pos(resolved, tf_const, 0, int(count))
            if rates is None or len(rates) == 0:
                code, message = self._mt5.last_error()
                self._last_error = f"copy_rates_from_pos failed [{code}] {message}"
                return None
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            if "tick_volume" in df.columns:
                df["volume"] = df["tick_volume"]
            return df[["time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            LOGGER.warning("fetch_frame(%s,%s) raised: %s", symbol, timeframe, exc)
            return None

    # ------------------------------------------------------------------ #
    # Specs
    # ------------------------------------------------------------------ #
    def spec(self, symbol: str) -> SymbolSpec:
        with self._lock:
            cached = self._specs.get(symbol.upper())
        if cached is not None:
            return cached

        spec: Optional[SymbolSpec] = None
        if self.connected:
            try:
                resolved = self._resolve_symbol(symbol) or symbol
                info = self._mt5.symbol_info(resolved)
                if info is not None:
                    tick_size = float(getattr(info, "trade_tick_size", 0.0) or getattr(info, "point", 0.0) or 0.0)
                    spec = SymbolSpec(
                        symbol=symbol,
                        digits=int(getattr(info, "digits", 5) or 5),
                        point=float(getattr(info, "point", 0.0) or (10 ** -int(getattr(info, "digits", 5) or 5))),
                        contract_size=float(getattr(info, "trade_contract_size", 0.0) or 100_000.0),
                        tick_value=float(getattr(info, "trade_tick_value", 0.0) or 0.0),
                        tick_size=tick_size or (10 ** -int(getattr(info, "digits", 5) or 5)),
                        min_lot=float(getattr(info, "volume_min", 0.01) or 0.01),
                        max_lot=float(getattr(info, "volume_max", 100.0) or 100.0),
                        lot_step=float(getattr(info, "volume_step", 0.01) or 0.01),
                    )
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("spec(%s) unavailable: %s", symbol, exc)

        if spec is None:
            spec = self._fallback_spec(symbol)
        with self._lock:
            self._specs[symbol.upper()] = spec
        return spec

    @staticmethod
    def _fallback_spec(symbol: str) -> SymbolSpec:
        data = _FALLBACK_SPECS.get(symbol.upper())
        if data is None:
            digits = 2 if symbol.upper().endswith("JPY") else 5
            data = {"digits": digits, "point": 10 ** -digits, "contract_size": 100_000.0,
                    "tick_value": 1.0, "tick_size": 10 ** -digits}
        return SymbolSpec(symbol=symbol, **data)


# --------------------------------------------------------------------------- #
# Offline simulator (deterministic per symbol)
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
    digits = MT5Client._fallback_spec(symbol).digits
    return max(base * 0.00005, 10 ** -digits)


def _simulate_price(symbol: str) -> float:
    rng = random.Random(_seed(symbol) + int(time.time() // 60))
    drift = math.sin(rng.random() * math.tau) * 0.0008
    return _base_price(symbol) * (1.0 + drift)


def _simulate_candles(symbol: str, timeframe: str, count: int) -> pd.DataFrame:
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


__all__ = [
    "MT5Client",
    "SymbolSpec",
    "load_mt5",
    "add_indicators",
    "DEFAULT_SYMBOLS",
    "TIMEFRAMES",
]
