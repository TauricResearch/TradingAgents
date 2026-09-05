"""Callable entrypoint for a single propagate() decision — the bridge news-gap-ml's
live_listener.py subprocesses into once its OR-gate trigger fires (trading-workspace
issue #18). Runs the full multi-agent graph for one ticker/date and prints exactly
one line of JSON to stdout: the decision, nothing else. All progress/error output
goes to stderr so a subprocess caller can parse stdout unconditionally.

This makes a real, billed call to the configured LLM provider — it is not free and
is not fast (propagate() chains several sequential LLM calls through the analyst/
debate/risk graph). Do not call this in a tight loop.

Ticker must include the exchange suffix TradingAgents expects (see README.md,
e.g. "RELIANCE.NS" for NSE India, "WIPRO.NS", plain "NVDA" for US) — this script
does not guess or normalize tickers.

--context (trading-workspace#37, optional) carries a JSON blob of a prior
technical signal from an external scanner (news-gap-ml's leg-3 trigger, which
*is* options-signal-bot's own stock_decisions/decision_features row) — passed
through to the market analyst as context to reason about, not ground truth to
trust blindly. Only news-gap-ml's technical-trigger leg has anything to hand
over here; news/global-shock triggers have no equivalent prior signal, so they
call this script without --context, same as before.

Usage:
    python scripts/decide.py --ticker WIPRO.NS --date 2026-07-15
    python scripts/decide.py --ticker NVDA --date 2026-07-15 --asset-type stock
    python scripts/decide.py --ticker WIPRO.NS --date 2026-07-15 --context '{"side": "long", "score": 78.5, ...}'
    python scripts/decide.py --ticker CRUDEOILM --date 2026-07-15 --asset-type commodity
        (trading-workspace#68 -- broker/MCX-style commodity names like
        CRUDEOILM/GOLDM resolve to their global USD benchmark future, e.g.
        CL=F/GC=F, via symbol_utils.py's alias table, same as XAUUSD/USOIL
        already do for stock/crypto)

Output (stdout, single line):
    {"ticker": "WIPRO.NS", "trade_date": "2026-07-15", "rating": "Buy",
     "holding_recommendation": "Square Off Intraday",
     "final_trade_decision": "...", "generated_at": "2026-07-15T09:03:11+00:00",
     "cost_usd": 0.50, "token_usage": {"claude-sonnet-4-6": {"input_tokens": 8000, ...}}}
    (TFR-215: cost_usd example updated to match the real observed average
    ~$0.50/decision, not the original $0.0412 placeholder -- that number was
    12x too low and was a real budgeting trap for anyone sizing MAX_TRIGGERS_
    PER_POLL/day-cost ceilings off this docstring. See news-gap-ml's
    live_listener.py (trading-workspace#86) for the measured figure.)

On failure: non-zero exit code, error detail on stderr, nothing on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from langchain_core.callbacks import UsageMetadataCallbackHandler

from tradingagents.agents.utils.rating import parse_holding_recommendation
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

# Indian tickers get much better news coverage from the indian_news vendor than
# the yfinance-only default (see default_config.py's data_vendors comment) —
# applied automatically so callers don't need to know this vendor detail.
_INDIAN_SUFFIXES = (".NS", ".BO")

# $ per 1M tokens (input, output) — trading-workspace issue #24. Keyed by the
# model_name langchain reports in AIMessage.response_metadata, which can carry
# a dated suffix (e.g. "claude-haiku-4-5-20251001") — _price_for() matches by
# longest-prefix so both bare and dated IDs resolve. Update when the .env
# TRADINGAGENTS_DEEP_THINK_LLM/QUICK_THINK_LLM models or their pricing change.
_PRICING_PER_MTOK = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
}


def _price_for(model_name: str) -> tuple:
    """Longest-prefix match against _PRICING_PER_MTOK, or None if unknown."""
    match = max(
        (key for key in _PRICING_PER_MTOK if model_name.startswith(key)),
        key=len, default=None,
    )
    return _PRICING_PER_MTOK[match] if match else None


def _compute_cost(usage_metadata: dict) -> tuple[float, list]:
    """Returns (total_usd, [model names with no pricing entry])."""
    total = 0.0
    unpriced = []
    for model_name, usage in usage_metadata.items():
        price = _price_for(model_name)
        if price is None:
            unpriced.append(model_name)
            continue
        price_in, price_out = price
        total += usage.get("input_tokens", 0) / 1_000_000 * price_in
        total += usage.get("output_tokens", 0) / 1_000_000 * price_out
    return round(total, 4), unpriced


def _build_config(ticker: str) -> dict:
    config = DEFAULT_CONFIG.copy()
    if ticker.upper().endswith(_INDIAN_SUFFIXES):
        config["data_vendors"] = {
            **config["data_vendors"],
            "news_data": "indian_news,yfinance",
        }
    return config


# Ordered (field, label) pairs surfaced from a --context payload, if present.
# Field names match options-signal-bot's stock_decisions/decision_features
# columns (trading-workspace#37) — not every field is always populated
# (decision_features has no historical backfill), so missing ones are skipped.
_CONTEXT_DETAIL_FIELDS = (
    ("structure", "structure"), ("rsi14", "RSI14"), ("ema20", "EMA20"), ("ema50", "EMA50"),
    ("atr14", "ATR14"), ("pullback_atr", "pullback (ATR)"),
    ("entry_price", "entry"), ("stop_price", "stop"), ("target_price", "target"),
)


def _format_external_signal_context(raw_json: str) -> str:
    """Turn a --context JSON blob into a natural-language passage for the
    market analyst's prompt. Framed so the analyst reasons *about* the
    scanner's finding rather than re-deriving it from scratch (the point of
    #37) while still forming its own independent view (not "trust it
    blindly" — the whole reason this graph has a debate/risk structure)."""
    try:
        signal = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError) as exc:
        print(f"decide.py: --context was not valid JSON ({exc}), ignoring: {raw_json[:200]!r}", file=sys.stderr)
        return ""

    parts = [
        f"A separate technical scanner already flagged this stock today "
        f"({signal.get('side', 'unknown')} {signal.get('action', 'signal')}, "
        f"score {signal.get('score', '?')}/100)."
    ]
    details = [f"{label}={signal[key]}" for key, label in _CONTEXT_DETAIL_FIELDS if signal.get(key) is not None]
    if details:
        parts.append("Scanner detail: " + ", ".join(details) + ".")
    parts.append(
        "Treat this as one input to weigh alongside your own independent analysis, "
        "not as ground truth — verify or challenge it with your own tools rather than assuming it holds."
    )
    return " ".join(parts)


