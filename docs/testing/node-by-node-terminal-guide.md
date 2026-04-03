# Node-by-Node Terminal Testing Guide

## Purpose

This guide defines a repeatable terminal workflow to:

1. implement a fix for a specific graph node
2. run that node path live
3. monitor in-flight events
4. validate artifacts for hallucination/provenance behavior
5. move to the next node

Use this for structured-contract migration and hallucination hardening work.

This guide now covers two complementary validation paths:

1. API-backed live runs through `run_node_live.py`
2. direct graph probes when you need to inspect actual prompt/context wiring and the API wrapper is too noisy

## Prerequisites

- Repo root: `/Users/Ahmet/Repo/TradingAgents`
- Backend API running (default in this repo): `http://localhost:8088`
- Python environment available via `uv`
- A known baseline artifact set for injection tests, for example:
  `reports/daily/2026-04-02/01KN86XN2BHGRTME4GHYQF21R5/market/macro_scan_summary.md`

## Direct one-command runner

Use the helper script when you want to run this flow directly:

```bash
cd /Users/Ahmet/Repo/TradingAgents
./scripts/run_node_live.py --help
```

Example: trigger + monitor a news-only run with injected market report:

```bash
./scripts/run_node_live.py \
  --trigger \
  --ticker AAPL \
  --date 2026-04-02 \
  --analysts news \
  --market-report-file reports/daily/2026-04-02/01KN86XN2BHGRTME4GHYQF21R5/market/macro_scan_summary.md \
  --show-system \
  --timeout-seconds 600 \
  --stop-on-timeout \
  --validate-news-prompt \
  --write-run-json /tmp/aapl-news-run.json
```

Example: monitor an existing run:

```bash
./scripts/run_node_live.py \
  --run-id 01KN9TK6NYDGKHTJKCZMBN9EGE \
  --show-system \
  --watch-nodes "News Analyst,News Fact Checker"
```

Example: trigger + validate a market-only rollout step (live ticker):

```bash
./scripts/run_node_live.py \
  --trigger \
  --ticker AAPL \
  --date 2026-03-31 \
  --analysts market \
  --show-system \
  --watch-nodes "Market Analyst,__system__" \
  --heartbeat-seconds 20 \
  --timeout-seconds 900 \
  --stop-on-timeout \
  --stall-seconds 180 \
  --validate-market-checkpoint \
  --market-require-structured \
  --market-required-fields "status,contract_version,macro_regime" \
  --validate-downstream-entry \
  --downstream-after-node "Market Analyst" \
  --downstream-entry-nodes "Bull Researcher" \
  --write-run-json /tmp/aapl-market-run.json
```

Summary-bypass validation command (analysts -> Bull Researcher, no summary node):

```bash
./scripts/run_node_live.py \
  --trigger \
  --ticker AAPL \
  --date 2026-03-31 \
  --analysts market,news,fundamentals \
  --show-system \
  --watch-nodes "Market Analyst,News Analyst,Fundamentals Analyst,Research Packet Summary,Bull Researcher,__system__" \
  --heartbeat-seconds 20 \
  --stall-seconds 180 \
  --stop-on-stall \
  --timeout-seconds 1200 \
  --validate-bypass-summary-flow \
  --required-analyst-nodes "Market Analyst,News Analyst,Fundamentals Analyst" \
  --forbidden-nodes-before-bull "Research Packet Summary" \
  --validate-analyst-contracts \
  --required-contract-fields "market_report_structured,news_report_structured,fundamentals_report_structured" \
  --write-run-json /tmp/aapl-bypass-summary-run.json
```

Example: direct live-context probe for a single node path with injected market context:

