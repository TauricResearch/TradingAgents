# Hypothesis Backtesting System — Design Spec

## Goal

Enable systematic, branch-per-hypothesis experimentation for scanner improvements. Each hypothesis runs its modified code daily in isolation, accumulates picks, and auto-concludes with a statistical comparison once enough data exists. Up to 5 experiments run in parallel, prioritized by expected impact, with full UI visibility.

---

## Architecture

```
docs/iterations/hypotheses/
  active.json                              ← source of truth for all experiments
  concluded/
    YYYY-MM-DD-<id>.md                     ← one file per concluded hypothesis

.claude/commands/
  backtest-hypothesis.md                   ← /backtest-hypothesis command

.github/workflows/
  hypothesis-runner.yml                    ← daily 08:00 UTC, runs all active experiments

tradingagents/ui/pages/
  hypotheses.py                            ← new Streamlit dashboard tab
```

The `active.json` file lives on `main`. Each hypothesis branch (`hypothesis/<scanner>-<slug>`) contains the code change being tested. The daily runner checks out each branch, runs discovery, commits picks back to that branch, and — once `min_days` have elapsed — concludes the hypothesis and cleans up.

---

## `active.json` Schema

```json
{
  "max_active": 5,
  "hypotheses": [
    {
      "id": "options_flow-scan-3-expirations",
      "scanner": "options_flow",
      "title": "Scan 3 expirations instead of 1",
      "description": "Hypothesis: scanning up to 3 expirations captures institutional positioning in 30+ DTE contracts, improving signal quality over nearest-expiry-only.",
      "branch": "hypothesis/options_flow-scan-3-expirations",
      "pr_number": 14,
      "status": "running",
      "priority": 8,
      "expected_impact": "high",
      "hypothesis_type": "implementation",
      "created_at": "2026-04-09",
      "min_days": 14,
      "days_elapsed": 3,
      "picks_log": ["2026-04-09", "2026-04-10", "2026-04-11"],
      "baseline_scanner": "options_flow",
      "conclusion": null
    }
  ]
}
```

**Field reference:**

| Field | Description |
|---|---|
| `id` | `<scanner>-<slug>` — unique, used for branch and file names |
| `status` | `running` / `paused` / `concluded` |
| `priority` | 1–10 (higher = more important); auto-pause lowest when at capacity |
| `hypothesis_type` | `statistical` (answer from existing data) or `implementation` (requires branch + forward testing) |
| `min_days` | Minimum picks days before conclusion analysis runs |
| `picks_log` | Dates when the runner collected picks on this branch |
| `conclusion` | `null` while running; `"accepted"` or `"rejected"` once concluded |

---

## `/backtest-hypothesis` Command

**Trigger:** `claude /backtest-hypothesis "<description>"`

**Flow:**

1. **Classify** the hypothesis as `statistical` or `implementation`.
   - Statistical: answerable from existing `performance_database.json` data — no code change needed.
   - Implementation: requires a code change and forward-testing period.

2. **Statistical path:** Run the analysis immediately against existing performance data. Write conclusion to the relevant scanner domain file (`docs/iterations/scanners/<scanner>.md`). Done — no branch created.

3. **Implementation path:**
   a. Read `active.json`. If `running` count < 5, proceed. If at 5, auto-pause the entry with the lowest `priority` (set `status: "paused"`, keep branch alive).
   b. Create branch `hypothesis/<scanner>-<slug>` from `main`.
   c. Implement the minimal code change on the branch.
   d. Open a draft PR: title `hypothesis(<scanner>): <title>`, body describes the hypothesis, expected impact, and `min_days`.
   e. Write new entry to `active.json` on `main` with `status: "running"`.
   f. Print summary: branch name, PR number, expected conclusion date.

**Priority scoring** (set at creation time):

| Factor | Score contribution |
|---|---|
| Scanner has poor 30d win rate (<40%) | +3 |
| Change is low-complexity (1 file, 1 parameter) | +2 |
| Hypothesis directly addresses a known weak spot in LEARNINGS.md | +2 |
| High daily pick volume from scanner (more data faster) | +1 |
| Evidence from external research (arXiv, Alpha Architect, etc.) | +1 |
| Conflicting evidence or uncertain direction | -2 |

Max score 9. Claude assigns this score and writes it to `active.json`.

---

## Daily Hypothesis Runner (`hypothesis-runner.yml`)

Runs at **08:00 UTC daily** (after iterate at 06:00 UTC).

**Per-hypothesis loop** (for each entry with `status: "running"`):

```
1. git checkout hypothesis/<id>
2. Run daily discovery pipeline (same as daily-discovery.yml)
3. Append today's date to picks_log
4. Commit picks update back to hypothesis branch
5. If days_elapsed >= min_days:
   a. Run statistical comparison vs baseline scanner (same scanner, main branch picks)
   b. Compute: win rate delta, avg return delta, pick volume delta, p-value if N >= 20
   c. Decision rule:
      - accepted if win rate delta > +5pp OR avg return delta > +1% (with p < 0.1 if N >= 20)
      - rejected otherwise
   d. Write concluded doc to docs/iterations/hypotheses/concluded/YYYY-MM-DD-<id>.md
   e. Update scanner domain file with finding
   f. Set status = "concluded", conclusion = "accepted"/"rejected" in active.json
   g. If accepted: merge PR into main
      If rejected: close PR without merging, delete hypothesis branch
   h. Push active.json update to main
```

**Capacity:** 5 experiments × ~2 min each = ~10 min max runtime. Workflow timeout: 60 minutes.

---

## Conclusion Document Format

`docs/iterations/hypotheses/concluded/YYYY-MM-DD-<id>.md`:

```markdown
# Hypothesis: <title>

**Scanner:** options_flow
**Branch:** hypothesis/options_flow-scan-3-expirations
**Period:** 2026-04-09 → 2026-04-23 (14 days)
**Outcome:** accepted ✅ / rejected ❌

## Hypothesis
<original description>

## Results

| Metric | Baseline | Experiment | Delta |
|---|---|---|---|
| 7d win rate | 42% | 53% | +11pp |
| 30d avg return | -2.9% | +0.8% | +3.7% |
| Picks/day | 1.2 | 1.8 | +0.6 |

## Decision
<1-2 sentences on why accepted/rejected>

## Action
<what was merged or discarded>
```

---

## Dashboard Tab (`tradingagents/ui/pages/hypotheses.py`)

New "Hypotheses" tab in the Streamlit dashboard.

**Active experiments table:**

| Hypothesis | Scanner | Status | Days | Picks | Expected Ready | Priority |
|---|---|---|---|---|---|---|
| Scan 3 expirations | options_flow | running | 3/14 | 4 | 2026-04-23 | 8 |
| ITM-only filter | options_flow | paused | 1/14 | 1 | — | 5 |

**Concluded experiments table:**

| Hypothesis | Scanner | Outcome | Concluded | Win Rate Delta |
|---|---|---|---|---|
| Premium filter >$25K | options_flow | ✅ merged | 2026-04-01 | +9pp |
| Reddit DD confidence gate | reddit_dd | ❌ rejected | 2026-03-20 | -3pp |

Both tables read directly from `active.json` and the `concluded/` directory. No separate database.

---

## What Is Not In Scope

- Hypothesis branches do not interact with each other (no cross-branch comparison)
- No A/B testing within a single discovery run (too complex, not needed)
- No email/Slack notifications (rolling PRs in GitHub are the notification mechanism)
- No manual override of priority scoring (set at creation, editable directly in `active.json`)
