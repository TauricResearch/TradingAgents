"""The intraday account: a second paper account that decides hourly (ADR 0006).

It shares the ledger, the paper market, the OKX client and the sizing rules of
the daily account, with its own constants (``settings``), its own ledger file and
its own job. The daily account is not touched by anything in this package.
"""
