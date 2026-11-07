"""When a benchmark is a poor stand-in for a ticker's own market, and what to tell the reader."""

from __future__ import annotations

from tradingagents.dataflows.symbols import normalize_symbol


def benchmark_caveat(ticker: str, benchmark: str, config: dict) -> str | None:
    """A sentence to put beside a beta, or None when the benchmark needs no caveat.

    Two cases a reader would otherwise mistake for a local-market beta:
    - a non-US ticker measured against the US default (no regional benchmark is configured);
    - a non-US ticker measured against a USD-listed ETF standing in for the local index, which
      trades on other days and hours, so a daily beta is understated.
    An explicit ``benchmark_ticker`` is the user's own choice and is not second-guessed.
    """
    if config.get("benchmark_ticker"):
        return None
    symbol = normalize_symbol(ticker)
    suffix = symbol.rsplit(".", 1)[1] if "." in symbol else ""
    default = (config.get("benchmark_map") or {}).get("", "SPY")
    if benchmark == default:
        # A one-letter suffix is a share class (BRK.B), not a market.
        if len(suffix) >= 2:
            return (f"no regional benchmark is configured for the .{suffix} market, so beta is measured "
                    f"against {benchmark} and is not a local-market beta; set benchmark_ticker to change it")
        return None
    if suffix and not benchmark.startswith("^") and "." not in benchmark:
        return (f"{benchmark} is a USD-listed ETF standing in for the local index (Yahoo serves no usable "
                "local index history); it trades on different days and hours from the local market, so a "
                "daily beta against it is understated (weekly beta is less affected)")
    return None
