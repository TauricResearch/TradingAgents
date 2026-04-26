# Live Integration Testing Strategy

Related operational guide:
- [Node-by-Node Terminal Testing Guide](/Users/Ahmet/Repo/TradingAgents/docs/testing/node-by-node-terminal-guide.md)

## Scope
This strategy covers the recent reliability changes around:
- Smart-money scanner provenance metadata (`Source`, `Scan Date`, canonical citation block)
- Source-name validation and scanner/SEC attribution separation
- SQLite-backed evidence IDs injected into news prompts
- Post-generation `News Fact Checker` provenance enforcement
- Fail-closed news behavior (retry once, then structured `abort_signal`) and graph routing

## Execution Policy
- Live integration tests are strictly opt-in.
- They must only run when explicitly invoked via:
  - `scripts/run_live_validation_tests.sh --suite ...`
- The runner does not default to any suite; `--suite` is required.

## Test Tiers
1. Unit (deterministic, no network)
- Purpose: validate parsing, validation rules, retry logic, and abort routing deterministically.
- Required in every PR:
  - `tests/unit/test_output_validation.py`
  - `tests/unit/test_context_filtering.py`
  - `tests/unit/agents/test_analyst_agents.py`
  - `tests/unit/test_fast_reject.py`

2. Integration (internal wiring, mostly deterministic)
- Purpose: validate component wiring and graph behavior with realistic state transitions.
- Required in every PR:
  - `tests/unit/test_instruments.py`
  - `tests/unit/test_graph_setup_llm_assignment.py`
  - `tests/unit/test_ground_truth_propagation.py`

3. Live Integration (real external services)
- Purpose: detect production regressions in external data paths used by scanner/news context.
- Run in CI nightly and before release cut.
- Note: the opt-in live `News Analyst` regression remains a manual targeted run,
  not a default CI gate, because it depends on a real LLM provider and prompt
  determinism rather than only data-path stability.

## Live Test Matrix
### Suite: `core` (no API keys required)
- `tests/integration/test_market_prices_live.py`
  - Gate: all tests pass.
- `tests/integration/test_gatekeeper_live.py`
  - Gate: pass or explicit `pytest.skip` for no matching live rows.
- `tests/integration/test_finviz_live.py`
  - Gate: pass; if `finvizfinance` missing, runner fails fast.

### Optional live macro suite (outside provenance gate)
- `tests/integration/test_sovereign_cds_live.py`
  - Gate: pass or explicit `pytest.skip` for stale same-day snapshot.
  - Note: keep this outside the provenance/source-validation gate because it validates geopolitical scanner tool wiring, not smart-money/news attribution.

### Optional targeted LLM provenance check
- `tests/integration/test_news_analyst_live.py`
  - Gate: manual/opt-in only.
  - Purpose: replay a reduced production payload against a live model and verify
    the response avoids fake source labels such as `Macro Regime Classification`.
  - Run when changing prompt wording, provenance instructions, or validator rules.

### Suite: `alpha-vantage` (requires `ALPHA_VANTAGE_API_KEY`)
- `tests/integration/test_alpha_vantage_live.py`
  - Gate: pass.
- `tests/integration/test_scanner_context_filtering_live.py`
  - Gate: pass; if no recent articles, skip accepted where test explicitly skips.

### Suite: `full`
- Runs `core` + `alpha-vantage`.
- Optional extension:
  - `tests/integration/test_finnhub_live.py` when `FINNHUB_API_KEY` is configured.
  - Gate: pass for non-paid-tier tests; paid-tier tests may skip.

## Pass/Fail Gates
1. PR gate (required):
- all unit and integration commands above pass.
- optional smoke live run (`core`) for high-risk scanner changes.

2. Nightly gate (required):
- `scripts/run_live_validation_tests.sh --suite full` passes.
- Any hard failure in live suite blocks release branch promotion.

3. Release gate (required):
- rerun `full` suite within 24 hours of release cut.

## Prerequisites and Environment
- Python dependencies installed from project requirements.
- Network access enabled for live suites.
- `pytest-socket` is enabled globally via project defaults; live runs must pass an explicit host allowlist.
- Environment variables:
  - `ALPHA_VANTAGE_API_KEY` for `alpha-vantage` and `full` suites.
    - Optional fallback: pass `--allow-demo-av` to intentionally run with `demo` key when the env var is not set.
  - `FINNHUB_API_KEY` optional for Finnhub extension.
  - Optional `LIVE_ALLOW_HOSTS` to override default host allowlist used by the runner.
  - Optional `PYTEST_TIMEOUT_SEC` to cap per-module runtime during live runs.
- Python package:
  - `finvizfinance` required by Finviz live tests.

## Artifact and Response Recording
The live test runner writes timestamped artifacts under:
- `artifacts/live-tests/<UTC_TIMESTAMP>/`

Artifacts produced:
- `run_metadata.txt` (suite, git sha, python version, host env flags)
- `<module>.log` (stdout/stderr test response stream)
- `<module>.junit.xml` (machine-readable pass/fail report)
- `summary.tsv` (module, status, return code)

This preserves raw test responses and machine-readable results for debugging and trend tracking.

Runner examples:
- `scripts/run_live_validation_tests.sh --suite core`
- `scripts/run_live_validation_tests.sh --suite alpha-vantage --allow-demo-av`
- `scripts/run_live_validation_tests.sh --suite core --module tests/integration/test_market_prices_live.py`

## Rollout Cadence
1. Every PR:
- required unit + integration tiers.

2. Nightly:
- run `full` live suite and retain artifacts for 14 days minimum.

3. Weekly QA review:
- inspect failure trends by module from `summary.tsv` and JUnit history.
- classify failures as: data-staleness skip, transient vendor error, regression.

## Operational Notes
- Live tests are expected to have occasional skip outcomes due to market closures, stale snapshots, or empty live result sets; these are acceptable only when tests explicitly skip with reason.
- Unknown-source or scanner/SEC conflation coverage remains deterministic in unit tests by design; live tests validate upstream data path stability, not LLM determinism.
- The primary provenance gate for PRs remains unit/integration coverage. The live
  news-analyst test is a targeted diagnostic, not a stable PR gate.
