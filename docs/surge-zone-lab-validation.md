# Local validation — 2026-11-08

## Reference-card increment (latest)

Both two-page source cards (version 20260501) were visually reviewed, and temporary
copies/renders were removed after inspection. Added pattern-specific distal spans,
separate boundary/detector versions, all six evidence-driven score bands, explicit
partial totals, and a dashboard component scorecard. No automatic context inference
or full-score claims were added. See [rule mapping](surge-reference-rules.md).

- Targeted suite: **93 passed in 12.27 seconds**.
- Full suite: **1500 passed, 6 skipped, 1 deselected, 24 warnings,
  100 subtests passed in 61.06 seconds**, using `pytest -q --disable-warnings`.
- Full-repository Ruff, formatting of changed Python files, ty for Surge/provider,
  `pip check`, and `git diff --check` passed.
- Temporary localhost server loaded with agent API `status: ready`; its initial
  warning correctly describes card formulas and Time-only automatic scoring.
  Console showed no new warnings/tracebacks. Scorecard/chart/replay interactions
  passed mocked AppTest. No paid EODHD request or browser visual inspection.

The 52 additional cases cover pattern-specific multi-candle boundary spans and all
score bands, inclusive thresholds, half points, missing/inconsistent evidence,
fresh-opposing-zone requirements, and complete-only entry guidance. The original
workflows remain unchanged. Earlier validation is retained below as a dated record.

## Initial vertical slice

Branch: `feature/surge-zone-lab`. Windows, Python 3.11.9, pandas 3.1.1,
Streamlit 1.67.0, Plotly 7.1.0, exchange-calendars 4.13.2, pytest 9.2.0,
Ruff 0.17.4, ty 0.0.99. Dependencies installed into the ignored project `.venv`.

Final command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --disable-warnings
```

Result: **1448 passed, 6 skipped, 1 deselected, 24 warnings,
100 subtests passed in 62.22 seconds.** Includes all 41 new Surge cases. Five
skips concern POSIX-specific behavior on Windows; one is optional Bedrock SDK
availability. The integration marker is excluded by repository defaults.
Warnings concern existing provider/model tests. No paid API requests were made.

Additional checks passed:

- `python -m ruff check .` — full repository.
- `python -m ruff format --check` — all nine new Python files.
- `python -m ty check tradingagents/surge tradingagents/dataflows/vendors/eodhd.py`.
- `python -m pip check` — no broken requirements.
- `git diff --check` and Python compilation of new modules/tests.

Tests cover all four labels, experimental boundaries, base count/thresholds,
departure measurements, BOS/FVG, prefix/cutoff invariance, missing-data and
adjustment discontinuities, invalid inputs, daily normalization, DST/holiday/early
closes, incomplete bars, caching/TTL/refresh, vendor denial and credential-safe
errors, mocked provider → detector → Plotly flow, and dashboard scan/replay/failure
behavior. Windows AppTest permits the standard library's internal socketpair
construction while application network access stays blocked.

A temporary Streamlit server on `127.0.0.1:8765` passed health and agent API
initial-load checks (`status: ready`). Submitting an invalid ticker rendered a
validation error with no API call or uncaught exception. Console output had no
new warnings or tracebacks. The server was stopped, and no listener remained.
Chart objects and chart-producing dashboard interactions were tested headlessly;
browser-rendered appearance has not been visually inspected.

No live EODHD contract/entitlement test was performed. These results validate the
first daily experimental slice only, not official Surge rules, historical trade
outcomes, point-in-time corporate actions, ML quality, or any profitability claim.
No merge, commit, deployment, or original agent workflow change was performed.
