# Node-by-Node Terminal Testing Guide

## Purpose

This guide defines a repeatable terminal workflow to:

1. implement a fix for a specific graph node
2. run that node path live
3. monitor in-flight events
4. validate artifacts for hallucination/provenance behavior
5. move to the next node

Use this for structured-contract migration and hallucination hardening work.

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

## 6) Node-by-node execution loop

For each node in top-down order:

1. apply code change for that node contract
2. run node/unit tests
3. run live scoped pipeline for that node path
4. monitor events until complete/fail/timeout
5. inspect persisted artifacts
6. record pass/fail notes before moving to next node

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