def run_decision(ticker: str, trade_date: str, asset_type: str = "stock", context: str | None = None) -> dict:
    """Run one propagate() decision and return the result dict (hermes#213).

    Extracted from main() so both the CLI below and scripts/service.py's
    HTTP endpoint share one implementation of the actual decision-making
    call -- only the transport (argv/stdout vs. HTTP request/response)
    differs between callers.

    Raises on failure; callers decide how to report it (the CLI prints to
    stderr and exits 1, the HTTP service returns a 500 with the exception
    detail).
    """
    external_signal_context = _format_external_signal_context(context) if context else ""

    usage_handler = UsageMetadataCallbackHandler()
    config = _build_config(ticker)
    ta = TradingAgentsGraph(debug=False, config=config, callbacks=[usage_handler])
    final_state, rating = ta.propagate(
        ticker, trade_date, asset_type=asset_type,
        external_signal_context=external_signal_context,
    )
    final_decision = final_state["final_trade_decision"]
    holding_recommendation = parse_holding_recommendation(final_decision)

    cost_usd, unpriced_models = _compute_cost(usage_handler.usage_metadata)
    if unpriced_models:
        print(f"decide.py: no pricing entry for model(s) {unpriced_models} — cost_usd is a partial total", file=sys.stderr)

    # debate_first_speaker defaults to "random" (default_config.py) and is
    # resolved once per decision at GraphSetup construction time -- surfaced
    # here (not just internal state) so cron.log/the returned dict can be
    # audited later against decision_outcomes for the last-speaker bias
    # trading-workspace#26 found, without needing a DB schema change.
    debate_first_speaker_used = ta.debate_first_speaker
    print(f"decide.py: debate_first_speaker={debate_first_speaker_used} for {ticker}@{trade_date}")

    return {
        "ticker": ticker,
        "trade_date": trade_date,
        "asset_type": asset_type,
        "rating": rating,
        "holding_recommendation": holding_recommendation,
        "final_trade_decision": final_decision,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cost_usd": cost_usd,
        "token_usage": usage_handler.usage_metadata,
        "debate_first_speaker": debate_first_speaker_used,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticker", required=True, help='e.g. "WIPRO.NS", "RELIANCE.NS", "NVDA"')
    parser.add_argument("--date", required=True, dest="trade_date", help="YYYY-MM-DD")
    parser.add_argument("--asset-type", default="stock", choices=["stock", "crypto", "commodity"])
    parser.add_argument("--context", default=None, help="JSON blob of a prior technical signal (trading-workspace#37)")
    args = parser.parse_args()

    try:
        result = run_decision(args.ticker, args.trade_date, args.asset_type, args.context)
    except Exception as exc:  # noqa: BLE001 — report cleanly on stderr, never on stdout
        print(f"decide.py failed for {args.ticker} on {args.trade_date}: {exc}", file=sys.stderr)
        return 1

    print(f"decide.py: ${result['cost_usd']:.4f} for this call ({result['token_usage']})", file=sys.stderr)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
