# Hypothesis Backtesting System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a branch-per-hypothesis experimentation system that runs scanner code changes daily in isolation, accumulates picks, auto-concludes with a statistical comparison, and surfaces everything in the dashboard.

**Architecture:** `active.json` is the registry (lives on `main`). Each hypothesis gets a `hypothesis/<scanner>-<slug>` branch with the code change. A daily workflow (08:00 UTC) uses git worktrees to run discovery on each branch, stores picks in `docs/iterations/hypotheses/<id>/picks.json` on the hypothesis branch, and concludes when `min_days` elapsed. The `/backtest-hypothesis` command classifies, creates branches, and manages the registry.

**Tech Stack:** Python 3.10, yfinance (`download_history`), GitHub Actions, Streamlit, `gh` CLI, `git worktree`

---

## File Map

| Path | Action | Purpose |
|---|---|---|
| `docs/iterations/hypotheses/active.json` | Create | Registry of all experiments |
| `docs/iterations/hypotheses/concluded/.gitkeep` | Create | Directory placeholder |
| `scripts/compare_hypothesis.py` | Create | Fetch returns + statistical comparison |
| `.claude/commands/backtest-hypothesis.md` | Create | `/backtest-hypothesis` Claude command |
| `.github/workflows/hypothesis-runner.yml` | Create | Daily 08:00 UTC runner |
| `tradingagents/ui/pages/hypotheses.py` | Create | Dashboard "Hypotheses" tab |
| `tradingagents/ui/pages/__init__.py` | Modify | Register new page |
| `tradingagents/ui/dashboard.py` | Modify | Add "Hypotheses" to nav |

---

## Task 1: Hypothesis Registry Structure

**Files:**
- Create: `docs/iterations/hypotheses/active.json`
- Create: `docs/iterations/hypotheses/concluded/.gitkeep`

- [ ] **Step 1: Create the directory and initial `active.json`**

```bash
mkdir -p docs/iterations/hypotheses/concluded
```

Write `docs/iterations/hypotheses/active.json`:

```json
{
  "max_active": 5,
  "hypotheses": []
}
```

- [ ] **Step 2: Create the concluded directory placeholder**

```bash
touch docs/iterations/hypotheses/concluded/.gitkeep
```

- [ ] **Step 3: Verify JSON is valid**

```bash
python3 -c "import json; json.load(open('docs/iterations/hypotheses/active.json')); print('valid')"
```

Expected: `valid`

- [ ] **Step 4: Commit**

```bash
git add docs/iterations/hypotheses/
git commit -m "feat(hypotheses): initialize hypothesis registry"
```

---

## Task 2: Comparison Script

**Files:**
- Create: `scripts/compare_hypothesis.py`
- Create: `tests/test_compare_hypothesis.py`

`★ Insight ─────────────────────────────────────`
The comparison reads picks from the hypothesis branch via `git show <branch>:path` — this avoids checking out the branch just to read a file, keeping the working tree on `main` throughout.
`─────────────────────────────────────────────────`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_compare_hypothesis.py`:

```python
"""Tests for the hypothesis comparison script."""
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.compare_hypothesis import (
    compute_metrics,
    compute_7d_return,
    load_baseline_metrics,
    make_decision,
)


# ── compute_metrics ──────────────────────────────────────────────────────────

def test_compute_metrics_empty():
    result = compute_metrics([])
    assert result == {"count": 0, "evaluated": 0, "win_rate": None, "avg_return": None}


def test_compute_metrics_all_wins():
    picks = [
        {"return_7d": 5.0, "win_7d": True},
        {"return_7d": 3.0, "win_7d": True},
    ]
    result = compute_metrics(picks)
    assert result["win_rate"] == 100.0
    assert result["avg_return"] == 4.0
    assert result["evaluated"] == 2


def test_compute_metrics_mixed():
    picks = [
        {"return_7d": 10.0, "win_7d": True},
        {"return_7d": -5.0, "win_7d": False},
        {"return_7d": None, "win_7d": None},   # pending — excluded
    ]
    result = compute_metrics(picks)
    assert result["win_rate"] == 50.0
    assert result["avg_return"] == 2.5
    assert result["evaluated"] == 2
    assert result["count"] == 3


# ── compute_7d_return ────────────────────────────────────────────────────────

def test_compute_7d_return_positive():
    mock_df = MagicMock()
    mock_df.empty = False
    # Simulate DataFrame with Close column: entry=100, exit=110
    mock_df.__len__ = lambda self: 2
    mock_df["Close"].iloc.__getitem__ = MagicMock(side_effect=lambda i: 100.0 if i == 0 else 110.0)

    with patch("scripts.compare_hypothesis.download_history", return_value=mock_df):
        ret, win = compute_7d_return("AAPL", "2026-03-01")

    assert ret == pytest.approx(10.0, rel=0.01)
    assert win is True


def test_compute_7d_return_empty_data():
    mock_df = MagicMock()
    mock_df.empty = True

    with patch("scripts.compare_hypothesis.download_history", return_value=mock_df):
        ret, win = compute_7d_return("AAPL", "2026-03-01")

    assert ret is None
    assert win is None


# ── load_baseline_metrics ────────────────────────────────────────────────────

def test_load_baseline_metrics(tmp_path):
    db = {
        "recommendations_by_date": {
            "2026-03-01": [
                {"strategy_match": "options_flow", "return_7d": 5.0, "win_7d": True},
                {"strategy_match": "options_flow", "return_7d": -2.0, "win_7d": False},
                {"strategy_match": "reddit_dd", "return_7d": 3.0, "win_7d": True},
            ]
        }
    }
    db_file = tmp_path / "performance_database.json"
    db_file.write_text(json.dumps(db))

    result = load_baseline_metrics("options_flow", str(db_file))

    assert result["win_rate"] == 50.0
    assert result["avg_return"] == 1.5
    assert result["count"] == 2


