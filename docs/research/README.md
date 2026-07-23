# Institutional Backtesting Research & Design Program

Research package: study verified elite traders, mine recurring patterns, benchmark backtesting frameworks, and design the evolution of `tradingagents/pro/backtest` — documents + machine-readable data only; implementation follows in later sessions per [13_roadmap.md](13_roadmap.md).

Everything here obeys the honesty contract in [00_methodology.md](00_methodology.md): sourced facts only, null = not disclosed, N printed with every statistic, verification tiers visible everywhere, caution flags never laundered.

## Deliverable map & status

| # | Deliverable | File(s) | Status |
|---|---|---|---|
| — | Methodology & research protocol | [00_methodology.md](00_methodology.md) | **done (S1)** |
| — | Profile schema + vocabularies | [data/traders.schema.json](data/traders.schema.json), [data/vocabularies.json](data/vocabularies.json) v1.0.0 | **done (S1)** — awaiting operator approval |
| — | Cohort rosters (8 cohorts, ~155 candidates) | [data/cohorts.md](data/cohorts.md) | **done (S1)** — awaiting operator approval |
| — | Validator / exporter / miner | [data/analyze_traders.py](data/analyze_traders.py) | **done (S1)** |
| 1 | Trader knowledge base (JSON + CSV) | [data/traders.json](data/traders.json), data/traders.csv | **FROZEN — 146 profiles** (all 8 cohorts; 22 A / 96 B / 28 C; 5 candidates dropped as unverifiable) |
| 2 | Statistical analysis (honest Ns) | [01_trader_statistics.md](01_trader_statistics.md) + data/derived/ | **done (S4)** |
| 3 | Pattern report (recurring combinations) | [02_pattern_report.md](02_pattern_report.md) | **done (S4)** |
| 4 | Institutional best-practices report | [03_institutional_best_practices.md](03_institutional_best_practices.md) | **done (S4)** |
| 5 | Framework comparison matrix | [04_framework_comparison.md](04_framework_comparison.md), [data/frameworks.csv](data/frameworks.csv) | **done (S5)** |
| 6 | Gap analysis (TradingView + best-in-class vs ours) | [05_gap_analysis.md](05_gap_analysis.md) | **done (S5)** |
| 7 | HLD / LLD (evolve-in-place, six tracks) | 06_hld.md, 07_lld.md | pending (S6) |
| 8 | Data/artifact schema deltas | 08_data_schema.md | pending (S6) |
| 9 | API specification | 09_api_spec.md | pending (S6) |
| 10 | Strategy SDK design | 10_strategy_sdk.md | pending (S6) |
| 11 | Performance recommendations | 11_performance_recommendations.md | pending (S7) |
| 12 | Validation methodology (anti-overfit / look-ahead) | 12_validation_methodology.md | pending (S6) |
| 13 | Implementation roadmap | 13_roadmap.md | pending (S7) |
| 14 | Prioritized backlog with estimates | 14_backlog.md | pending (S7) |
| 15 | Final recommendation | 15_final_recommendation.md | pending (S7) |

## Session plan (checkpoints in bold)

| Session | Work | Checkpoint |
|---|---|---|
| S1 ✅ | Scaffolding: methodology, schema, vocabularies, rosters, tooling | **Approve schema + vocabularies + rosters** |
| S2 ✅ | Research cohorts C1–C3 → 68 profiles merged (B1: 30, B2: 20, B3: 18), QA'd | Sample-check 5 profiles |
| S3 ✅ | Research C4–C8 → KB frozen at 146 (waves A+B), full dedup + tier audit | **KB freeze**; review missing-data report |
| S4 ✅ | Pattern mining → derived/ → deliverables 2–4 written | Veto pseudo-precision |
| S5 ✅ | Framework desk study (10 frameworks + ours) → deliverables 5–6 | Confirm gap priorities |
| S6 | Architecture → deliverables 7–10, 12 | **Design review** |
| S7 | Deliverables 11, 13–15; wrap | Final sign-off |

## Commands

```bash
# validate the KB (and optional un-merged batch files)
python docs/research/data/analyze_traders.py --validate [batch.json ...]

# regenerate traders.csv from the canonical JSON
python docs/research/data/analyze_traders.py --export-csv

# regenerate every table in data/derived/ (frequency / numeric / co-occurrence /
# missing-data; all-tiers + tier-A/B variants)
python docs/research/data/analyze_traders.py --analyze
```

`data/derived/` outputs are committed so the statistics docs stay auditable without re-running anything; regenerate before citing them.
