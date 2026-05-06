"""Kalshi execution layer.

Modules:
    safety         — paper-mode flag + ``TRADINGAGENTS_LIVE_DISABLED`` kill switch
    kalshi_client  — signed POST/DELETE/GET against Kalshi's portfolio API
    order_ledger   — SQLite lifecycle tracking (submit -> fill -> settle)
    sizing         — Kelly stake from MarketDecision + risk-debate-adjusted
                     stake fraction
    runner         — paper/live execution wrapper that reads a MarketDecision
                     and (in live mode) places the corresponding order
"""