def test_load_baseline_metrics_missing_file(tmp_path):
    result = load_baseline_metrics("options_flow", str(tmp_path / "missing.json"))
    assert result == {"count": 0, "win_rate": None, "avg_return": None}


# ── make_decision ─────────────────────────────────────────────────────────────

def test_make_decision_accepted_by_win_rate():
    hyp = {"win_rate": 60.0, "avg_return": 0.5, "evaluated": 10}
    baseline = {"win_rate": 50.0, "avg_return": 0.5}
    decision, reason = make_decision(hyp, baseline)
    assert decision == "accepted"
    assert "win rate" in reason.lower()


def test_make_decision_accepted_by_return():
    hyp = {"win_rate": 52.0, "avg_return": 3.0, "evaluated": 10}
    baseline = {"win_rate": 50.0, "avg_return": 1.5}
    decision, reason = make_decision(hyp, baseline)
    assert decision == "accepted"
    assert "return" in reason.lower()


def test_make_decision_rejected():
    hyp = {"win_rate": 48.0, "avg_return": 0.2, "evaluated": 10}
    baseline = {"win_rate": 50.0, "avg_return": 1.0}
    decision, reason = make_decision(hyp, baseline)
    assert decision == "rejected"


def test_make_decision_insufficient_data():
    hyp = {"win_rate": 80.0, "avg_return": 5.0, "evaluated": 2}
    baseline = {"win_rate": 50.0, "avg_return": 1.0}
    decision, reason = make_decision(hyp, baseline)
    assert decision == "rejected"
    assert "insufficient" in reason.lower()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_compare_hypothesis.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'scripts.compare_hypothesis'` or similar import error — confirms tests are wired correctly.

- [ ] **Step 3: Write `scripts/compare_hypothesis.py`**

```python
#!/usr/bin/env python3
"""
Hypothesis comparison — computes 7d returns for hypothesis picks and
compares them against the baseline scanner in performance_database.json.

Usage (called by hypothesis-runner.yml after min_days elapsed):
    python scripts/compare_hypothesis.py \\
        --hypothesis-id options_flow-scan-3-expirations \\
        --picks-json '{"picks": [...]}' \\
        --scanner options_flow \\
        --db-path data/recommendations/performance_database.json

Prints a JSON conclusion to stdout:
    {
      "decision": "accepted",
      "reason": "...",
      "hypothesis": {"win_rate": 58.0, "avg_return": 1.8, "count": 14, "evaluated": 10},
      "baseline":   {"win_rate": 42.0, "avg_return": -0.3, "count": 87}
    }
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tradingagents.dataflows.y_finance import download_history


# Minimum evaluated picks required to make a decision
_MIN_EVALUATED = 5
# Thresholds from spec
_WIN_RATE_DELTA_THRESHOLD = 5.0   # percentage points
_AVG_RETURN_DELTA_THRESHOLD = 1.0  # percent


def compute_7d_return(ticker: str, pick_date: str) -> Tuple[Optional[float], Optional[bool]]:
    """
    Fetch 7-day return for a pick using yfinance.

    Args:
        ticker: Stock symbol, e.g. "AAPL"
        pick_date: Date the pick was made, "YYYY-MM-DD"

    Returns:
        (return_pct, is_win) or (None, None) if data unavailable
    """
    try:
        entry_dt = datetime.strptime(pick_date, "%Y-%m-%d")
        exit_dt = entry_dt + timedelta(days=10)  # +3 buffer for weekends/holidays
        df = download_history(
            ticker,
            start=entry_dt.strftime("%Y-%m-%d"),
            end=exit_dt.strftime("%Y-%m-%d"),
        )
        if df.empty or len(df) < 2:
            return None, None

        # Use first available close as entry, 7th trading day as exit
        close = df["Close"]
        entry_price = float(close.iloc[0])
        exit_idx = min(5, len(close) - 1)  # ~7 calendar days = ~5 trading days
        exit_price = float(close.iloc[exit_idx])

        if entry_price <= 0:
            return None, None

        ret = (exit_price - entry_price) / entry_price * 100
        return round(ret, 4), ret > 0

    except Exception:
        return None, None


def enrich_picks_with_returns(picks: list) -> list:
    """
    Compute 7d return for each pick that is old enough (>= 7 days) and
    doesn't already have return_7d populated.

    Args:
        picks: List of pick dicts with at least 'ticker' and 'date' fields

    Returns:
        Same list with return_7d and win_7d populated where possible
    """
    cutoff = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    for pick in picks:
        if pick.get("return_7d") is not None:
            continue  # already computed
        if pick.get("date", "9999-99-99") > cutoff:
            continue  # too recent
        ret, win = compute_7d_return(pick["ticker"], pick["date"])
        pick["return_7d"] = ret
        pick["win_7d"] = win
    return picks


def compute_metrics(picks: list) -> dict:
    """
    Compute win rate and avg return for a list of picks.

    Only picks with non-None return_7d contribute to win_rate and avg_return.

    Returns:
        {"count": int, "evaluated": int, "win_rate": float|None, "avg_return": float|None}
    """
    evaluated = [p for p in picks if p.get("return_7d") is not None]
    if not evaluated:
        return {"count": len(picks), "evaluated": 0, "win_rate": None, "avg_return": None}

    wins = sum(1 for p in evaluated if p.get("win_7d"))
    avg_ret = sum(p["return_7d"] for p in evaluated) / len(evaluated)
    return {
        "count": len(picks),
        "evaluated": len(evaluated),
        "win_rate": round(wins / len(evaluated) * 100, 1),
        "avg_return": round(avg_ret, 2),
    }


def load_baseline_metrics(scanner: str, db_path: str) -> dict:
    """
    Load baseline metrics for a scanner from performance_database.json.

    Args:
        scanner: Scanner name, e.g. "options_flow"
        db_path: Path to performance_database.json

    Returns:
        {"count": int, "win_rate": float|None, "avg_return": float|None}
    """
    path = Path(db_path)
    if not path.exists():
        return {"count": 0, "win_rate": None, "avg_return": None}

    try:
        with open(path) as f:
            db = json.load(f)
    except Exception:
        return {"count": 0, "win_rate": None, "avg_return": None}

    picks = []
    for recs in db.get("recommendations_by_date", {}).values():
        for rec in (recs if isinstance(recs, list) else []):
            if rec.get("strategy_match") == scanner and rec.get("return_7d") is not None:
                picks.append(rec)

    return compute_metrics(picks)


def make_decision(hypothesis: dict, baseline: dict) -> Tuple[str, str]:
    """
    Decide accepted or rejected based on metrics delta.

    Rules:
    - Minimum _MIN_EVALUATED evaluated picks required
    - accepted if win_rate_delta > _WIN_RATE_DELTA_THRESHOLD (5pp)
      OR avg_return_delta > _AVG_RETURN_DELTA_THRESHOLD (1%)
    - rejected otherwise

    Returns:
        (decision, reason) where decision is "accepted" or "rejected"
    """
    evaluated = hypothesis.get("evaluated", 0)
    if evaluated < _MIN_EVALUATED:
        return "rejected", f"Insufficient data: only {evaluated} evaluated picks (need {_MIN_EVALUATED})"

    hyp_wr = hypothesis.get("win_rate")
    hyp_ret = hypothesis.get("avg_return")
    base_wr = baseline.get("win_rate")
    base_ret = baseline.get("avg_return")

    reasons = []

    if hyp_wr is not None and base_wr is not None:
        delta_wr = hyp_wr - base_wr
        if delta_wr > _WIN_RATE_DELTA_THRESHOLD:
            reasons.append(f"win rate improved by {delta_wr:+.1f}pp ({base_wr:.1f}% → {hyp_wr:.1f}%)")

    if hyp_ret is not None and base_ret is not None:
        delta_ret = hyp_ret - base_ret
        if delta_ret > _AVG_RETURN_DELTA_THRESHOLD:
            reasons.append(f"avg return improved by {delta_ret:+.2f}% ({base_ret:+.2f}% → {hyp_ret:+.2f}%)")

    if reasons:
        return "accepted", "; ".join(reasons)

    wr_str = f"{hyp_wr:.1f}% vs baseline {base_wr:.1f}%" if hyp_wr is not None else "no win rate data"
    ret_str = f"{hyp_ret:+.2f}% vs baseline {base_ret:+.2f}%" if hyp_ret is not None else "no return data"
    return "rejected", f"No significant improvement — win rate: {wr_str}; avg return: {ret_str}"


def main():
    parser = argparse.ArgumentParser(description="Compare hypothesis picks against baseline")
    parser.add_argument("--hypothesis-id", required=True)
    parser.add_argument("--picks-json", required=True, help="JSON string of picks list")
    parser.add_argument("--scanner", required=True, help="Baseline scanner name")
    parser.add_argument(
        "--db-path",
        default="data/recommendations/performance_database.json",
        help="Path to performance_database.json",
    )
    args = parser.parse_args()

    picks = json.loads(args.picks_json)
    picks = enrich_picks_with_returns(picks)

    hyp_metrics = compute_metrics(picks)
    base_metrics = load_baseline_metrics(args.scanner, args.db_path)

    decision, reason = make_decision(hyp_metrics, base_metrics)

    result = {
        "hypothesis_id": args.hypothesis_id,
        "decision": decision,
        "reason": reason,
        "hypothesis": hyp_metrics,
        "baseline": base_metrics,
        "enriched_picks": picks,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_compare_hypothesis.py -v
```

Expected: all 10 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/compare_hypothesis.py tests/test_compare_hypothesis.py
git commit -m "feat(hypotheses): add comparison + conclusion script"
```

---

## Task 3: `/backtest-hypothesis` Command

**Files:**
- Create: `.claude/commands/backtest-hypothesis.md`

- [ ] **Step 1: Write the command file**

Create `.claude/commands/backtest-hypothesis.md`:

````markdown
# /backtest-hypothesis

Test a hypothesis about a scanner improvement using branch-per-hypothesis isolation.

**Usage:** `/backtest-hypothesis "<description of the hypothesis>"`

**Example:** `/backtest-hypothesis "options_flow: scan 3 expirations instead of 1 to capture institutional 30+ DTE positioning"`

---

## Step 1: Read Current Registry

Read `docs/iterations/hypotheses/active.json`. Note:
- How many hypotheses currently have `status: "running"`
- The `max_active` limit (default 5)
- Any existing `pending` entries

Also read `docs/iterations/LEARNINGS.md` and the relevant scanner domain file in
`docs/iterations/scanners/` to understand the current baseline.

## Step 2: Classify the Hypothesis

Determine whether this is:

**Statistical** — answerable from existing data in `data/recommendations/performance_database.json`
without any code change. Examples:
- "Does high confidence (≥8) predict better 30d returns?"
- "Are options_flow picks that are ITM outperforming OTM ones?"

**Implementation** — requires a code change and forward-testing period. Examples:
- "Scan 3 expirations instead of 1"
- "Apply a premium filter of $50K instead of $25K"

## Step 3a: Statistical Path

If statistical: run the analysis now against `data/recommendations/performance_database.json`.
Write the finding to the relevant scanner domain file under **Evidence Log**. Print a summary.
Done — no branch needed.

## Step 3b: Implementation Path

### 3b-i: Capacity check

Count running hypotheses from `active.json`. If fewer than `max_active` running, proceed.
If at capacity: add the new hypothesis as `status: "pending"` — running experiments are NEVER
paused mid-streak. Inform the user which slot it queued behind and when it will likely start.

### 3b-ii: Score the hypothesis

Assign a `priority` score (1–9) using these factors:

| Factor | Score |
|---|---|
| Scanner 30d win rate < 40% | +3 |
| Change touches 1 file, 1 parameter | +2 |
| Directly addresses a weak spot in LEARNINGS.md | +2 |
| Scanner generates ≥2 picks/day (data accrues fast) | +1 |
| Supported by external research (arXiv, Alpha Architect, etc.) | +1 |
| Contradictory evidence or unclear direction | −2 |

### 3b-iii: Determine min_days

Set `min_days` based on the scanner's typical picks-per-day rate:
- ≥2 picks/day → 14 days
- 1 pick/day → 21 days
- <1 pick/day → 30 days

### 3b-iv: Create the branch and implement the code change

```bash
BRANCH="hypothesis/<scanner>-<slug>"
git checkout -b "$BRANCH"
```

Make the minimal code change that implements the hypothesis. Read the scanner file first.
Only change what the hypothesis requires — do not refactor surrounding code.

```bash
git add tradingagents/
git commit -m "hypothesis(<scanner>): <title>"
```

### 3b-v: Create picks tracking file on the branch

Create `docs/iterations/hypotheses/<id>/picks.json` on the hypothesis branch:

```json
{
  "hypothesis_id": "<id>",
  "scanner": "<scanner>",
  "picks": []
}
```

```bash
mkdir -p docs/iterations/hypotheses/<id>
# write the file
git add docs/iterations/hypotheses/<id>/picks.json
git commit -m "hypothesis(<scanner>): add picks tracker"
git push -u origin "$BRANCH"
```

### 3b-vi: Open a draft PR

```bash
gh pr create \
  --title "hypothesis(<scanner>): <title>" \
  --body "**Hypothesis:** <description>

**Expected impact:** <high/medium/low>
**Min days:** <N>
**Priority:** <score>/9

*This is an automated hypothesis experiment. It will be auto-concluded after ${MIN_DAYS} days of data.*" \
  --draft \
  --base main
```

Note the PR number from the output.

### 3b-vii: Update active.json on main

Check out `main`, then update `docs/iterations/hypotheses/active.json` to add the new entry:

```json
{
  "id": "<scanner>-<slug>",
  "scanner": "<scanner>",
  "title": "<title>",
  "description": "<description>",
  "branch": "hypothesis/<scanner>-<slug>",
  "pr_number": <N>,
  "status": "running",
  "priority": <score>,
  "expected_impact": "<high|medium|low>",
  "hypothesis_type": "implementation",
  "created_at": "<YYYY-MM-DD>",
  "min_days": <N>,
  "days_elapsed": 0,
  "picks_log": [],
  "baseline_scanner": "<scanner>",
  "conclusion": null
}
```

```bash
git checkout main
git add docs/iterations/hypotheses/active.json
git commit -m "feat(hypotheses): register hypothesis <id>"
git push origin main
```

## Step 4: Print Summary

Print a confirmation:
- Hypothesis ID and branch name
- Status: running or pending
- Expected conclusion date (created_at + min_days)
- PR link (if running)
- Priority score and why
````

- [ ] **Step 2: Verify the file exists and is non-empty**

```bash
wc -l .claude/commands/backtest-hypothesis.md
```

Expected: at least 80 lines.

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/backtest-hypothesis.md
git commit -m "feat(hypotheses): add /backtest-hypothesis command"
```

---

## Task 4: Hypothesis Runner Workflow

**Files:**
- Create: `.github/workflows/hypothesis-runner.yml`

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/hypothesis-runner.yml`:

```yaml
name: Hypothesis Runner

on:
  schedule:
    # 8:00 AM UTC daily — runs after iterate (06:00) and daily-discovery (12:30)
    - cron: "0 8 * * *"
  workflow_dispatch:
    inputs:
      hypothesis_id:
        description: "Run a specific hypothesis ID only (blank = all running)"
        required: false
        default: ""

env:
  PYTHON_VERSION: "3.10"

jobs:
  run-hypotheses:
    runs-on: ubuntu-latest
    environment: TradingAgent
    timeout-minutes: 60
    permissions:
      contents: write
      pull-requests: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GH_TOKEN }}

      - name: Set up git identity
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip

      - name: Install dependencies
        run: pip install --upgrade pip && pip install -e .

      - name: Run hypothesis experiments
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          FINNHUB_API_KEY: ${{ secrets.FINNHUB_API_KEY }}
          ALPHA_VANTAGE_API_KEY: ${{ secrets.ALPHA_VANTAGE_API_KEY }}
          FMP_API_KEY: ${{ secrets.FMP_API_KEY }}
          REDDIT_CLIENT_ID: ${{ secrets.REDDIT_CLIENT_ID }}
          REDDIT_CLIENT_SECRET: ${{ secrets.REDDIT_CLIENT_SECRET }}
          TRADIER_API_KEY: ${{ secrets.TRADIER_API_KEY }}
          FILTER_ID: ${{ inputs.hypothesis_id }}
        run: |
          python scripts/run_hypothesis_runner.py

      - name: Commit active.json updates
        run: |
          git add docs/iterations/hypotheses/active.json || true
          if git diff --cached --quiet; then
            echo "No registry changes"
          else
            git commit -m "chore(hypotheses): update registry $(date -u +%Y-%m-%d)"
            git pull --rebase origin main
            git push origin main
          fi
```

- [ ] **Step 2: Write `scripts/run_hypothesis_runner.py`**

Create `scripts/run_hypothesis_runner.py`:

```python
#!/usr/bin/env python3
"""
Hypothesis Runner — orchestrates daily experiment cycles.

