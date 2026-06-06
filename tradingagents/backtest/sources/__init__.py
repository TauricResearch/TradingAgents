"""F2 PriceSource adapters.

F2 ships only yfinance; polygon/alpha_vantage/futu are registered as stubs
so the fallback chain is wired from day one. Users (or F3) replace the
stubs with real implementations as needed.
"""
