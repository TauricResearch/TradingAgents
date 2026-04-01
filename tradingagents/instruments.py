import re

# Quotes commonly used for crypto trading pairs.
CRYPTO_QUOTES = {
    "USD",
    "USDT",
    "USDC",
    "BUSD",
    "DAI",
    "FDUSD",
    "TUSD",
    "BTC",
    "ETH",
    "BNB",
    "EUR",
    "JPY",
}

# Stablecoin quotes are normalized to USD for Yahoo Finance compatibility.
STABLECOIN_QUOTES = {"USDT", "USDC", "BUSD", "DAI", "FDUSD", "TUSD"}

# Popular crypto symbols used for auto-normalization when a quote is omitted.
MAJOR_CRYPTO_BASES = {
    "BTC",
    "ETH",
    "ONT",
    "SOL",
    "XRP",
    "BNB",
    "DOGE",
    "ADA",
    "TRX",
    "AVAX",
    "DOT",
    "MATIC",
    "LTC",
    "BCH",
    "LINK",
    "ATOM",
    "UNI",
    "AAVE",
    "ETC",
    "XLM",
    "NEAR",
    "FIL",
}

CONCAT_QUOTE_SUFFIXES = tuple(
    sorted(
        CRYPTO_QUOTES,
        key=len,
        reverse=True,
    )
)

EXCHANGE_SUFFIX_PATTERN = re.compile(r"^[A-Z0-9]+(?:\.[A-Z0-9]{1,5})+$")


def _normalize_quote(quote: str) -> str:
    if quote in STABLECOIN_QUOTES:
        return "USD"
    return quote


def normalize_instrument_symbol(symbol: str) -> str:
    """Normalize ticker-like input while preserving equity suffixes and crypto pairs.

    Examples:
    - " cnc.to "   -> "CNC.TO"
    - "btc-usdt"   -> "BTC-USD"
    - "eth/usdt"   -> "ETH-USD"
    - "BTCUSDT"    -> "BTC-USD"
    - "btc"        -> "BTC-USD"
    """
    normalized = symbol.strip().upper().replace(" ", "")
    if not normalized:
        return normalized

    # TradingView-like venue prefixes (e.g. BINANCE:BTCUSDT).
    if ":" in normalized and normalized.count(":") == 1:
        _, normalized = normalized.split(":", 1)

    # Preserve exchange-qualified equity symbols such as 7203.T or CNC.TO.
    if EXCHANGE_SUFFIX_PATTERN.match(normalized):
        return normalized

    # Pair formats: BTC/USDT, BTC_USDT, BTC-USD.
    pair_candidate = normalized.replace("_", "/")
    if pair_candidate.count("/") == 1:
        base, quote = pair_candidate.split("/")
        if base.isalnum() and quote.isalnum():
            return f"{base}-{_normalize_quote(quote)}"

    if normalized.count("-") == 1:
        base, quote = normalized.split("-")
        if base.isalnum() and quote.isalnum():
            return f"{base}-{_normalize_quote(quote)}"

    # Concatenated pair format: BTCUSDT, ETHUSD, SOLBTC.
    for suffix in CONCAT_QUOTE_SUFFIXES:
        if normalized.endswith(suffix) and len(normalized) > len(suffix) + 1:
            base = normalized[: -len(suffix)]
            if base.isalnum():
                return f"{base}-{_normalize_quote(suffix)}"

    # Bare major crypto symbols default to USD quote.
    if normalized in MAJOR_CRYPTO_BASES:
        return f"{normalized}-USD"

    return normalized


def is_crypto_symbol(symbol: str) -> bool:
    """Heuristic crypto detector based on normalized pair semantics."""
    normalized = normalize_instrument_symbol(symbol)
    if not normalized:
        return False

    if normalized.endswith("-USD") and normalized[:-4] in MAJOR_CRYPTO_BASES:
        return True

    if normalized.count("-") == 1 and "." not in normalized:
        base, quote = normalized.split("-")
        if base.isalnum() and quote in CRYPTO_QUOTES:
            return True

    return False


def get_asset_class(symbol: str) -> str:
    """Return 'crypto' for cryptocurrency symbols, otherwise 'equity'."""
    return "crypto" if is_crypto_symbol(symbol) else "equity"
