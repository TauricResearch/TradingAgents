from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from backend.integrations.india import INDICES, catalog_name, normalize_india_symbol
from backend.schemas import Candle, StockQuote


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    def quote(self, symbol: str) -> StockQuote:
        raise NotImplementedError

    @abstractmethod
    def history(self, symbol: str, range_key: str) -> list[Candle]:
        raise NotImplementedError

    @abstractmethod
    def index_quotes(self) -> list[StockQuote]:
        raise NotImplementedError


class YahooFinanceProvider(MarketDataProvider):
    name = "yahoo"

    def quote(self, symbol: str) -> StockQuote:
        import yfinance as yf

        from tradingagents.dataflows.symbol_utils import normalize_symbol

        canonical, exchange = normalize_india_symbol(symbol)
        yahoo = normalize_symbol(canonical)
        ticker = yf.Ticker(yahoo)
        info = ticker.fast_info if hasattr(ticker, "fast_info") else {}
        hist = ticker.history(period="5d")
        price = _safe_float(getattr(info, "last_price", None) if info is not None else None)
        prev = _safe_float(getattr(info, "previous_close", None) if info is not None else None)
        if (price is None or prev is None) and hist is not None and not hist.empty:
            price = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
        change = (price - prev) if price is not None and prev is not None else None
        pct = (change / prev * 100) if change is not None and prev else None
        return StockQuote(
            symbol=canonical,
            name=catalog_name(canonical) or str(getattr(info, "short_name", canonical) or canonical),
            exchange=exchange,
            currency=str(getattr(info, "currency", "INR") or "INR"),
            price=price,
            change=change,
            change_percent=pct,
            previous_close=prev,
            open=_safe_float(getattr(info, "open", None) if info is not None else None),
            high=_safe_float(getattr(info, "day_high", None) if info is not None else None),
            low=_safe_float(getattr(info, "day_low", None) if info is not None else None),
            volume=_safe_float(getattr(info, "last_volume", None) if info is not None else None),
            market_cap=_safe_float(getattr(info, "market_cap", None) if info is not None else None),
        )

    def history(self, symbol: str, range_key: str) -> list[Candle]:
        import yfinance as yf

        from tradingagents.dataflows.symbol_utils import normalize_symbol

        canonical, _ = normalize_india_symbol(symbol)
        period, interval = _range_to_yf(range_key)
        data = yf.Ticker(normalize_symbol(canonical)).history(period=period, interval=interval)
        candles: list[Candle] = []
        if data is None or data.empty:
            return candles
        for idx, row in data.iterrows():
            candles.append(
                Candle(
                    time=idx.isoformat(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row.get("Volume") or 0),
                )
            )
        return candles

    def index_quotes(self) -> list[StockQuote]:
        quotes = []
        for item in INDICES:
            try:
                q = self.quote(item["yahoo"])
                q.name = item["label"]
                q.symbol = item["symbol"]
                q.exchange = "INDEX"
                quotes.append(q)
            except Exception:
                quotes.append(
                    StockQuote(
                        symbol=item["symbol"],
                        name=item["label"],
                        exchange="INDEX",
                        price=None,
                    )
                )
        return quotes


class NSEProvider(MarketDataProvider):
    """Placeholder for a future official NSE feed. Falls back to Yahoo."""

    name = "nse"

    def __init__(self) -> None:
        self._yahoo = YahooFinanceProvider()

    def quote(self, symbol: str) -> StockQuote:
        return self._yahoo.quote(symbol)

    def history(self, symbol: str, range_key: str) -> list[Candle]:
        return self._yahoo.history(symbol, range_key)

    def index_quotes(self) -> list[StockQuote]:
        return self._yahoo.index_quotes()


def get_market_provider(name: str | None = None) -> MarketDataProvider:
    key = (name or "yahoo").lower()
    if key in {"nse", "broker", "custom"}:
        return NSEProvider()
    return YahooFinanceProvider()


def _safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _range_to_yf(range_key: str) -> tuple[str, str]:
    mapping = {
        "1D": ("1d", "5m"),
        "5D": ("5d", "15m"),
        "1M": ("1mo", "1d"),
        "3M": ("3mo", "1d"),
        "6M": ("6mo", "1d"),
        "1Y": ("1y", "1d"),
        "5Y": ("5y", "1wk"),
    }
    return mapping.get(range_key.upper(), ("6mo", "1d"))


def classify_regime(index_quotes: list[StockQuote]) -> str | None:
    nifty = next((q for q in index_quotes if q.symbol in {"^NSEI", "NIFTY 50"}), None)
    if nifty is None or nifty.change_percent is None:
        return None
    if nifty.change_percent >= 0.6:
        return "Bullish"
    if nifty.change_percent <= -0.6:
        return "Bearish"
    return "Neutral"