For each running hypothesis in active.json:
  1. Creates a git worktree for the hypothesis branch
  2. Runs the daily discovery pipeline in that worktree
  3. Extracts picks from the discovery result, appends to picks.json
  4. Commits and pushes picks to hypothesis branch
  5. Removes worktree
  6. Updates active.json (days_elapsed, picks_log)
  7. If days_elapsed >= min_days: concludes the hypothesis

After all hypotheses: promotes highest-priority pending → running if a slot opened.

Environment variables read:
  FILTER_ID — if set, only run the hypothesis with this ID
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ACTIVE_JSON = ROOT / "docs/iterations/hypotheses/active.json"
CONCLUDED_DIR = ROOT / "docs/iterations/hypotheses/concluded"
DB_PATH = ROOT / "data/recommendations/performance_database.json"
TODAY = datetime.utcnow().strftime("%Y-%m-%d")


def load_registry() -> dict:
    with open(ACTIVE_JSON) as f:
        return json.load(f)


def save_registry(registry: dict) -> None:
    with open(ACTIVE_JSON, "w") as f:
        json.dump(registry, f, indent=2)


def run(cmd: list, cwd: str = None, check: bool = True) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=cwd or str(ROOT), check=check, capture_output=False)


def run_capture(cmd: list, cwd: str = None) -> str:
    result = subprocess.run(cmd, cwd=cwd or str(ROOT), capture_output=True, text=True)
    return result.stdout.strip()


