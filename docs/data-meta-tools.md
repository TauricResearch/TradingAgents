# Analyst data meta-tools

The market, fundamentals, and news analysts each have one bounded data-bundle
tool in addition to the precise individual tools:

| Analyst | Meta-tool | Default capabilities |
| --- | --- | --- |
| Market | `get_market_research_bundle` | verified market snapshot and price history |
| Fundamentals | `get_fundamentals_research_bundle` | company fundamentals and the three quarterly statements |
| News | `get_news_research_bundle` | company news |

Each accepts `symbol`, `curr_date`, and a natural-language `request`. The
request is matched only against the reviewed catalogue in
`tradingagents/agents/utils/data_meta_tools.py`; it is never imported or
executed as code, and it cannot select a vendor. Explicit keywords can add a
small relevant supplement (for example RSI, A-share capital flow, macro CPI),
but A-share-only capabilities are unavailable for non-A-share symbols.

The bundle runs no more than four capabilities and no more than three at once.
It returns stable-order JSON with a route-method/capability provenance record.
Provider exception text is intentionally not forwarded: failures use the public
types `source_unavailable`, `invalid_request`, or `source_failed`. A partial
bundle is `degraded`, rather than a reason for the analyst pipeline to invent
missing data or halt.

Use the individual tools when one exact query or a non-default parameter is
required. Use a meta-tool when independent views are needed together.
