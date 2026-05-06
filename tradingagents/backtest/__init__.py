"""Backtest harness for the Kalshi prediction-market pipeline.

**Phase 5 ships scaffolding only — no automated sweep runs here.**

Why: a single contract run already costs ~10-20 LLM calls; replaying
the pipeline against 30+ historical BTC daily contracts means hundreds
of calls per parameter combination. Firing that off should be an
intentional decision (with budget allocated) rather than a side-effect
of running tests.

This package gives you the pieces to:

1. ``data_collector`` — collect historical contract metadata + outcomes,
   Coinbase candles for the same window, news/sentiment snapshots.
2. ``replay`` — replay a single historical contract through
   ``run_contract`` with a frozen-time view of the data layer, so the
   agent committee sees what it would have seen at decision time.
3. ``metrics`` — hit rate, edge calibration (does the committee's
   ``p_yes`` match realized win rate at each probability bin?),
   Sharpe-ish growth-rate metric, drawdown.
4. ``sweep`` — light grid-search runner around the parameters most
   likely to matter (Kelly multiplier, debate rounds, model tier).

To actually run a sweep:

    from tradingagents.backtest.sweep import run_sweep
    run_sweep(contracts=[...], grid={"kelly_mult": [0.1, 0.25, 0.5]})

That call exercises real LLM endpoints, so don't do it without
budget allocated. The harness is wired so you can iterate on the
analyst prompts and re-run the sweep cheaply once a baseline is
captured (see ``replay.py`` for the cache strategy).
"""