def extract_picks(worktree: str, scanner: str) -> list:
    """
    Extract picks for the given scanner from the most recent discovery result
    in the worktree's results/discovery/<TODAY>/ directory.
    """
    results_dir = Path(worktree) / "results" / "discovery" / TODAY
    if not results_dir.exists():
        print(f"    No discovery results for {TODAY} in worktree", flush=True)
        return []

    picks = []
    for run_dir in sorted(results_dir.iterdir()):
        result_file = run_dir / "discovery_result.json"
        if not result_file.exists():
            continue
        try:
            with open(result_file) as f:
                data = json.load(f)
            for item in data.get("final_ranking", []):
                if item.get("strategy_match") == scanner:
                    picks.append({
                        "date": TODAY,
                        "ticker": item["ticker"],
                        "score": item.get("final_score"),
                        "confidence": item.get("confidence"),
                        "scanner": scanner,
                        "return_7d": None,
                        "win_7d": None,
                    })
        except Exception as e:
            print(f"    Warning: could not read {result_file}: {e}", flush=True)

    return picks


def load_picks_from_branch(hypothesis_id: str, branch: str) -> list:
    """Load picks.json from the hypothesis branch using git show."""
    picks_path = f"docs/iterations/hypotheses/{hypothesis_id}/picks.json"
    result = subprocess.run(
        ["git", "show", f"{branch}:{picks_path}"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout).get("picks", [])
    except Exception:
        return []


def save_picks_to_worktree(worktree: str, hypothesis_id: str, scanner: str, picks: list) -> None:
    """Write updated picks.json into the worktree and commit."""
    picks_dir = Path(worktree) / "docs" / "iterations" / "hypotheses" / hypothesis_id
    picks_dir.mkdir(parents=True, exist_ok=True)
    picks_file = picks_dir / "picks.json"
    payload = {"hypothesis_id": hypothesis_id, "scanner": scanner, "picks": picks}
    picks_file.write_text(json.dumps(payload, indent=2))

    run(["git", "add", str(picks_file)], cwd=worktree)
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=worktree
    )
    if result.returncode != 0:
        run(
            ["git", "commit", "-m", f"chore(hypotheses): picks {TODAY} for {hypothesis_id}"],
            cwd=worktree,
        )


