"""Ticker anonymization for debate prompts."""


def anonymize_ticker(text: str, ticker: str, alias: str = "TICKER_A") -> str:
    """Replace all occurrences of *ticker* (case-insensitive) with *alias*.

    Also handles common variants: lowercase, with/without dots (e.g. BRK.B).
    """
    if not ticker or not text:
        return text
    import re

    # Escape for regex (handles dots in tickers like BRK.B)
    pattern = re.compile(re.escape(ticker), re.IGNORECASE)
    return pattern.sub(alias, text)
