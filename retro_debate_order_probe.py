"""Debate-order bias probe (trading-workspace research follow-up, 2026-09-04).

Context: the droplet's live decision_outcomes gate (249 decisions, 182
resolved) showed a 40.7% directional accuracy (PF 0.292) and a heavily
bearish rating mix -- 97 Underweight vs only 2 Buy + 18 Overweight, zero
Sell ever issued. Investigation found the research-debate prompts
(bull_researcher.py / bear_researcher.py) are a symmetric mirror in wording,
but graph/setup.py hard-codes the debate to always start "Bull Researcher"
first -- and since should_continue_debate() (conditional_logic.py) just
alternates away from whoever last spoke, Bear always gets the LAST word
before Research Manager synthesizes, regardless of max_debate_rounds. This
is the classic LLM recency/last-speaker bias, structural rather than lexical.

This script re-runs the SAME 15 real (ticker, trade_date) pairs -- the most
recent 15 distinct tickers from news-gap-ml's live `decisions` table on the
droplet, pulled 2026-09-04 -- twice each: once with debate_first_speaker=
"bull" (current production order) and once with "bear" (swapped, Bull gets
the last word instead). Everything else (config, models, historical market
data for the pinned trade_date) is identical between the two runs on a given
ticker, so any shift in the Buy/Overweight vs Underweight/Sell split is
attributable to speaking order, not to which tickers got picked or to
market-data drift.

Uses decide.py's own config/cost-accounting helpers (_build_config,
_compute_cost) rather than run_decision() directly, since run_decision()
doesn't expose a way to override debate_first_speaker per call -- this new
config key (tradingagents/default_config.py) defaults to "bull" everywhere
else (decide.py's HTTP service, the droplet, every other caller), so this
script is the only thing that ever sets it to "bear".

Real, billed LLM calls -- same anthropic provider / deep=claude-sonnet-5 /
quick=claude-haiku-4-5 config as production. Real droplet decisions average
$0.498/call (range $0.38-0.60, n=249, queried 2026-09-04), so this 15-ticker
x 2-order = 30-call batch is expected to cost roughly $12-18 and take
several hours sequentially (each decision took ~9-11 min in the prior
debate-mode retro_batch_20 run).
"""
import json
import os
import sys
from datetime import datetime

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Norton SSL inspection breaks curl_cffi (yfinance's TLS stack) in this local
# environment -- same workaround as run_scanner_retro.py / retro_smoke_postsync.py.
try:
    import curl_cffi.requests as _cffi_req
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    _orig_session_init = _cffi_req.Session.__init__
    def _patched_session_init(self, *args, **kwargs):
        kwargs.setdefault("verify", False)
        _orig_session_init(self, *args, **kwargs)
    _cffi_req.Session.__init__ = _patched_session_init
    print("yfinance: curl_cffi Session patched with verify=False (Norton SSL workaround)")
except Exception as e:
    print(f"yfinance SSL patch failed: {e} -- downloads may fail")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from langchain_core.callbacks import UsageMetadataCallbackHandler  # noqa: E402

from scripts.decide import _build_config, _compute_cost  # noqa: E402
from tradingagents.agents.utils.rating import parse_holding_recommendation  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402

# Most recent 15 distinct tickers from news-gap-ml's live `decisions` table
# on the droplet (queried 2026-09-04), most-recent-trigger-per-ticker,
# commodity/'&'-ticker rows excluded (same exclusions as run_scanner_retro.py
# / news_gap_premarket_sweep.py's own commodity carve-out).
ENTRIES = [
    ("LICI.NS",       "2026-09-01"),
    ("HCLTECH.NS",    "2026-09-01"),
    ("KALYANKJIL.NS", "2026-09-01"),
    ("SBILIFE.NS",    "2026-09-01"),
    ("ITC.NS",        "2026-09-01"),
    ("MARUTI.NS",     "2026-09-01"),
    ("ICICIGI.NS",    "2026-09-01"),
    ("HINDALCO.NS",   "2026-09-01"),
    ("HDFCLIFE.NS",   "2026-09-01"),
    ("JINDALSTEL.NS", "2026-09-01"),
    ("BEL.NS",        "2026-09-01"),
    ("ICICIPRULI.NS", "2026-09-01"),
    ("ASIANPAINT.NS", "2026-09-01"),
    ("BPCL.NS",       "2026-09-01"),
    ("EICHERMOT.NS",  "2026-09-01"),
]

JSONL_FILE = "retro_debate_order_probe_results.jsonl"
MD_FILE = "retro_debate_order_probe_results.md"

md_lines = [
    "# Debate-Order Bias Probe (bull-first vs bear-first, decision_mode=debate)",
    f"\n**Run date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    "\n**Purpose:** confirm whether the fixed Bull-first/Bear-last debate "
    "order in graph/setup.py is itself injecting the bearish rating skew "
    "seen in live droplet decisions (97 Underweight vs 20 Buy+Overweight, "
    "0 Sell, out of 249), independent of prompt wording (already confirmed "
    "symmetric). Each of the 15 real (ticker, trade_date) pairs below is run "
    "twice: debate_first_speaker=bull (current production order, Bear gets "
    "the last word) and debate_first_speaker=bear (swapped, Bull gets the "
    "last word). Same historical market data both times for a given ticker.",
    "\n---\n",
]


def run_one(ticker: str, trade_date: str, debate_first_speaker: str) -> dict:
    config = _build_config(ticker)
    config["debate_first_speaker"] = debate_first_speaker
    usage_handler = UsageMetadataCallbackHandler()
    ta = TradingAgentsGraph(debug=False, config=config, callbacks=[usage_handler])
    final_state, rating = ta.propagate(ticker, trade_date)
    final_decision = final_state["final_trade_decision"]
    holding_recommendation = parse_holding_recommendation(final_decision)
    cost_usd, unpriced_models = _compute_cost(usage_handler.usage_metadata)
    if unpriced_models:
        print(f"  no pricing entry for model(s) {unpriced_models} -- cost_usd is a partial total")
    return {
        "ticker": ticker,
        "trade_date": trade_date,
        "debate_first_speaker": debate_first_speaker,
        "rating": rating,
        "holding_recommendation": holding_recommendation,
        "final_trade_decision": final_decision,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cost_usd": cost_usd,
    }


total_cost = 0.0
with open(JSONL_FILE, "w", encoding="utf-8") as jf:
    for ticker, date in ENTRIES:
        for order in ("bull", "bear"):
            print(f"\n{'='*60}\nRunning: {ticker} @ {date} (first_speaker={order})\n{'='*60}")
            sys.stdout.flush()
            try:
                result = run_one(ticker, date, order)
                total_cost += result["cost_usd"]
                jf.write(json.dumps(result) + "\n")
                jf.flush()
                print(f"DECISION: {result['rating']} / {result['holding_recommendation']} "
                      f"(${result['cost_usd']:.4f})")
                md_lines.append(
                    f"## {ticker} @ {date} -- first_speaker={order}\n"
                    f"**Rating:** {result['rating']}  \n"
                    f"**Holding:** {result['holding_recommendation']}  \n"
                    f"**Cost:** ${result['cost_usd']:.4f}\n\n"
                    f"{result['final_trade_decision']}\n"
                )
            except Exception as e:
                err = f"ERROR: {e}"
                print(err)
                jf.write(json.dumps({
                    "ticker": ticker, "trade_date": date,
                    "debate_first_speaker": order, "error": str(e),
                }) + "\n")
                jf.flush()
                md_lines.append(f"## {ticker} @ {date} -- first_speaker={order}\n**Error:** {e}\n")

            with open(MD_FILE, "w", encoding="utf-8") as mf:
                mf.write("\n".join(md_lines) + f"\n\n---\n**Running total cost:** ${total_cost:.4f}\n")
            print(f"Saved intermediate results to {MD_FILE} (running cost: ${total_cost:.4f})")

print(f"\nAll done. Total cost: ${total_cost:.4f}")