def run_hypothesis(hyp: dict) -> bool:
    """
    Run one hypothesis experiment cycle. Returns True if the experiment concluded.
    """
    hid = hyp["id"]
    branch = hyp["branch"]
    scanner = hyp["scanner"]
    worktree = f"/tmp/hyp-{hid}"

    print(f"\n── Hypothesis: {hid} ──", flush=True)

    # 1. Create worktree
    run(["git", "fetch", "origin", branch], check=False)
    run(["git", "worktree", "add", worktree, branch])

    try:
        # 2. Run discovery in worktree
        result = subprocess.run(
            [sys.executable, "scripts/run_daily_discovery.py", "--date", TODAY, "--no-update-positions"],
            cwd=worktree,
            check=False,
        )
        if result.returncode != 0:
            print(f"    Discovery failed for {hid}, skipping picks update", flush=True)
        else:
            # 3. Extract picks + merge with existing
            new_picks = extract_picks(worktree, scanner)
            existing_picks = load_picks_from_branch(hid, branch)
            # Deduplicate by (date, ticker)
            seen = {(p["date"], p["ticker"]) for p in existing_picks}
            merged = existing_picks + [p for p in new_picks if (p["date"], p["ticker"]) not in seen]

            # 4. Save picks + commit in worktree
            save_picks_to_worktree(worktree, hid, scanner, merged)

            # 5. Push hypothesis branch
            run(["git", "push", "origin", f"HEAD:{branch}"], cwd=worktree)

        # 6. Update registry fields
        if TODAY not in hyp.get("picks_log", []):
            hyp.setdefault("picks_log", []).append(TODAY)
        hyp["days_elapsed"] = len(hyp["picks_log"])

        # 7. Check conclusion
        if hyp["days_elapsed"] >= hyp["min_days"]:
            return conclude_hypothesis(hyp)

    finally:
        run(["git", "worktree", "remove", "--force", worktree], check=False)

    return False


