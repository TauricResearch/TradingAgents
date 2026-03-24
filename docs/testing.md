# TradingAgents — Test Suite Reference

> **Last verified:** 2026-03-24  
> **Test counts (current):** 793 passed · 14 skipped (unit+portfolio+cli default run) · 101 integration · 1 e2e

---

## Table of Contents

1. [Overview](#overview)
2. [Three-Tier Architecture](#three-tier-architecture)
3. [Libraries and Tools](#libraries-and-tools)
4. [Fixtures Reference](#fixtures-reference)
5. [Markers Reference](#markers-reference)
6. [Test File Catalogue](#test-file-catalogue)
7. [Execution Flow Diagrams](#execution-flow-diagrams)
8. [How to Run Tests](#how-to-run-tests)
9. [Mock Patterns](#mock-patterns)
10. [What is MagicMock?](#what-is-magicmock)
11. [Adding New Tests — Checklist](#adding-new-tests--checklist)

---

## Overview

The test suite enforces a strict **network isolation** policy: the default `pytest` run
(used in CI) **cannot make any real socket connections**.  Tests that need live APIs are
placed in separate directories and are *excluded from the default run* via `addopts` in
`pyproject.toml`.

```
tests/
├── conftest.py              ← root fixtures (shared across all tiers)
├── unit/                    ← offline, <5 s total, default run
│   ├── conftest.py          ← mock factories (yfinance, AV, LLM)
│   ├── agents/              ← agent-specific unit tests
│   └── test_*.py
├── integration/             ← live APIs, excluded from default run
│   ├── conftest.py          ← VCR config + live key fixtures
│   └── test_*_live.py
├── e2e/                     ← real LLM pipeline, manual only
│   ├── conftest.py
│   └── test_*.py
├── portfolio/               ← portfolio module unit tests (no DB)
│   ├── conftest.py
│   └── test_*.py
├── cli/                     ← CLI module unit tests
│   └── test_*.py
└── cassettes/               ← recorded HTTP responses (VCR)
```

---

## Three-Tier Architecture

| Tier | Directory | Default run? | Network? | Speed | Purpose |
|------|-----------|:---:|:---:|-------|---------|
| **Unit** | `tests/unit/`, `tests/portfolio/`, `tests/cli/` | ✅ yes | ❌ blocked by `pytest-socket` | < 5 s | Validate logic, parsing, routing with mocks |
| **Integration** | `tests/integration/` | ❌ ignored | ✅ real APIs | seconds–minutes | Validate vendor API contracts, live data shapes |
| **E2E** | `tests/e2e/` | ❌ ignored | ✅ real LLM + APIs | minutes | Validate the full multi-agent pipeline |

### Why three tiers?

- **Fast feedback loop** — developers get a pass/fail signal in under 5 seconds on every commit.
- **No flaky CI** — CI never fails due to API rate limits, network timeouts, or key rotation.
- **Live API contract tests** — integration tests confirm the real API shape hasn't drifted from mocks.
- **Full pipeline validation** — e2e tests confirm all agents wire together correctly end-to-end.

---

## Libraries and Tools

### pytest `>=9.0.2`

The test runner.  Key configuration lives in `pyproject.toml` under
`[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--ignore=tests/integration --ignore=tests/e2e --disable-socket --allow-unix-socket -x -q"
markers = [
    "integration: tests that hit real external APIs",
    "e2e: tests that hit real LLM APIs (manual trigger only)",
    "vcr: tests that use VCR cassette recording",
    "slow: tests that take a long time to run",
    "paid_tier: tests requiring a paid Finnhub subscription",
]
```

**Key flags explained:**

| Flag | Effect |
|------|--------|
| `--ignore=tests/integration` | Excludes the entire `integration/` directory from the default run |
| `--ignore=tests/e2e` | Excludes the entire `e2e/` directory from the default run |
| `--disable-socket` | Blocks all TCP/UDP sockets — any real network call raises `SocketBlockedError` |
| `--allow-unix-socket` | Permits Unix domain socket connections (needed by some local processes) |
| `-x` | Stop at the first failure (fast feedback in CI) |
| `-q` | Quiet mode — minimal output |

---

### pytest-socket `>=0.7.0`

Adds the `--disable-socket` and `--allow-hosts` CLI flags and the `@pytest.mark.allow_hosts` marker.

**How it works:**  
At test startup it monkey-patches `socket.socket.__new__` to raise
`pytest_socket.SocketBlockedError` (a `RuntimeError` subclass) for any TCP/UDP
connection attempt.  Unix domain sockets are allowed through when
`--allow-unix-socket` is set.

**Impact on the project:**

- All unit tests run with sockets blocked — any accidental real API call immediately
  fails with a clear error message.
- The root `conftest.py`'s `av_api_key` fixture catches `RuntimeError` so that
  `@pytest.mark.integration` tests that depend on it auto-skip rather than error when
  run in a socket-blocked context.
- yfinance uses `curl_cffi` (libcurl) which bypasses Python's `socket` module.  This
  is why yfinance-backed tests must use mocks rather than relying on
  `--disable-socket` alone.

---

### pytest-recording `>=0.13.2` + vcrpy `>=6.0.2`

[VCR.py](https://vcrpy.readthedocs.io/) records real HTTP responses to YAML
"cassette" files, then replays them offline in subsequent runs.

**Configuration** (in `tests/integration/conftest.py`):

```python
@pytest.fixture(scope="module")
def vcr_config():
    return {
        "cassette_library_dir": "tests/cassettes",
        "match_on": ["method", "scheme", "host", "port", "path"],
        "filter_headers": ["Authorization", "Cookie", "X-Api-Key"],
        "filter_query_parameters": ["apikey", "token"],
        "decode_compressed_response": True,
    }
```

**Key settings:**

| Setting | Value | Why |
|---------|-------|-----|
| `match_on` | method, scheme, host, port, path | Ignores query string changes (e.g., different API keys), matches by URL shape |
| `filter_headers` | Auth headers | Strips secrets before writing to cassette files |
| `filter_query_parameters` | `apikey`, `token` | Strips API keys from recorded URLs |
| `decode_compressed_response` | `True` | Ensures gzip/brotli responses are stored as readable text |

> **Note:** VCR.py cannot intercept `curl_cffi` (yfinance's HTTP backend).
> Therefore, cassettes are only used for `requests`-based vendors
> (Alpha Vantage, Finnhub). yfinance integration tests run live.

---

### unittest.mock (stdlib)

Python's built-in mocking library.  The project uses three primitives heavily:

| Primitive | Use case |
|-----------|----------|
| `patch(target)` | Temporarily replace a module-level name (e.g., `requests.get`) |
| `patch.dict(os.environ, {...})` | Inject temporary env vars without touching the real environment |
| `MagicMock()` | Create a flexible mock object with auto-spec attributes |
| `PropertyMock` | Mock `@property` descriptors on classes (e.g., `yf.Ticker.info`) |

---

### pandas / numpy (test helpers)

Used only inside test helpers to build realistic DataFrame fixtures that match
yfinance's actual return shapes.  No pandas assertions are made directly — output
is always validated as a formatted string.

---

## Fixtures Reference

Fixtures are defined at three levels; pytest resolves them from the innermost
conftest outward.

### Root: `tests/conftest.py`

Available to **all** tiers.

#### `_set_alpha_vantage_demo_key` *(autouse)*

```python
@pytest.fixture(autouse=True)
def _set_alpha_vantage_demo_key(monkeypatch):
    ...
```

- **Scope:** function (default)
- **Effect:** Sets `ALPHA_VANTAGE_API_KEY=demo` in the test environment if the
  variable is not already present.
- **Why autouse:** Prevents tests from accidentally hitting Alpha Vantage with a
  real key or failing because the key is missing.  Every test runs with a known
  safe value.

#### `av_api_key`

```python
@pytest.fixture
def av_api_key():
    ...
```

- **Scope:** function
- **Effect:** Returns the Alpha Vantage API key (`"demo"` by default).  If the
  Alpha Vantage endpoint is unreachable (network blocked, CI sandbox, or
  `pytest-socket` active), the test is **automatically skipped**.
- **Why:** Allows the same integration test file to run both in development
  (live) and in CI (skipped gracefully) without any test code changes.
- **Catches:** `socket.error`, `OSError`, `RuntimeError` (covers
  `SocketBlockedError`).

#### `av_config`

```python
@pytest.fixture
def av_config():
    ...
```

- **Scope:** function
- **Effect:** Returns a copy of `DEFAULT_CONFIG` with `scanner_data` vendor
  overridden to `"alpha_vantage"`.
- **Why:** Tests that want to exercise the Alpha Vantage scanner code path without
  touching the real config.

---

### Unit tier: `tests/unit/conftest.py`

Available only within `tests/unit/`.

#### `mock_yf_screener`

```python
@pytest.fixture
def mock_yf_screener():
    # Returns a factory: _make(quotes) → {"quotes": quotes}
```

- **Scope:** function
- **Effect:** Factory that builds a minimal yfinance screener response dict.
- **Why:** yfinance's `Screener` object is hard to instantiate offline; this
  factory lets tests inject arbitrary screener data.

#### `mock_yf_download`

```python
@pytest.fixture
def mock_yf_download():
    # Returns a factory: _make(symbols, periods, base_price) → MultiIndex DataFrame
```

- **Scope:** function
- **Effect:** Factory that builds a MultiIndex `Close` DataFrame matching
  yfinance's `download()` output shape.
- **Why:** Tests for functions that process downloaded price data need a
  realistic DataFrame — this factory provides one without any network calls.

#### `mock_av_request`

```python
@pytest.fixture
def mock_av_request():
    # Returns a factory: _make(responses: dict) → fake _rate_limited_request
```

- **Scope:** function
- **Effect:** Factory that builds a drop-in replacement for
  `alpha_vantage_common._rate_limited_request`.  The `responses` dict maps
  `function_name → return_value`.  Supports both plain values and callables
  (for dynamic responses).
- **Why:** Lets unit tests exercise AV parsing code without any HTTP calls or
  rate-limit logic.

#### `mock_llm`

```python
@pytest.fixture
def mock_llm():
    # Returns a factory: _make(content) → MagicMock LLM
```

- **Scope:** function
- **Effect:** Factory that builds a `MagicMock` that implements `.invoke()` and
  `.ainvoke()` returning a canned `content` string.
- **Why:** Agent tests need an LLM object but must not make real API calls.

---

### Integration tier: `tests/integration/conftest.py`

Available only within `tests/integration/`.

#### `vcr_config` *(module-scoped)*

```python
@pytest.fixture(scope="module")
def vcr_config():
    return { "cassette_library_dir": "tests/cassettes", ... }
```

- **Scope:** module (shared across all tests in a module)
- **Effect:** Provides VCR.py configuration — cassette directory, match rules,
  secret filtering.
- **Why module-scoped:** Cassette config is the same for all tests in a file;
  no need to recreate per-test.

#### `av_api_key` *(integration override)*

```python
@pytest.fixture
def av_api_key():
    return os.environ.get("ALPHA_VANTAGE_API_KEY", "demo")
```

- **Scope:** function
- **Effect:** Returns the API key directly **without** a reachability check.
  Integration tests assume the network is available.
- **Why override:** Integration tests are only run when the developer explicitly
  requests them (`pytest tests/integration/`), so a reachability guard is
  unnecessary.

---

### E2E tier: `tests/e2e/conftest.py`

#### `pytest_collection_modifyitems` hook

```python
def pytest_collection_modifyitems(config, items):
    for item in items:
        item.add_marker(pytest.mark.e2e)
        item.add_marker(pytest.mark.slow)
```

- **Effect:** Automatically tags every test in `tests/e2e/` with both
  `@pytest.mark.e2e` and `@pytest.mark.slow` — no manual decoration needed.

---

## Markers Reference

| Marker | Applied by | Meaning | Tests using it |
|--------|-----------|---------|----------------|
| `integration` | `@pytest.mark.integration` on class/function | Test hits a real external API | `tests/unit/test_alpha_vantage_scanner.py`, `tests/integration/*.py`, some `tests/unit/test_*.py` integration classes |
| `e2e` | e2e conftest hook (autoapplied) | Test runs real LLM pipeline | all of `tests/e2e/` |
| `slow` | e2e conftest hook (autoapplied) | Test takes >30 s | all of `tests/e2e/` |
| `vcr` | `@pytest.mark.vcr` on function | Test replays VCR cassette | (available, not yet widely used) |
| `paid_tier` | `@pytest.mark.paid_tier` | Requires paid Finnhub subscription | `tests/integration/test_finnhub_live.py` |
| `skip` | `@pytest.mark.skip` | Unconditionally skipped | paid-tier Finnhub tests |
| `skipif` | `@pytest.mark.skipif(not KEY, ...)` | Conditionally skipped | `tests/integration/test_finnhub_live.py`, `tests/integration/test_nlm_live.py` |

---

## Test File Catalogue

### Unit tests (`tests/unit/`)

| File | # Tests (approx.) | What it covers | Key mocks used |
|------|-----------------:|----------------|---------------|
| `test_alpha_vantage_exceptions.py` | 7 | AV exception hierarchy + error-handling branches | `requests.get` (side_effect) |
| `test_alpha_vantage_integration.py` | ~36 | AV data layer — stock, fundamentals, news, indicators | `requests.get` (mock response) |
| `test_alpha_vantage_scanner.py` | 10 (skipped) | AV scanner — gainers, losers, indices, sectors, news | Real API (auto-skipped via `av_api_key`) |
| `test_config_wiring.py` | 15 | AgentState fields, new tool exports, config defaults | Import-only |
| `test_debate_rounds.py` | 17 | `ConditionalLogic` — debate and risk routing thresholds | None (pure logic) |
| `test_e2e_api_integration.py` | 19 | `route_to_vendor` + full yfinance+AV pipeline | `yf.Ticker`, `requests.get` |
| `test_env_override.py` | 15 | `TRADINGAGENTS_*` env vars override `DEFAULT_CONFIG` | `importlib.reload`, `patch.dict` |
| `test_finnhub_integration.py` | ~100 | Finnhub data layer — all endpoints, exception types | `requests.get` (mock response) |
| `test_finnhub_scanner_utils.py` | 10 | `_safe_fmt` and other Finnhub scanner utility functions | None (pure logic) |
| `test_incident_fixes.py` | 15 | `_load_or_fetch_ohlcv` cache, `YFinanceError` propagation | `yf.Ticker`, `tmp_path` |
| `test_industry_deep_dive.py` | 12 | `_extract_top_sectors()` + `run_tool_loop` nudge | `MagicMock` LLM, `ToolMessage` |
| `test_json_utils.py` | 15 | `extract_json` — fences, think-tags, malformed input | None (pure logic) |
| `test_langgraph_engine_extraction.py` | 14 | `_map_langgraph_event` — event type mapping, metadata extraction | `MagicMock` events |
| `test_langgraph_engine_run_modes.py` | 28 | `run_scan/pipeline/portfolio/auto` — phase coordination, skip logic | `MagicMock` store, `AsyncMock` graph |
| `test_macro_bridge.py` | ~12 | Macro JSON parsing, filtering, report rendering | `tmp_path` |
| `test_macro_regime.py` | ~32 | VIX signals, credit spread, breadth, regime classifier | `pd.Series`, `patch` (yfinance) |
| `test_notebook_sync.py` | 5 | `sync_to_notebooklm` subprocess flow | `subprocess.run` |
| `test_peer_comparison.py` | ~18 | Sector peers, relative performance, comparison report | `yf.Ticker`, `yf.Sector` |
| `test_portfolio_tools.py` | 23 | `portfolio_tools.py` — in-memory data, no DB | `MagicMock` repo |
| `test_scanner_fallback.py` | 2 | AV scanner raises on total failure | `_fetch_global_quote` side_effect |
| `test_scanner_graph.py` | 4 | `ScannerGraph` + `ScannerGraphSetup` compile correctly | `ScannerGraph._create_llm` |
| `test_scanner_mocked.py` | ~57 | yfinance + AV scanner functions, route_to_vendor routing | `yf.Screener`, `requests.get` |
| `test_security_notebook_sync.py` | 3 | Shell injection guard in `sync_to_notebooklm` | None |
| `test_stockstats_utils.py` | ~20 | `get_stockstats_indicator` + `stockstats` formatting | `yf.download` mock |
| `test_ttm_analysis.py` | ~21 | TTM metric computation, report formatting | `yf.Ticker` (quarterly data) |
| `test_vendor_failfast.py` | 11 | Fail-fast routing (ADR 011), error chaining | `requests.get`, `MagicMock` |
| `test_yfinance_integration.py` | ~48 | yfinance data layer — OHLCV, fundamentals, news | `yf.Ticker`, `yf.Search` |
| `agents/test_analyst_agents.py` | ~15 | Analyst agent node wiring + prompt formatting | `MagicMock` LLM |

### Portfolio tests (`tests/portfolio/`)

These tests cover the portfolio management module with in-memory data only — no database connection is required.

| File | # Tests | What it covers | Key mocks used |
|------|--------:|----------------|---------------|
| `test_candidate_prioritizer.py` | 10 | Candidate scoring + ranking algorithm | None (pure logic) |
| `test_config.py` | 8 | Portfolio config defaults + env var overrides | `patch.dict` |
| `test_models.py` | 23 | `Portfolio`, `Holding`, `Trade`, `PortfolioSnapshot` dataclasses | None (pure logic) |
| `test_report_store.py` | 23 | `ReportStore` save/load cycle, JSON serialization | `tmp_path` |
| `test_repository.py` | 16 | `PortfolioRepository` — CRUD operations | `MagicMock` Supabase client |
| `test_risk_evaluator.py` | 28 | Risk constraint checks — position limits, sector limits, cash floor | None (pure logic) |
| `test_risk_metrics.py` | 48 | Volatility, Sharpe, max drawdown, beta metrics | `pd.Series` |
| `test_trade_executor.py` | 10 | `TradeExecutor` — sell/buy ordering, constraint pre-flight, snapshot | `MagicMock` repo |

### CLI tests (`tests/cli/`)

| File | # Tests | What it covers | Key mocks used |
|------|--------:|----------------|---------------|
| `test_main.py` | ~8 | `extract_content_string`, CLI argument parsing | `patch` (LLM), `tmp_path` |
| `test_stats_handler.py` | ~6 | `StatsCallbackHandler` — token counting, threading safety | `MagicMock` LLM callbacks |

### Integration tests (`tests/integration/`)

| File | # Tests | What it covers | Requires |
|------|--------:|----------------|---------|
| `test_alpha_vantage_live.py` | 3 | Live AV `_make_api_request` — key errors, timeout, success | Network |
| `test_finnhub_live.py` | ~41 | All Finnhub free-tier + paid-tier endpoints (live HTTP) | `FINNHUB_API_KEY` |
| `test_finviz_live.py` | 27 | All three Finviz smart-money screener tools — live HTTP | Network; auto-skips if `finvizfinance` not installed |
| `test_nlm_live.py` | 1 | NotebookLM source CRUD via `nlm` CLI | `NOTEBOOKLM_ID` + `nlm` binary |
| `test_scanner_live.py` | ~23 | yfinance scanner tools + AV routing (live yfinance + AV) | Network; `ALPHA_VANTAGE_API_KEY` for AV tests |
| `test_stockstats_live.py` | ~6 | `get_stockstats_indicator` against live yfinance data | Network |

### E2E tests (`tests/e2e/`)

| File | # Tests | What it covers | Requires |
|------|--------:|----------------|---------|
| `test_llm_e2e.py` | 1 | Full `run_scan()` pipeline — file output validation | LLM API key + network |

---

## Execution Flow Diagrams

### Default `pytest` run (CI / development)

```mermaid
flowchart TD
    A([pytest invoked]) --> B{addopts applied}
    B --> C["--ignore=tests/integration\n--ignore=tests/e2e"]
    B --> D["--disable-socket\n--allow-unix-socket"]
    B --> E["-x -q"]
    C --> F[Collect tests/unit/**]
    D --> G[pytest-socket patches socket.socket.__new__]
    F --> H{For each test}
    H --> I{Needs network?}
    I -- "yes (real call)" --> J["SocketBlockedError raised\n→ test FAILS immediately"]
    I -- "no (mocked)" --> K[Test runs offline]
    K --> L{Uses av_api_key fixture?}
    L -- yes --> M["root conftest tries socket.connect()\n→ catches RuntimeError\n→ pytest.skip()"]
    L -- no --> N[Run test body]
    M --> O([Test SKIPPED])
    N --> P{assertions pass?}
    P -- yes --> Q([Test PASSED])
    P -- no --> R([Test FAILED])
    E --> S["-x: stop at first failure"]
```

---

### Integration test run (`pytest tests/integration/`)

```mermaid
flowchart TD
    A([pytest tests/integration/]) --> B[No --disable-socket\nNetwork allowed]
    B --> C{FINNHUB_API_KEY set?}
    C -- no --> D["pytestmark skipif\n→ entire test_finnhub_live.py SKIPPED"]
    C -- yes --> E[Finnhub live tests run]
    B --> F{ALPHA_VANTAGE_API_KEY set?}
    F -- no --> G["av_api_key returns 'demo'\n(limited data)"]
    F -- yes --> H["av_api_key returns real key"]
    G & H --> I[AV live tests run]
    B --> J{NOTEBOOKLM_ID + nlm CLI set?}
    J -- no --> K["pytest.mark.skipif\n→ test_nlm_live.py SKIPPED"]
    J -- yes --> L[NotebookLM live test runs]
    B --> M[Scanner live tests run\nagainst real yfinance API]
    B --> N{finvizfinance installed?}
    N -- no --> O["pytestmark skipif\n→ test_finviz_live.py SKIPPED"]
    N -- yes --> P[Finviz screener tests run\nno API key needed]
    E & I & K & L & M & O & P --> Q([Results reported])
```

---

### Mock data flow (unit test)

```mermaid
flowchart LR
    subgraph "Test body"
        T[Test function]
    end

    subgraph "Mocks / patches"
        P1["patch('requests.get')\nreturns mock response"]
        P2["patch('yf.Ticker')\nreturns MagicMock"]
        P3["patch.dict(os.environ)\ninjects API key"]
    end

    subgraph "Code under test"
        F1["AV data function\nalpha_vantage_stock.get_stock()"]
        F2["yfinance data function\ny_finance.get_YFin_data_online()"]
        F3["route_to_vendor()\nvendor router"]
    end

    T --> P1 --> F1 --> R1[Formatted string result]
    T --> P2 --> F2 --> R2[Formatted string result]
    T --> P3 --> F3 --> R1
    T --> P3 --> F3 --> R2
    R1 --> A1{assert isinstance result str}
    R2 --> A2{assert 'AAPL' in result}
```

---

### pytest-socket protection flow

```mermaid
flowchart TD
    A[Test starts] --> B["pytest-socket active\n(--disable-socket)"]
    B --> C{Test tries to\nopen a socket?}
    C -- "No socket call" --> D[Test continues normally]
    C -- "Python socket.socket()" --> E["SocketBlockedError raised\n(RuntimeError subclass)"]
    C -- "curl_cffi / libcurl\n(yfinance)" --> F["⚠️ Bypasses pytest-socket!\nMust use mock instead"]
    E --> G{Is test using\nav_api_key fixture?}
    G -- yes --> H["RuntimeError caught in fixture\n→ pytest.skip()"]
    G -- no --> I[Test FAILS]
    F --> J["Use patch('yf.Ticker') to mock\nbefore calling yfinance code"]
```

---

### VCR cassette lifecycle (integration)

```mermaid
flowchart TD
    A["pytest tests/integration/ --record-mode=new_episodes"] --> B{Cassette file\nexists?}
    B -- no --> C[Make real HTTP request to API]
    C --> D[Write response to\ntests/cassettes/<name>.yaml]
    D --> E[Test asserts on response]
    B -- yes --> F[Load response from cassette]
    F --> E
    E --> G{Test passes?}
    G -- yes --> H([✅ Pass])
    G -- no --> I([❌ Fail])

    A2["pytest tests/integration/\n(default — no --record-mode)"] --> F
```

---

## How to Run Tests

### Quick reference

| What to run | Command | Expected result |
|---|---|---|
| **All unit tests (CI-safe)** | `pytest` | 793 passed, 14 skipped, < 5 s |
| **Unit tests only** | `pytest tests/unit/` | ~600 passed |
| **Portfolio tests only** | `pytest tests/portfolio/` | ~166 passed |
| **CLI tests only** | `pytest tests/cli/` | ~14 passed |
| **All integration tests** | `pytest tests/integration/ -v` | varies (network required) |
| **Finviz integration** | `pytest tests/integration/test_finviz_live.py -v` | 27 tests, network required |
| **Finnhub integration** | `FINNHUB_API_KEY=<key> pytest tests/integration/test_finnhub_live.py -v` | requires key |
| **E2E pipeline** | `pytest tests/e2e/ -v` | requires LLM key + network |

---

### Install dependencies first

```bash
pip install -e .
pip install pytest pytest-socket
```

---

### Default (unit + portfolio + cli, CI-safe)

The default `pytest` invocation is controlled by `addopts` in `pyproject.toml`:

```toml
addopts = "--ignore=tests/integration --ignore=tests/e2e --disable-socket --allow-unix-socket -x -q"
```

Run it with:

```bash
# Simplest — uses addopts automatically
pytest

# Equivalent explicit form
pytest tests/ --ignore=tests/integration --ignore=tests/e2e \
    --disable-socket --allow-unix-socket -x -q
```

Expected output:

```
793 passed, 14 skipped in 4.9s
```

**What `-x` does:** stops at the first failing test.  
**What `-q` does:** minimal output (dots + summary).  
**What `--disable-socket` does:** blocks all real network calls — any accidental HTTP call fails with `SocketBlockedError`.

To see all failures instead of stopping at the first:

```bash
pytest tests/ --ignore=tests/integration --ignore=tests/e2e \
    --disable-socket --allow-unix-socket -q
# (omit -x)
```

---

### Run a single test file

```bash
# Unit file
pytest tests/unit/test_langgraph_engine_run_modes.py -v \
    --disable-socket --allow-unix-socket

# Portfolio file
pytest tests/portfolio/test_trade_executor.py -v \
    --disable-socket --allow-unix-socket

# CLI file
pytest tests/cli/test_stats_handler.py -v \
    --disable-socket --allow-unix-socket
```

---

### Run a single test class or test function

```bash
# Single class
pytest tests/unit/test_langgraph_engine_run_modes.py::TestRunAutoTickerSource -v \
    --disable-socket --allow-unix-socket

# Single test function
pytest tests/unit/test_langgraph_engine_run_modes.py::TestRunAutoTickerSource::test_run_auto_gets_tickers_from_scan_report -v \
    --disable-socket --allow-unix-socket
```

---

### Integration tests (requires network)

Integration tests make **real HTTP calls** to external APIs.  They are
excluded from the default run but can be run explicitly at any time.

```bash
# All integration tests (everything in tests/integration/)
pytest tests/integration/ -v

# Finviz smart-money screener tests (no API key needed — free public screener)
pytest tests/integration/test_finviz_live.py -v

# Alpha Vantage live tests ('demo' key works for basic calls)
pytest tests/integration/test_alpha_vantage_live.py -v

# Finnhub live tests (free-tier endpoints only)
FINNHUB_API_KEY=your_key pytest tests/integration/test_finnhub_live.py -v \
    -m "integration and not paid_tier"

# Finnhub — all tests including paid-tier (requires premium subscription)
FINNHUB_API_KEY=your_key pytest tests/integration/test_finnhub_live.py -v

# Live scanner tests (hits real yfinance + Alpha Vantage APIs)
pytest tests/integration/test_scanner_live.py -v

# Live stockstats tests
pytest tests/integration/test_stockstats_live.py -v

# NotebookLM tests (requires NOTEBOOKLM_ID env var and nlm CLI binary)
NOTEBOOKLM_ID=your_id pytest tests/integration/test_nlm_live.py -v
```

> **Tip:** When running integration tests from a network-blocked environment
> (e.g., CI without outbound access), tests that require a network connection
> will auto-skip rather than fail — they detect the blocked socket and call
> `pytest.skip()` gracefully.

---

### E2E tests (requires LLM API key + network, manual only)

```bash
# Requires a real LLM API key (e.g., OPENAI_API_KEY) and network access.
# Takes several minutes to complete.
pytest tests/e2e/ -v
```

---

### Run only tests with a specific marker

```bash
# All integration-marked tests across the entire test suite
pytest tests/ --override-ini="addopts=" -m integration -v

# All tests except slow ones
pytest tests/ --override-ini="addopts=" -m "not slow" \
    --disable-socket --allow-unix-socket

# Only paid_tier Finnhub tests (requires premium key)
FINNHUB_API_KEY=your_key pytest tests/integration/ -m paid_tier -v
```

> **`--override-ini="addopts="`** clears the default `addopts` from
> `pyproject.toml` so you can pass your own flags instead.

---

### Re-record VCR cassettes

```bash
# Record only new requests (existing cassettes kept)
pytest tests/integration/ --record-mode=new_episodes

# Re-record everything from scratch
pytest tests/integration/ --record-mode=all
```

---

## Mock Patterns

### Pattern 1 — Mock `requests.get` for Alpha Vantage / Finnhub

Used in: `test_alpha_vantage_integration.py`, `test_finnhub_integration.py`,
`test_scanner_mocked.py`, `test_vendor_failfast.py`

```python
import json
from unittest.mock import patch, MagicMock

def _mock_response(payload, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = json.dumps(payload) if isinstance(payload, dict) else payload
    resp.json.return_value = payload if isinstance(payload, dict) else {}
    resp.raise_for_status = MagicMock()
    return resp

def test_something():
    with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
               return_value=_mock_response({"Symbol": "AAPL"})):
        result = get_fundamentals("AAPL")
    assert "AAPL" in result
```

---

### Pattern 2 — Mock `yf.Ticker` for yfinance

Used in: `test_yfinance_integration.py`, `test_e2e_api_integration.py`,
`test_scanner_mocked.py`, `test_peer_comparison.py`

```python
import pandas as pd
from unittest.mock import patch, MagicMock, PropertyMock

def _make_ohlcv():
    idx = pd.date_range("2024-01-02", periods=3, freq="B", tz="America/New_York")
    return pd.DataFrame(
        {"Open": [150.0, 151.0, 152.0], "Close": [152.0, 153.0, 154.0],
         "High": [155.0, 156.0, 157.0], "Low": [148.0, 149.0, 150.0],
         "Volume": [1_000_000] * 3},
        index=idx,
    )

def test_something():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _make_ohlcv()
    # For .info (a property):
    type(mock_ticker).info = PropertyMock(return_value={"longName": "Apple Inc."})

    with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
        result = get_YFin_data_online("AAPL", "2024-01-02", "2024-01-05")
    assert "AAPL" in result
```

---

### Pattern 3 — Mock `requests.get` for error branches

Used in: `test_alpha_vantage_exceptions.py`, `test_vendor_failfast.py`

```python
import requests as _requests
from unittest.mock import patch

def test_timeout_raises_correct_exception():
    with patch(
        "tradingagents.dataflows.alpha_vantage_common.requests.get",
        side_effect=_requests.exceptions.Timeout("simulated timeout"),
    ):
        with pytest.raises(ThirdPartyTimeoutError):
            _make_api_request("TIME_SERIES_DAILY", {"symbol": "IBM"})
```

---

### Pattern 4 — Reload config module to test env var overrides

Used in: `test_env_override.py`

```python
import importlib
import os
from unittest.mock import patch

class TestEnvOverrides:
    def _reload_config(self):
        import tradingagents.default_config as mod
        importlib.reload(mod)
        return mod.DEFAULT_CONFIG

    def test_llm_provider_override(self):
        with patch.dict(os.environ, {"TRADINGAGENTS_LLM_PROVIDER": "anthropic"}):
            cfg = self._reload_config()
        assert cfg["llm_provider"] == "anthropic"
```

> **Why `importlib.reload`?** `DEFAULT_CONFIG` is built at *module import time*.
> To test different env var values, the module must be re-evaluated.  The
> `_reload_config` helper also patches `dotenv.load_dotenv` to prevent
> `.env` files from interfering with isolated env patches.

---

### Pattern 5 — Mock LLM for agent / tool-loop tests

Used in: `test_industry_deep_dive.py`

```python
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage

def _make_llm(content: str):
    msg = AIMessage(content=content, tool_calls=[])
    llm = MagicMock()
    llm.invoke.return_value = msg
    return llm
```

---

### Pattern 6 — Local-file fixtures with `autouse`

Used in: `tests/unit/test_finnhub_integration.py`

```python
@pytest.fixture(autouse=True)
def set_fake_api_key(monkeypatch):
    """Inject a dummy API key so every test bypasses the missing-key guard."""
    monkeypatch.setenv("FINNHUB_API_KEY", "test_key")
```

`monkeypatch` is a built-in pytest fixture.  `autouse=True` makes it apply
automatically to every test in the file without explicit declaration.

---

## What is MagicMock?

`MagicMock` is the workhorse of Python's `unittest.mock` library — the
standard tool for replacing real objects with controllable stand-ins during
tests.  Understanding it is essential for reading and writing tests in this
project.

---

### The core idea: a pretend object

When you write:

```python
from unittest.mock import MagicMock

repo = MagicMock()
```

`repo` is now an object that:
- **accepts any attribute access** (`repo.some_attr` → another `MagicMock`)
- **accepts any method call** (`repo.get_portfolio()` → another `MagicMock`)
- **records everything** so you can ask later: "was this called? with what?"

No database, no HTTP, no file system — just a pretend object you fully control.

---

### Setting return values

By default every method returns a new `MagicMock`.  You can override this:

```python
repo = MagicMock()
repo.get_portfolio.return_value = {"portfolio_id": "p1", "cash": 50_000.0}

result = repo.get_portfolio("p1")   # returns the dict you set, not a MagicMock
print(result["cash"])               # 50000.0
```

This is critical.  If you forget `return_value=...`, the method returns a
`MagicMock`, which is **truthy**.  Code that does `if repo.load_data(...):`
will take the "data exists" branch even when it shouldn't.

---

### The truthy problem (and why it caused the mock trade bug)

This project has guard clauses like:

```python
if not force and store.load_execution_result(date, portfolio_id):
    # skip — already done
    return
```

If `store = MagicMock()` and `load_execution_result` is never given a
`return_value`, the call returns a new `MagicMock`, which is truthy.
The entire Phase 3 (portfolio execution / trades) gets **skipped** even
though no trades ever ran.

**The fix:** always set `return_value=None` for methods that are supposed to
return "nothing found":

```python
mock_store = MagicMock()
mock_store.load_scan.return_value = scan_data       # some data
mock_store.load_execution_result.return_value = None  # ← explicitly "not found"
mock_store.load_pm_decision.return_value = None       # ← explicitly "not found"
mock_store.load_analysis.return_value = None          # ← explicitly "not found"
```

This is the pattern used in `TestRunAutoTickerSource._make_mock_store()`.

---

### Checking calls (assertions)

```python
repo = MagicMock()
repo.add_holding("p1", "AAPL", 10, 150.0)

# Was it called?
repo.add_holding.assert_called_once()

# Was it called with these exact arguments?
repo.add_holding.assert_called_once_with("p1", "AAPL", 10, 150.0)

# How many times?
assert repo.add_holding.call_count == 1

# What args did the last call use?
args, kwargs = repo.add_holding.call_args
assert args[1] == "AAPL"
```

---

### Raising exceptions from mocks

```python
repo.add_holding.side_effect = InsufficientCashError("Not enough cash")

# Now calling add_holding() will raise the error instead of returning a value
```

`side_effect` can also be a callable or a list of values/exceptions to cycle
through on successive calls.

---

### AsyncMock — for `async def` functions

LangGraph uses `async for` and `await` extensively.  For those, use
`AsyncMock`:

```python
from unittest.mock import AsyncMock, MagicMock

mock_graph = MagicMock()
mock_graph.astream_events = AsyncMock(return_value=iter([]))
# or as an async generator:
async def fake_stream(*args, **kwargs):
    yield {"event": "on_chain_end", "data": {"output": {}}}
mock_graph.astream_events = fake_stream
```

---

### patch() — replacing real objects temporarily

`MagicMock` creates the stand-in; `patch()` *swaps* it in for the duration
of a `with` block (or test function):

```python
from unittest.mock import patch, MagicMock

def test_run_portfolio_skips_when_already_done():
    mock_store = MagicMock()
    mock_store.load_execution_result.return_value = {"summary": "done"}

    with patch("agent_os.backend.services.langgraph_engine.ReportStore",
               return_value=mock_store):
        # All code inside here that imports ReportStore gets mock_store instead
        ...
```

The `target` string must be the **import path where the name is used**, not
where it is defined.  If `langgraph_engine.py` does
`from tradingagents.portfolio.report_store import ReportStore`, you patch
`agent_os.backend.services.langgraph_engine.ReportStore`.

---

### PropertyMock — for `@property` attributes

```python
from unittest.mock import MagicMock, PropertyMock

mock_ticker = MagicMock()
type(mock_ticker).info = PropertyMock(return_value={"longName": "Apple Inc."})
# mock_ticker.info now returns the dict (not a MagicMock)
```

---

### Quick reference table

| Tool | Use case |
|------|----------|
| `MagicMock()` | Stand-in for any object (repo, client, graph) |
| `mock.method.return_value = x` | Make a method return `x` |
| `mock.method.side_effect = exc` | Make a method raise `exc` |
| `mock.method.assert_called_once_with(...)` | Assert exact call args |
| `AsyncMock()` | Stand-in for `async def` functions / methods |
| `patch("module.Name")` | Swap a real class/function with a mock temporarily |
| `patch.dict(os.environ, {...})` | Inject env vars for the duration of a test |
| `PropertyMock` | Mock `@property` descriptors |

---

## Adding New Tests — Checklist

When adding a test to this project, choose the right tier and follow the
corresponding checklist.

### Unit test (default tier — 95% of cases)

- [ ] File goes in `tests/unit/test_<module>.py`
- [ ] **No real network calls.** All HTTP must be mocked with `patch`.
- [ ] yfinance: use `patch("...yf.Ticker", ...)` — never call yfinance directly.
- [ ] AV / Finnhub: use `patch("...requests.get", return_value=_mock_response(...))`.
- [ ] Use `monkeypatch.setenv` or `patch.dict(os.environ, ...)` for env var tests.
- [ ] When mocking a store/repo, always pin `load_*` methods to `None` to avoid
      truthy MagicMock accidentally triggering "already done" skip branches.
- [ ] Do NOT use `@pytest.mark.integration` — that signals the test is being tracked
      for future migration, not that it's already mocked.
- [ ] Run `pytest tests/unit/ -x --disable-socket --allow-unix-socket` to confirm the test passes offline.

### Portfolio module test (no DB needed)

- [ ] File goes in `tests/portfolio/test_<component>.py`.
- [ ] Use `MagicMock()` for the Supabase client / `PortfolioRepository` if testing
      higher-level logic.  Do NOT use a real DB connection.
- [ ] Run `pytest tests/portfolio/ -x --disable-socket --allow-unix-socket`.

### Integration test (live API needed)

- [ ] File goes in `tests/integration/test_<vendor>_live.py`.
- [ ] Class or function decorated with `@pytest.mark.integration`.
- [ ] Use the `av_api_key` fixture (or a similar guard) to auto-skip when the API
      is unavailable.
- [ ] For APIs with no key (e.g., Finviz): use `pytest.mark.skipif(not lib_available, ...)`
      so the file is skipped if the library is not installed.
- [ ] For Finnhub paid-tier endpoints: add both `@pytest.mark.paid_tier` and
      `@pytest.mark.skip` so they are documented but never run accidentally.
- [ ] Do NOT add the file path to `addopts`'s `--ignore` list — it is already
      covered by `--ignore=tests/integration`.

### E2E test (full pipeline)

- [ ] File goes in `tests/e2e/test_<feature>_e2e.py`.
- [ ] The conftest auto-applies `@pytest.mark.e2e` and `@pytest.mark.slow`.
- [ ] Mock only filesystem paths and CLI prompts — **not** LLM or data APIs.
- [ ] Document required env vars in the module docstring.
