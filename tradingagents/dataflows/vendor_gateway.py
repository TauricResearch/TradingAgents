"""Single data-layer gateway for yfinance access from the Koral paper desk.

Vendor libraries are imported exclusively in dataflows. This wrapper does
not validate vendor provenance; callers must continue to validate every bar
and declare the data vendor in output.
"""


def get_yahoo_ticker(symbol: str):
    import yfinance as yf

    return yf.Ticker(symbol)


def download_yahoo_bars(*args, **kwargs):
    import yfinance as yf

    return yf.download(*args, **kwargs)