def conclude_hypothesis(hyp: dict) -> bool:
    """Run comparison, write conclusion doc, close/merge PR. Returns True."""
    hid = hyp["id"]
    scanner = hyp["scanner"]
    branch = hyp["branch"]

    print(f"\n  Concluding {hid}...", flush=True)

    # Load picks from branch
    picks = load_picks_from_branch(hid, branch)
    if not picks:
        print(f"    No picks found for {hid}, marking rejected", flush=True)
        conclusion = {
            "decision": "rejected",
            "reason": "No picks were collected during the experiment period",
            "hypothesis": {"count": 0, "evaluated": 0, "win_rate": None, "avg_return": None},
            "baseline": {"count": 0, "win_rate": None, "avg_return": None},
        }
    else:
        # Run comparison script
        result = subprocess.run(
            [
                sys.executable, "scripts/compare_hypothesis.py",
                "--hypothesis-id", hid,
                "--picks-json", json.dumps(picks),
                "--scanner", scanner,
                "--db-path", str(DB_PATH),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"    compare_hypothesis.py failed: {result.stderr}", flush=True)
            return False
        conclusion = json.loads(result.stdout)

    decision = conclusion["decision"]
    hyp_metrics = conclusion["hypothesis"]
    base_metrics = conclusion["baseline"]

    # Write concluded doc
    period_start = hyp.get("created_at", TODAY)
    concluded_doc = CONCLUDED_DIR / f"{TODAY}-{hid}.md"
    concluded_doc.write_text(
        f"# Hypothesis: {hyp['title']}\n\n"
        f"**Scanner:** {scanner}\n"
        f"**Branch:** {branch}\n"
        f"**Period:** {period_start} → {TODAY} ({hyp['days_elapsed']} days)\n"
        f"**Outcome:** {'accepted ✅' if decision == 'accepted' else 'rejected ❌'}\n\n"
        f"## Hypothesis\n{hyp.get('description', hyp['title'])}\n\n"
        f"## Results\n\n"
        f"| Metric | Baseline | Experiment | Delta |\n"
        f"|---|---|---|---|\n"
        f"| 7d win rate | {base_metrics.get('win_rate') or '—'}% | "
        f"{hyp_metrics.get('win_rate') or '—'}% | "
        f"{_delta_str(hyp_metrics.get('win_rate'), base_metrics.get('win_rate'), 'pp')} |\n"
        f"| Avg return | {base_metrics.get('avg_return') or '—'}% | "
        f"{hyp_metrics.get('avg_return') or '—'}% | "
        f"{_delta_str(hyp_metrics.get('avg_return'), base_metrics.get('avg_return'), '%')} |\n"
        f"| Picks | {base_metrics.get('count', '—')} | {hyp_metrics.get('count', '—')} | — |\n\n"
        f"## Decision\n{conclusion['reason']}\n\n"
        f"## Action\n"
        f"{'Branch merged into main.' if decision == 'accepted' else 'Branch closed without merging.'}\n"
    )

    run(["git", "add", str(concluded_doc)], check=False)

    # Close or merge PR
    pr = hyp.get("pr_number")
    if pr:
        if decision == "accepted":
            subprocess.run(
                ["gh", "pr", "merge", str(pr), "--squash", "--delete-branch"],
                cwd=str(ROOT), check=False,
            )
        else:
            subprocess.run(
                ["gh", "pr", "close", str(pr), "--delete-branch"],
                cwd=str(ROOT), check=False,
            )

    # Update registry entry
    hyp["status"] = "concluded"
    hyp["conclusion"] = decision

    print(f"  {hid}: {decision} — {conclusion['reason']}", flush=True)
    return True


def _delta_str(hyp_val, base_val, unit: str) -> str:
    if hyp_val is None or base_val is None:
        return "—"
    delta = hyp_val - base_val
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.1f}{unit}"


def promote_pending(registry: dict) -> None:
    """Promote the highest-priority pending hypothesis to running if a slot is open."""
    running_count = sum(1 for h in registry["hypotheses"] if h["status"] == "running")
    max_active = registry.get("max_active", 5)
    if running_count >= max_active:
        return

    pending = [h for h in registry["hypotheses"] if h["status"] == "pending"]
    if not pending:
        return

    # Promote highest priority
    to_promote = max(pending, key=lambda h: h.get("priority", 0))
    to_promote["status"] = "running"
    print(f"\n  Promoted pending hypothesis to running: {to_promote['id']}", flush=True)


