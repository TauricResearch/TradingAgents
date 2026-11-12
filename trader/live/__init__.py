"""The live account: real money on OKX's production environment (ADR 0010).

So far the package holds the account's API key and the client built from it
(``keys``). It is the only place that builds a client of the production environment,
and the settings, the other accounts, the daily jobs and the dashboard do not import it.
"""
