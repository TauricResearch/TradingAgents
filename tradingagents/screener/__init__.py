"""Stock screener over the India database: filter every stock on its metrics.

    catalog   every metric a screen can use: names, aliases, units, descriptions,
              and the function computing each from ``company``'s inputs
    company   one security's inputs, read point in time from the India database
    snapshot  the precomputed ``metrics_snapshot`` table, live and as of past dates
    query     the query language: tokenizer, recursive-descent parser, AST
    compiler  AST to SQL: catalog identifiers only, every literal a bound parameter
    engine    validate and run a screen over a snapshot
    screens   saved screens, custom ratios and the presets
    peers     a company's peers and an industry's stocks, as screens of its industry
    watchlists  named lists of stocks, with notes and optional holdings
    alerts    price, metric, screen, filing and shareholding alerts, and their inbox
    delivery  alert channels beyond the inbox: Telegram, a webhook, email
    export    CSV and Excel exports; ``xlsx`` writes the workbooks
    userdb    the user's own database: screens, ratios, watchlists, alerts

Every formula is ``dataflows.formulas``, the module the Company page uses too,
so a metric reads the same in a screen and on the Company page. Nothing here
imports the live Company page: snapshots are point in time, so a backtest of a
screen can read them later.
"""