def main():
    registry = load_registry()
    filter_id = os.environ.get("FILTER_ID", "").strip()

    hypotheses = registry.get("hypotheses", [])
    running = [
        h for h in hypotheses
        if h["status"] == "running" and (not filter_id or h["id"] == filter_id)
    ]

    if not running:
        print("No running hypotheses to process.", flush=True)
    else:
        for hyp in running:
            run_hypothesis(hyp)

    promote_pending(registry)
    save_registry(registry)
    print("\nRegistry updated.", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify the workflow YAML is valid**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/hypothesis-runner.yml'))" 2>/dev/null \
  || python3 -c "
import re, sys
with open('.github/workflows/hypothesis-runner.yml') as f:
    content = f.read()
# Just check the file exists and has the cron line
assert '0 8 * * *' in content, 'missing cron'
print('workflow file looks good')
"
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/hypothesis-runner.yml scripts/run_hypothesis_runner.py
git commit -m "feat(hypotheses): add daily hypothesis runner workflow"
```

---

## Task 5: Dashboard Hypotheses Tab

**Files:**
- Create: `tradingagents/ui/pages/hypotheses.py`
- Modify: `tradingagents/ui/pages/__init__.py`
- Modify: `tradingagents/ui/dashboard.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_hypotheses_page.py`:

```python
"""Tests for the hypotheses dashboard page data loading."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


from tradingagents.ui.pages.hypotheses import (
    load_active_hypotheses,
    load_concluded_hypotheses,
    days_until_ready,
)


# ── load_active_hypotheses ────────────────────────────────────────────────────

def test_load_active_hypotheses(tmp_path):
    active = {
        "max_active": 5,
        "hypotheses": [
            {
                "id": "options_flow-test",
                "title": "Test hypothesis",
                "scanner": "options_flow",
                "status": "running",
                "priority": 7,
                "days_elapsed": 5,
                "min_days": 14,
                "created_at": "2026-04-01",
                "picks_log": ["2026-04-01"] * 5,
                "conclusion": None,
            }
        ],
    }
    f = tmp_path / "active.json"
    f.write_text(json.dumps(active))

    result = load_active_hypotheses(str(f))
    assert len(result) == 1
    assert result[0]["id"] == "options_flow-test"


def test_load_active_hypotheses_missing_file(tmp_path):
    result = load_active_hypotheses(str(tmp_path / "missing.json"))
    assert result == []


# ── load_concluded_hypotheses ─────────────────────────────────────────────────

def test_load_concluded_hypotheses(tmp_path):
    doc = tmp_path / "2026-04-10-options_flow-test.md"
    doc.write_text(
        "# Hypothesis: Test\n\n"
        "**Scanner:** options_flow\n"
        "**Period:** 2026-03-27 → 2026-04-10 (14 days)\n"
        "**Outcome:** accepted ✅\n"
    )

    results = load_concluded_hypotheses(str(tmp_path))
    assert len(results) == 1
    assert results[0]["filename"] == doc.name
    assert results[0]["outcome"] == "accepted ✅"


def test_load_concluded_hypotheses_empty_dir(tmp_path):
    results = load_concluded_hypotheses(str(tmp_path))
    assert results == []


# ── days_until_ready ──────────────────────────────────────────────────────────

def test_days_until_ready_has_days_left():
    hyp = {"days_elapsed": 5, "min_days": 14}
    assert days_until_ready(hyp) == 9


def test_days_until_ready_past_due():
    hyp = {"days_elapsed": 15, "min_days": 14}
    assert days_until_ready(hyp) == 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_hypotheses_page.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError` for `tradingagents.ui.pages.hypotheses`.

- [ ] **Step 3: Write `tradingagents/ui/pages/hypotheses.py`**

```python
"""
Hypotheses dashboard page — tracks active and concluded experiments.

Reads docs/iterations/hypotheses/active.json and the concluded/ directory.
No external API calls; all data is file-based.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from tradingagents.ui.theme import COLORS, page_header

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_ACTIVE_JSON = _REPO_ROOT / "docs/iterations/hypotheses/active.json"
_CONCLUDED_DIR = _REPO_ROOT / "docs/iterations/hypotheses/concluded"


# ── Data loaders ─────────────────────────────────────────────────────────────


def load_active_hypotheses(active_path: str = str(_ACTIVE_JSON)) -> List[Dict[str, Any]]:
    """Load all hypotheses from active.json. Returns [] if file missing."""
    path = Path(active_path)
    if not path.exists():
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        return data.get("hypotheses", [])
    except Exception:
        return []


def load_concluded_hypotheses(concluded_dir: str = str(_CONCLUDED_DIR)) -> List[Dict[str, Any]]:
    """
    Load concluded hypothesis metadata by parsing the markdown files in concluded/.

    Extracts: filename, title, scanner, period, outcome from each .md file.
    """
    dir_path = Path(concluded_dir)
    if not dir_path.exists():
        return []

    results = []
    for md_file in sorted(dir_path.glob("*.md"), reverse=True):
        if md_file.name == ".gitkeep":
            continue
        try:
            text = md_file.read_text()
            title = _extract_md_field(text, r"^# Hypothesis: (.+)$")
            scanner = _extract_md_field(text, r"^\*\*Scanner:\*\* (.+)$")
            period = _extract_md_field(text, r"^\*\*Period:\*\* (.+)$")
            outcome = _extract_md_field(text, r"^\*\*Outcome:\*\* (.+)$")
            results.append({
                "filename": md_file.name,
                "title": title or md_file.stem,
                "scanner": scanner or "—",
                "period": period or "—",
                "outcome": outcome or "—",
            })
        except Exception:
            continue

    return results


def _extract_md_field(text: str, pattern: str) -> str:
    """Extract a field value from a markdown line using regex."""
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def days_until_ready(hyp: Dict[str, Any]) -> int:
    """Return number of days remaining before hypothesis can conclude (min 0)."""
    return max(0, hyp.get("min_days", 14) - hyp.get("days_elapsed", 0))


# ── Rendering ─────────────────────────────────────────────────────────────────


def render() -> None:
    """Render the hypotheses tracking page."""
    st.markdown(
        page_header("Hypotheses", "Active experiments & concluded findings"),
        unsafe_allow_html=True,
    )

    hypotheses = load_active_hypotheses()
    concluded = load_concluded_hypotheses()

    if not hypotheses and not concluded:
        st.info(
            "No hypotheses yet. Run `/backtest-hypothesis \"<description>\"` to start an experiment."
        )
        return

    # ── Active experiments ────────────────────────────────────────────────────
    running = [h for h in hypotheses if h["status"] == "running"]
    pending = [h for h in hypotheses if h["status"] == "pending"]

    st.markdown(
        f'<div class="section-title">Active Experiments '
        f'<span class="accent">// {len(running)} running, {len(pending)} pending</span></div>',
        unsafe_allow_html=True,
    )

    if running or pending:
        active_rows = []
        for h in sorted(running + pending, key=lambda x: -x.get("priority", 0)):
            days_left = days_until_ready(h)
            ready_str = "concluding soon" if days_left == 0 else f"{days_left}d left"
            status_color = COLORS["green"] if h["status"] == "running" else COLORS["amber"]
            active_rows.append({
                "ID": h["id"],
                "Title": h.get("title", "—"),
                "Scanner": h.get("scanner", "—"),
                "Status": h["status"],
                "Progress": f"{h.get('days_elapsed', 0)}/{h.get('min_days', 14)}d",
                "Picks": len(h.get("picks_log", [])),
                "Ready": ready_str,
                "Priority": h.get("priority", "—"),
            })

        import pandas as pd
        df = pd.DataFrame(active_rows)
        st.dataframe(
            df,
            width="stretch",
            hide_index=True,
            column_config={
                "ID": st.column_config.TextColumn(width="medium"),
                "Title": st.column_config.TextColumn(width="large"),
                "Scanner": st.column_config.TextColumn(width="medium"),
                "Status": st.column_config.TextColumn(width="small"),
                "Progress": st.column_config.TextColumn(width="small"),
                "Picks": st.column_config.NumberColumn(format="%d", width="small"),
                "Ready": st.column_config.TextColumn(width="medium"),
                "Priority": st.column_config.NumberColumn(format="%d/9", width="small"),
            },
        )
    else:
        st.info("No active experiments.")

    st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)

    # ── Concluded experiments ─────────────────────────────────────────────────
    st.markdown(
        f'<div class="section-title">Concluded Experiments '
        f'<span class="accent">// {len(concluded)} total</span></div>',
        unsafe_allow_html=True,
    )

    if concluded:
        import pandas as pd
        concluded_rows = []
        for c in concluded:
            outcome = c["outcome"]
            emoji = "✅" if "accepted" in outcome else "❌"
            concluded_rows.append({
                "Date": c["filename"][:10],
                "Title": c["title"],
                "Scanner": c["scanner"],
                "Period": c["period"],
                "Outcome": emoji,
            })
        cdf = pd.DataFrame(concluded_rows)
        st.dataframe(
            cdf,
            width="stretch",
            hide_index=True,
            column_config={
                "Date": st.column_config.TextColumn(width="small"),
                "Title": st.column_config.TextColumn(width="large"),
                "Scanner": st.column_config.TextColumn(width="medium"),
                "Period": st.column_config.TextColumn(width="medium"),
                "Outcome": st.column_config.TextColumn(width="small"),
            },
        )
    else:
        st.info("No concluded experiments yet.")
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_hypotheses_page.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Register the page in `tradingagents/ui/pages/__init__.py`**