```bash
uv run python - <<'PY'
from pathlib import Path
from unittest.mock import MagicMock

from agent_os.backend.services.langgraph_engine import LangGraphEngine
from tradingagents.agents.utils.output_validation import build_market_report_structured
from tradingagents.agents.utils.summary_context import build_research_packet

macro_path = Path("reports/daily/2026-04-02/01KN86XN2BHGRTME4GHYQF21R5/market/macro_scan_summary.md")
engine = LangGraphEngine()
scanner_context = engine._build_scanner_context_packet(
    {"macro_scan_summary": macro_path.read_text(encoding="utf-8")},
    "JPM",
)
injected_market = engine._load_injected_market_report(str(macro_path))
market_structured = build_market_report_structured(
    ticker="JPM",
    as_of_date="2026-04-02",
    market_report=injected_market["market_report"],
    macro_regime_report=injected_market["macro_regime_report"],
)

state = {
    "company_of_interest": "JPM",
    "scanner_context_packet": scanner_context,
    "market_report": injected_market["market_report"],
    "market_report_structured": market_structured,
    "news_report": "",
    "sentiment_report": "",
    "fundamentals_report": "",
    "macro_regime_report": injected_market["macro_regime_report"],
}

packet = build_research_packet(state)
print("has_scanner_context", "## Scanner Context (Phase 1)" in packet)
print("has_market_contract", "## Market Structured Contract" in packet)
print(packet[:1600])
PY
```

## 0) Start backend

```bash
cd /Users/Ahmet/Repo/TradingAgents
uv run python -m agent_os.backend.main
```

In a separate terminal:

```bash
python - <<'PY'
import requests
r = requests.get("http://localhost:8088/", timeout=5)
print(r.status_code, r.text[:200])
PY
```

Expected: HTTP `200` with `{"status":"ok"...}`.

## 1) Trigger a node-scoped live run

### Important payload rule

`POST /api/run/pipeline` expects run params as the **top-level JSON body**.
Do not wrap under `{"params": ...}`.

### Example: news-only live run with injected market report

```bash
python - <<'PY'
import requests
payload = {
  "ticker": "AAPL",
  "date": "2026-04-02",
  "portfolio_id": "main_portfolio",
  "selected_analysts": ["news"],
  "market_report_file": "reports/daily/2026-04-02/01KN86XN2BHGRTME4GHYQF21R5/market/macro_scan_summary.md"
}
r = requests.post("http://localhost:8088/api/run/pipeline", json=payload, timeout=30)
print(r.status_code, r.text)
PY
```

Save the returned `run_id`.

## 2) Monitor run events in real time

```bash
python -u - <<'PY'
import requests, time
run_id = "REPLACE_RUN_ID"
base = "http://localhost:8088/api/run"
seen = 0
last_status = None
for _ in range(240):
    d = requests.get(f"{base}/{run_id}", timeout=30).json()
    status = d.get("status")
    events = d.get("events", [])
    if status != last_status:
        print("status", status, "events", len(events), flush=True)
        last_status = status
    for e in events[seen:]:
        nid = e.get("node_id", "")
        et = e.get("type", "")
        if nid in {"News Analyst", "News Fact Checker", "__system__"}:
            msg = (e.get("message") or e.get("response") or "")
            print("---", nid, et, flush=True)
            if msg:
                print(msg[:300].replace("\n", "\\n"), flush=True)
    seen = len(events)
    if status in {"completed", "failed"}:
        print("final", status, "error", d.get("error"), flush=True)
        break
    time.sleep(2)
PY
```

## 3) Stop a stuck run quickly

```bash
python - <<'PY'
import requests
run_id = "REPLACE_RUN_ID"
r = requests.post(f"http://localhost:8088/api/run/{run_id}/stop", timeout=30)
print(r.status_code, r.text)
PY
```

Use this when an external model call stalls and you still want artifact-level validation.

## 4) Validate persisted run artifacts

Run directory:

`reports/daily/<DATE>/<RUN_ID>/`

For event-level inspection:

```bash
python - <<'PY'
import json
p = "reports/daily/2026-04-02/REPLACE_RUN_ID/run_events.jsonl"
with open(p) as f:
    events = [json.loads(x) for x in f]
print("events", len(events))
for i, e in enumerate(events):
    if e.get("node_id") == "News Analyst" and e.get("type") == "thought":
        prompt = str(e.get("prompt") or "")
        print("prompt_len", len(prompt))
        print("has_old_block", "CRITICAL OUTPUT REQUIREMENTS" in prompt)
        print("has_sparse_guidance", "If the evidence window is sparse" in prompt)
        break
PY
```

For market rollout validation (checkpoint-level):

```bash
python - <<'PY'
import glob, json
run_id = "REPLACE_RUN_ID"
date = "2026-03-31"
ticker = "AAPL"
paths = sorted(glob.glob(f"reports/daily/{date}/{run_id}/{ticker}/report/*analysts_checkpoint.json"))
assert paths, "No analysts checkpoint found"
payload = json.loads(open(paths[-1]).read())
print("macro_fallback_detected", (payload.get("macro_regime_report") or "").strip() == (payload.get("market_report") or "").strip())
structured = payload.get("market_report_structured")
print("has_market_report_structured", isinstance(structured, dict) or (isinstance(structured, str) and structured.strip().startswith("{")))
PY
```

For stalled runs, inspect the last few events quickly:

```bash
python - <<'PY'
import json
p = "reports/daily/2026-03-31/REPLACE_RUN_ID/run_events.jsonl"
events = [json.loads(x) for x in open(p)]
print("event_count", len(events))
for e in events[-6:]:
    msg = (e.get("message") or e.get("response") or "").replace("\n", " ")
    print(e.get("node_id"), e.get("type"), msg[:180])
PY
```

## 5) Node-level deterministic test (without full graph)

Use direct node invocation to validate contract behavior even if live model calls are flaky.

Example: `News Fact Checker` non-abort behavior.

```bash
python - <<'PY'
from tradingagents.agents.managers.news_fact_checker import create_news_fact_checker
from tradingagents.memory.news_evidence import NewsEvidenceStore
import tempfile

with tempfile.TemporaryDirectory() as d:
    store = NewsEvidenceStore(db_path=f"{d}/news_evidence.sqlite3")
    node = create_news_fact_checker(store)

    out = node({
        "run_id": "node-test",
        "company_of_interest": "AAPL",
        "trade_date": "2026-04-02",
        "news_report": "AAPL News Analysis\\n\\n- placeholder"
    })
    print(out["sender"])
    print(out["news_report"])
PY
```

## 6) Direct prompt/context validation

Use this when you need to answer questions like:

- is the scanner context actually attached to the analyst prompt?
- is the context filtered to the target ticker?
- did the structured payload survive into the next node?
- is the downstream researcher using the deterministic packet instead of legacy summary prose?

Recommended workflow:

1. build or inject a known market/scanner artifact set
2. render the node prompt directly with a fake/mocked model
3. inspect prompt text for:
   - target ticker present
   - scanner context present
   - unwanted peer ticker leakage absent
   - contract sections present
4. run the immediate downstream node on the produced state
5. inspect structured payloads and the deterministic packet builder

What to check on the current structured-contract path:

1. `News Analyst`
   - prompt contains `## Scanner Context`
   - prompt contains target ticker
   - prompt contains allowed source hint such as `Finviz Smart Money Scanner`
   - prompt does not over-carry peer ticker context when filtered
2. `News Fact Checker`
   - `news_report_structured` exists
   - unsupported or hallucinated claims are removed without aborting the run
3. `Bull Researcher` and downstream debate/risk nodes
   - prompt contains `## Scanner Context (Phase 1)`
   - prompt contains `## Market Structured Contract`
   - prompt does not depend on legacy `research_packet_summary` text

## 6) Node-by-node execution loop

For each node in top-down order:

1. apply code change for that node contract
2. run node/unit tests
3. run live scoped pipeline for that node path
4. monitor events until complete/fail/timeout
5. inspect persisted artifacts
6. record pass/fail notes before moving to next node

Market-node gate to downstream gate sequence:

1. run market live gate with strict checkpoint checks and save run json
2. confirm `market_report_structured` contains required fields
3. confirm no macro fallback (`macro_regime_report` is not full `market_report`)
4. confirm downstream entry occurred after market (`Bull Researcher`)
5. only then move to downstream node-specific fixes

Recommended order for structured contracts:

1. analyst node (`market` / `news` / `fundamentals` / `social`)
2. immediate validator/fact-checker node
3. context packet builder node
4. manager/debate node
5. portfolio/risk synthesis node

## 7) Quick troubleshooting

- Symptom: wrong nodes run (for example `Market Analyst` appears in a news-only run)
  - Check request shape. Use top-level JSON body and set `selected_analysts` correctly.
- Symptom: no new events after first `thought`
  - External model stall. stop run, inspect artifacts, validate node deterministically.
- Symptom: rerun starts from broader phase than expected
  - `POST /api/run/rerun-node` is phase-based; for strict node scoping prefer a fresh `pipeline` run with narrowed analysts.

## 8) Minimum evidence to mark a node fix as validated

Require all:

1. relevant unit tests pass
2. one live scoped run attempted and monitored
3. persisted artifacts confirm prompt/contract change is present
4. deterministic node-level invocation confirms expected failure/success shape

For market-node completion specifically, include:

1. analysts checkpoint file exists under `reports/daily/<date>/<run_id>/<ticker>/report/*analysts_checkpoint.json`
2. `market_report_structured` exists and has `status`, `contract_version`, `macro_regime`
3. `macro_regime_report` is not equal to full `market_report`
4. a downstream entry node appears after `Market Analyst` in run events

When `Research Packet Summary` is bypassed, artifact expectations change:

1. `run_events.jsonl` should not contain `node_id="Research Packet Summary"` before `Bull Researcher`.
2. `Bull Researcher` should appear after analyst nodes directly (same ticker flow).
3. Analysts checkpoint remains the key contract artifact (`*analysts_checkpoint.json`) and should contain required structured fields.
4. Any summary-specific prompt/result traces for the summarizer node should disappear from run events for the bypassed path.

## Current Status

Done:

1. `Research Packet Summary` is removed from the canonical analyst-to-researcher path.
2. `build_research_packet()` now assembles the deterministic packet directly from scanner context and analyst outputs.
3. Runner validations exist for summary bypass, contract presence, market checkpoint validation, and stall detection.
4. Direct graph validation has confirmed the news path reaches `Bull Researcher` without hitting `Research Packet Summary`.

Left:

1. finish node-by-node downstream hardening until a full API-backed run completes cleanly end to end
2. fix the backend run/event wrapper behavior that can hide node progress during live runs
3. harden scanner-context enrichment so packet fields do not degrade to `N/A` when one vendor path fails
4. perform final cleanup refactor of [langgraph_engine.py](/Users/Ahmet/Repo/TradingAgents/agent_os/backend/services/langgraph_engine.py) after runtime stabilization

Market stall reproduction command (exit quickly when no progress):

```bash
./scripts/run_node_live.py \
  --trigger \
  --ticker AAPL \
  --date 2026-03-31 \
  --analysts market \
  --show-system \
  --watch-nodes "Market Analyst,__system__" \
  --heartbeat-seconds 15 \
  --stall-seconds 120 \
  --exit-on-stall \
  --write-run-json /tmp/aapl-market-stall.json
```

If you want automatic cleanup when stalled:

```bash
./scripts/run_node_live.py \
  --trigger \
  --ticker AAPL \
  --date 2026-03-31 \
  --analysts market \
  --show-system \
  --watch-nodes "Market Analyst,__system__" \
  --heartbeat-seconds 15 \
  --stall-seconds 120 \
  --stop-on-stall \
  --exit-on-stall \
  --write-run-json /tmp/aapl-market-stall.json
```

Note: when `--exit-on-stall` is used, the saved run JSON is captured at stall detection time. It may still show `status=running` even if `--stop-on-stall` was sent immediately after.
