import sys
import os
import truststore
truststore.inject_into_ssl()  # patches ssl.create_default_context → used by httpx (LLM calls)

from datetime import datetime

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# yfinance 1.4.1 uses curl_cffi (its own libcurl TLS stack), not Python ssl.
# Norton SSL inspection CA is not in libcurl's bundle → patch Session.__init__
# so every session curl_cffi creates has verify=False baked in.
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
    print(f"yfinance SSL patch failed: {e} — downloads may fail")

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ENTRIES = [
    ("NMDC.NS",       "2026-06-12"),
    ("HINDUNILVR.NS", "2026-06-12"),
    # M&M.NS skipped — TradingAgents path-safety regex blocks '&' character
    ("COFORGE.NS",    "2026-06-12"),
]

RESULTS_FILE = "scanner_retro_results.md"

config = DEFAULT_CONFIG.copy()
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1

results = []
results.append(f"# Scanner Retroactive TradingAgents Run\n")
results.append(f"**Run date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
results.append(f"**Entry date analysed:** 2026-06-12 (scanner picks)\n")
results.append(f"**Note:** M&M.NS skipped — TradingAgents path-safety regex blocks '&' character\n\n---\n")

for ticker, date in ENTRIES:
    print(f"\n{'='*60}")
    print(f"Running: {ticker} @ {date}")
    print(f"{'='*60}")
    sys.stdout.flush()

    try:
        ta = TradingAgentsGraph(debug=False, config=config)
        _, decision = ta.propagate(ticker, date)
        print(f"DECISION: {decision}")
        results.append(f"\n## {ticker}\n**Decision:** {decision}\n")
    except Exception as e:
        err = f"ERROR: {e}"
        print(err)
        results.append(f"\n## {ticker}\n**Error:** {e}\n")

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(results))
    print(f"Saved intermediate results to {RESULTS_FILE}")

print("\nAll done.")
