# Plan: Fix Pre-existing Test Failures

**Status**: complete
**Branch**: claude/objective-galileo
**Principle**: Tests that fail due to API rate limits are OK to fail — but they must state WHY. Never skip or artificially pass. Fix real bugs only.

## Failures to Fix (12 total, 5 test files)

---

### 1. `tests/test_config_wiring.py` — 4 tests

**Root cause**: `callable()` returns `False` on LangChain `StructuredTool` objects. The `@tool` decorator creates a `StructuredTool` instance, not a plain function.

**Failing lines**: 28, 32, 36, 40 — all `assert callable(X)`

**Fix**: Replace `assert callable(X)` with `assert hasattr(X, "invoke")` — this is the correct way to check LangChain tools are invocable.

```python
# BEFORE (broken)
assert callable(get_ttm_analysis)

# AFTER (correct)
assert hasattr(get_ttm_analysis, "invoke")
```

- [x] Fix line 28: `get_ttm_analysis`
- [x] Fix line 32: `get_peer_comparison`
- [x] Fix line 36: `get_sector_relative`
- [x] Fix line 40: `get_macro_regime`

---

### 2. `tests/test_env_override.py` — 2 tests

**Root cause**: `importlib.reload()` re-runs `load_dotenv()` which reads `TRADINGAGENTS_*` vars from the user's `.env` file even after stripping them from `os.environ`. `patch.dict(clear=True)` removes the keys but doesn't prevent `load_dotenv()` from re-injecting them.

**Failing tests**:
- `test_mid_think_llm_none_by_default` (line ~40-46) — expects `None`, gets `qwen/qwq-32b`
- `test_defaults_unchanged_when_no_env_set` (line ~96-108) — expects `gpt-5.2`, gets `deepseek/deepseek-r1-0528`

**Fix**: Build a clean env dict (strip `TRADINGAGENTS_*` vars) AND patch `dotenv.load_dotenv` to prevent `.env` re-reads during module reload.

```python
# Pattern for proper isolation
env_clean = {k: v for k, v in os.environ.items() if not k.startswith("TRADINGAGENTS_")}
with patch.dict(os.environ, env_clean, clear=True):
    with patch("dotenv.load_dotenv"):
        cfg = self._reload_config()
        assert cfg["mid_think_llm"] is None
```

- [x] Fix `test_mid_think_llm_none_by_default` — clean env + mock load_dotenv
- [x] Fix `test_defaults_unchanged_when_no_env_set` — add mock load_dotenv (already had clean env)
- [x] Audit other tests in the file — remaining tests use explicit env overrides, not affected

---

### 3. `tests/test_scanner_comprehensive.py` — 1 test

**Root cause**: Two bugs in `test_scan_command_creates_output_files`:
1. Wrong filenames (`market_movers.txt` etc.) — scanner saves `{key}.md` (e.g. `market_movers_report.md`)
2. Wrong path format — `str(test_date_dir / filename)` produces absolute paths, but `written_files` keys are relative (matching what `Path("results/macro_scan") / date / key` produces)

**Failing test**: `test_scan_command_creates_output_files` (line ~119)

**Fix**: Update filenames and use relative path keys:

```python
# AFTER (correct)
expected_files = [
    "geopolitical_report.md",
    "market_movers_report.md",
    "sector_performance_report.md",
    "industry_deep_dive_report.md",
    "macro_scan_summary.md",
]
for filename in expected_files:
    filepath = f"results/macro_scan/2026-03-15/{filename}"
    assert filepath in written_files, ...
```

- [x] Update expected filenames to match actual scanner output
- [x] Fix filepath key to use relative format matching run_scan() output
- [x] Remove format-specific content assertions (content is LLM-generated, not tool output)

---

### 4. `tests/test_scanner_fallback.py` — 2 tests

**Root cause**: Tests call `get_sector_performance_alpha_vantage()` and `get_industry_performance_alpha_vantage()` WITHOUT mocking, making real API calls. They expect ALL calls to fail and raise `AlphaVantageError`, but real API calls intermittently succeed.

**Failing tests**:
- `test_sector_perf_raises_on_total_failure` (line ~85)
- `test_industry_perf_raises_on_total_failure` (line ~90)

**Fix**: Mock `_fetch_global_quote` to simulate total failure:

```python
with patch(
    "tradingagents.dataflows.alpha_vantage_scanner._fetch_global_quote",
    side_effect=AlphaVantageError("Rate limit exceeded — mocked for test isolation"),
):
    with pytest.raises(AlphaVantageError, match="All .* sector queries failed"):
        get_sector_performance_alpha_vantage()
```

- [x] Mock `_fetch_global_quote` in `test_sector_perf_raises_on_total_failure`
- [x] Mock `_fetch_global_quote` in `test_industry_perf_raises_on_total_failure`
- [x] No `@pytest.mark.integration` to remove — class had no marker

---

### 5. `tests/test_scanner_graph.py` — 3 tests

**Root cause**: Tests import `MacroScannerGraph` but class was renamed to `ScannerGraph`. Third test uses `ScannerGraphSetup` but with wrong constructor args (no `agents` provided).

**Failing tests**:
- `test_scanner_graph_import` — `ImportError: cannot import name 'MacroScannerGraph'`
- `test_scanner_graph_instantiates` — same import error
- `test_scanner_setup_compiles_graph` — `TypeError: ScannerGraphSetup.__init__() missing 1 required positional argument: 'agents'`

**Fix**: Rename import, mock `_create_llm` for instantiation test, provide `mock_agents` dict:

```python
from unittest.mock import MagicMock, patch
from tradingagents.graph.scanner_graph import ScannerGraph

with patch.object(ScannerGraph, "_create_llm", return_value=MagicMock()):
    scanner = ScannerGraph()  # compiles real graph with mock LLMs
```

- [x] Fix import: `MacroScannerGraph` → `ScannerGraph`
- [x] Mock `_create_llm` to avoid real LLM init in instantiation test
- [x] Provide `mock_agents` dict to `ScannerGraphSetup` — compiles real wiring logic

---

## Verification

- [x] Run `pytest tests/test_config_wiring.py -v` — all 4 previously failing tests pass
- [x] Run `pytest tests/test_env_override.py -v` — all 2 previously failing tests pass
- [x] Run `pytest tests/test_scanner_fallback.py -v` — all 2 previously failing tests pass
- [x] Run `pytest tests/test_scanner_graph.py -v` — all 3 previously failing tests pass
- [x] Run `python -m pytest tests/test_scanner_comprehensive.py -v` — 1 previously failing test passes (482s, real LLM)
- [x] Run full offline suite: `python -m pytest tests/ -v -m "not integration"` — 388 passed, 70 deselected, 0 failures (512s)
- [x] API-dependent tests that fail due to rate limits include clear WHY in mock side_effect message

**Note**: Must use `python -m pytest` (not bare `pytest`) in this worktree. The editable install in `site-packages` maps `tradingagents` to the main repo. `python -m pytest` adds CWD to `sys.path`, making the worktree's `tradingagents` visible first.

## Files Changed

| File | Change |
|---|---|
| `tests/test_config_wiring.py` | `callable()` → `hasattr(x, "invoke")` |
| `tests/test_env_override.py` | Clean env + `patch("dotenv.load_dotenv")` to block .env re-reads |
| `tests/test_scanner_comprehensive.py` | Fix filenames + path format; remove format-specific content assertions |
| `tests/test_scanner_fallback.py` | Mock `_fetch_global_quote` instead of making real API calls |
| `tests/test_scanner_graph.py` | `MacroScannerGraph` → `ScannerGraph`; mock `_create_llm`; provide `mock_agents` |
