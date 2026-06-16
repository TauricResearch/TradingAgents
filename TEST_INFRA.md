# E2E Test Infra: Autonomous Continuous Trading Analyst MVP

## Test Philosophy
- Opaque-box, requirement-driven. No dependency on implementation design.
- Methodology: Category-Partition + BVA + Pairwise + Workload Testing.

## Feature Inventory
| # | Feature | Source (requirement) | Tier 1 | Tier 2 | Tier 3 |
|---|---------|---------------------|:------:|:------:|:------:|
| 1 | Core CLI & Event Loop | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 2 | Market Scanning | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| 3 | Memory & Risk Tracking | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ |
| 4 | Reporting System | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ |

## Test Architecture
- Test runner: `pytest`
- Test case format: Pytest functions with parameterization, structured assertion on outputs, mock LLM interactions, isolated configs.
- Directory layout:
  - `tests/test_continuous_e2e.py` (contains the E2E tests).

## Feature Case Index

### Tier 1: Feature Coverage (20 tests)
1. `test_cli_args_parsing`: Verify CLI parser accepts `--watch`, `--interval-minutes`, `--watchlist`, `--max-candidates`.
2. `test_run_watch_loop_cycles`: Verify `run_watch_loop` executes at least 2 cycles and stops when queue/cycles limit is reached.
3. `test_watchlist_parsing_formats`: Verify watchlist parses comma-separated lists correctly.
4. `test_max_candidates_filter`: Verify candidates are limited to `--max-candidates` count.
5. `test_loop_termination_on_signal`: Verify the event loop terminates cleanly when stop signal is set.
6. `test_market_watcher_fetch_snapshots`: Verify `MarketWatcher.fetch_snapshots` returns correct dictionaries for tickers and benchmark SPY.
7. `test_opportunity_scanner_scoring`: Verify `OpportunityScanner.score_candidates` returns candidates with numerical scores.
8. `test_opportunity_scanner_sorting`: Verify candidates are returned sorted by score descending.
9. `test_opportunity_scanner_empty_watchlist`: Verify scanner returns empty list if snapshots dictionary is empty.
10. `test_market_watcher_benchmark_only`: Verify SPY benchmark snapshot is fetched even if the watchlist itself is empty.
11. `test_portfolio_memory_initialization`: Verify `PortfolioMemory` starts with $10,000 cash balance.
12. `test_portfolio_memory_update`: Verify memory updates cash and positions after simulating a trade.
13. `test_portfolio_memory_performance_review`: Verify performance review calculates ROI of previous recommendations.
14. `test_risk_guard_assessment`: Verify `RiskGuard.assess_risk` evaluates and returns safe/watch/risky labels.
15. `test_portfolio_memory_json_snapshots`: Verify portfolio snapshots are correctly saved/loaded in JSON/JSONL format.
16. `test_report_writer_watch_log`: Verify `ReportWriter` appends records to `watch_log.jsonl`.
17. `test_report_writer_opportunities_log`: Verify `ReportWriter` appends records to `opportunities.jsonl`.
18. `test_report_writer_decisions_log`: Verify `ReportWriter` appends records to `decisions.jsonl`.
19. `test_report_writer_summary_generation`: Verify `ReportWriter` generates the `daily_summary.md` file.
20. `test_report_writer_summary_contents`: Verify `daily_summary.md` contains scanned tickers, risk flags, and portfolio balance.

### Tier 2: Boundary & Corner Cases (20 tests)
21. `test_cli_negative_interval`: Verify negative or zero interval throws value error.
22. `test_cli_invalid_watchlist_format`: Verify malformed watchlist strings are handled gracefully.
23. `test_cli_negative_max_candidates`: Verify negative `max-candidates` is handled.
24. `test_cli_missing_mandatory_args`: Verify CLI returns error code on missing mandatory arguments.
25. `test_loop_resilience_on_temp_failure`: Verify loop continues to next cycle if one cycle fails (e.g. timeout fetching data).
26. `test_market_watcher_nonexistent_ticker`: Verify watcher filters out or handles invalid ticker symbols.
27. `test_opportunity_scanner_negative_price`: Verify scoring logic handles negative/zero prices/volumes without crashing.
28. `test_opportunity_scanner_missing_benchmark`: Verify scoring logic uses fallback values if SPY benchmark is missing.
29. `test_opportunity_scanner_extreme_relative_strength`: Verify relative strength score is bounded or doesn't divide by zero when SPY is flat.
30. `test_opportunity_scanner_empty_market_data`: Verify opportunity scanner handles empty market data fields in snapshots.
31. `test_portfolio_insufficient_cash`: Verify paper trading prevents purchases exceeding cash (margin check).
32. `test_performance_review_no_past_decisions`: Verify performance reviewer returns 0 ROI and empty list if no past decisions.
33. `test_risk_guard_extreme_exposure`: Verify `RiskGuard` flags a ticker as `risky` if it exceeds single-ticker exposure.
34. `test_portfolio_memory_corrupted_snapshot`: Verify portfolio memory resets or handles corrupted JSON files safely.
35. `test_portfolio_memory_rapid_transactions`: Verify portfolio memory consistency under rapid sequential transactions.
36. `test_report_writer_missing_directory`: Verify `ReportWriter` creates the `reports/continuous` folder if it doesn't exist.
37. `test_report_writer_extreme_payload`: Verify logger handles large payloads and special characters.
38. `test_daily_summary_empty_cycles`: Verify `daily_summary.md` is generated with a placeholder when no candidates are scored.
39. `test_log_fields_missing`: Verify JSONL logging doesn't crash when some data fields are null.
40. `test_report_writer_concurrent_writes`: Verify logs are written cleanly under concurrent logging attempts.

### Tier 3: Cross-Feature Combinations (4 tests)
41. `test_scanner_watcher_integration`: Verify `MarketWatcher` snapshots feed directly into `OpportunityScanner` scoring.
42. `test_scoring_memory_integration`: Verify opportunity scores trigger simulated purchases in `PortfolioMemory`.
43. `test_risk_guard_decision_integration`: Verify `RiskGuard` risk rating changes transaction decision in `PortfolioMemory`.
44. `test_full_agent_cycle_integration`: Verify full flow: fetch data -> score -> risk assessment -> decision -> write logs and summary.

### Tier 4: Real-World Application Scenarios (5 tests)
45. `test_scenario_bull_market`: Simulation of a bullish day where tickers score high, risk is safe, buy actions are triggered, and reports log positive trade activity.
46. `test_scenario_market_crash`: Simulation of a crash day where tickers score low/negative, risk guard flags risky, portfolio stays in cash, and report warns of risks.
47. `test_scenario_multi_cycle_trading`: Simulation of 3 continuous cycles where prices fluctuate, memory tracks positions, ROI changes, and daily summary is updated.
48. `test_scenario_missing_benchmark`: Simulation of a run where SPY benchmark fails to load, testing graceful fallback and continuation of trading analysis.
49. `test_scenario_max_candidates_limit`: Simulation where 10 tickers are watched but `max_candidates` is 3, verifying only the top 3 are analyzed and logged.

## Coverage Thresholds
- Tier 1: ≥5 per feature (20 total)
- Tier 2: ≥5 per feature (20 total)
- Tier 3: pairwise coverage of major feature interactions (4 total)
- Tier 4: ≥5 realistic application scenarios (5 total)