Add after the `settings` import block (around line 38):

```python
try:
    from tradingagents.ui.pages import hypotheses
except Exception as _e:
    _logger.error("Failed to import hypotheses page: %s", _e, exc_info=True)
    hypotheses = None
```

And add `"hypotheses"` to `__all__`:

```python
__all__ = [
    "home",
    "todays_picks",
    "portfolio",
    "performance",
    "settings",
    "hypotheses",
]
```

- [ ] **Step 6: Add "Hypotheses" to dashboard navigation in `tradingagents/ui/dashboard.py`**

In `render_sidebar`, change the `options` list:

```python
page = st.radio(
    "Navigation",
    options=["Overview", "Signals", "Portfolio", "Performance", "Hypotheses", "Config"],
    label_visibility="collapsed",
)
```

In `route_page`, add to `page_map`:

```python
page_map = {
    "Overview": pages.home,
    "Signals": pages.todays_picks,
    "Portfolio": pages.portfolio,
    "Performance": pages.performance,
    "Hypotheses": pages.hypotheses,
    "Config": pages.settings,
}
```

- [ ] **Step 7: Run the full test suite**

```bash
python -m pytest tests/test_compare_hypothesis.py tests/test_hypotheses_page.py -v
```

Expected: all 16 tests pass.

- [ ] **Step 8: Commit everything**

```bash
git add \
  tradingagents/ui/pages/hypotheses.py \
  tradingagents/ui/pages/__init__.py \
  tradingagents/ui/dashboard.py \
  tests/test_hypotheses_page.py
git commit -m "feat(hypotheses): add Hypotheses dashboard tab"
```

---

## Self-Review

**Spec coverage check:**
- ✅ `active.json` schema with `status: running/pending/concluded` — Task 1
- ✅ `/backtest-hypothesis` command: classify, priority scoring, pending queue, branch creation — Task 3
- ✅ Running experiments never paused — enforced in `run_hypothesis_runner.py` (only `running` entries processed; new ones queue as `pending`)
- ✅ Daily runner: worktree per hypothesis, run discovery, commit picks, conclude — Task 4
- ✅ Statistical comparison with 5pp / 1% thresholds, minimum 5 evaluated picks — Task 2
- ✅ Auto-promote pending → running when slot opens — `promote_pending()` in runner
- ✅ Concluded doc written with metrics table — `conclude_hypothesis()` in runner
- ✅ PR merged (accepted) or closed (rejected) automatically — `conclude_hypothesis()`
- ✅ Dashboard tab with active + concluded tables — Task 5

**Type/name consistency:**
- `hypothesis_id` / `hid` / `id` field: the dict key is always `"id"`, the local var is `hid`, the argument is `--hypothesis-id` — consistent throughout
- `picks.json` structure: `{"hypothesis_id": ..., "scanner": ..., "picks": [...]}` — used in `save_picks_to_worktree` and `load_picks_from_branch` consistently
- `strategy_match` field used to filter picks in `extract_picks` — matches `discovery_result.json` structure confirmed by inspection
