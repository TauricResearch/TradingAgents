# Memory As-Of-Date Filtering and Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the portfolio memory system safe for backtesting by adding `as_of_date` filtering to prevent future leakage, seeding `run_id` in every portfolio run entry point, writing PM decisions back to reflexion memory after execution, and surfacing corrupt local memory as warnings instead of silent empty returns.

**Architecture:** Add an optional `as_of_date: str | None` parameter to `MacroMemory.get_recent()` / `build_macro_context()` and `ReflexionMemory.get_history()` / `build_context()` — both MongoDB (query filter) and local JSON paths. The summary agents forward `analysis_date` from state to these methods. `PortfolioGraph.run()` accepts and seeds a `run_id`. A new `record_pm_decisions_node` runs after `execute_trades` and writes final PM buy/sell/hold decisions to `micro_reflexion`. Corrupt local JSON logs a warning instead of silently returning `[]`.

**Tech Stack:** Python, pytest, pymongo (MongoDB optional — all paths tested against local JSON fallback), LangGraph state dicts.

---

## File Map

| File | Change |
|------|--------|
| `tradingagents/memory/macro_memory.py` | Add `as_of_date` param to `get_recent()` and `build_macro_context()`; warn on corrupt local file |
| `tradingagents/memory/reflexion.py` | Add `as_of_date` param to `get_history()` and `build_context()`; warn on corrupt local file |
| `tradingagents/agents/portfolio/macro_summary_agent.py` | Pass `analysis_date` as `as_of_date` to `build_macro_context()` |
| `tradingagents/agents/portfolio/micro_summary_agent.py` | Pass `analysis_date` as `as_of_date` to `build_context()` |
| `tradingagents/graph/portfolio_graph.py` | Add `run_id: str | None = None` to `run()`; seed into initial state |
| `tradingagents/graph/portfolio_setup.py` | Add `_make_record_pm_decisions_node()` factory; wire it into the graph after `execute_trades` |
| `tests/unit/test_macro_memory.py` | Add `as_of_date` filtering tests and corrupt-file warning test |
| `tests/unit/test_reflexion_memory.py` | Add `as_of_date` filtering tests and corrupt-file warning test |
| `tests/unit/test_summary_agents.py` | Verify `as_of_date` forwarded from state; verify `run_id` seeded |
| `tests/portfolio/test_portfolio_setup.py` | Verify reflexion write-back node records decisions |

---

## Task 1: Add `as_of_date` filter to `MacroMemory`

**Files:**
- Modify: `tradingagents/memory/macro_memory.py`
- Test: `tests/unit/test_macro_memory.py`

- [ ] **Step 1.1: Write failing tests for `as_of_date` filtering**

```python
# In tests/unit/test_macro_memory.py — add inside TestMacroMemoryLocalFallback

def test_get_recent_excludes_future_records(self, tmp_path):
    """get_recent(as_of_date=...) must not return records after that date."""
    m = MacroMemory(fallback_path=tmp_path / "macro.json")
    m.record_macro_state(
        date="2026-01-10", vix_level=20.0, macro_call="neutral",
        sector_thesis="Early year", key_themes=["rates"],
    )
    m.record_macro_state(
        date="2026-03-15", vix_level=25.0, macro_call="risk-off",
        sector_thesis="Q1 sell-off", key_themes=["inflation"],
    )
    m.record_macro_state(
        date="2026-04-20", vix_level=18.0, macro_call="risk-on",
        sector_thesis="Recovery", key_themes=["earnings"],
    )
    # Analysis date is 2026-03-20 — must NOT include 2026-04-20 record
    records = m.get_recent(limit=10, as_of_date="2026-03-20")
    dates = [r["regime_date"] for r in records]
    assert "2026-04-20" not in dates
    assert "2026-03-15" in dates
    assert "2026-01-10" in dates

def test_build_macro_context_excludes_future(self, tmp_path):
    """build_macro_context(as_of_date=...) must not include future records in output."""
    m = MacroMemory(fallback_path=tmp_path / "macro.json")
    m.record_macro_state(
        date="2026-03-15", vix_level=25.0, macro_call="risk-off",
        sector_thesis="Q1 sell-off", key_themes=["inflation"],
    )
    m.record_macro_state(
        date="2026-04-20", vix_level=18.0, macro_call="risk-on",
        sector_thesis="Future recovery", key_themes=["earnings"],
    )
    ctx = m.build_macro_context(limit=10, as_of_date="2026-03-20")
    assert "Future recovery" not in ctx
    assert "Q1 sell-off" in ctx

def test_get_recent_no_as_of_date_returns_all(self, tmp_path):
    """get_recent() without as_of_date returns all records (backward-compat)."""
    m = MacroMemory(fallback_path=tmp_path / "macro.json")
    m.record_macro_state(
        date="2026-01-10", vix_level=20.0, macro_call="neutral",
        sector_thesis="Early", key_themes=[],
    )
    m.record_macro_state(
        date="2026-04-20", vix_level=18.0, macro_call="risk-on",
        sector_thesis="Late", key_themes=[],
    )
    records = m.get_recent(limit=10)
    assert len(records) == 2

def test_corrupt_local_file_logs_warning(self, tmp_path, caplog):
    """Corrupt local JSON must log a warning, not silently return []."""
    import logging
    bad_path = tmp_path / "corrupt.json"
    bad_path.write_text("{not valid json}", encoding="utf-8")
    m = MacroMemory(fallback_path=bad_path)
    with caplog.at_level(logging.WARNING, logger="tradingagents.memory.macro_memory"):
        records = m.get_recent(limit=5)
    assert records == []
    assert any("corrupt" in r.message.lower() or "malformed" in r.message.lower()
               for r in caplog.records)
```

- [ ] **Step 1.2: Run tests to verify they fail**

```bash
/opt/miniconda3/envs/tradingagents/bin/python -m pytest tests/unit/test_macro_memory.py::TestMacroMemoryLocalFallback::test_get_recent_excludes_future_records tests/unit/test_macro_memory.py::TestMacroMemoryLocalFallback::test_build_macro_context_excludes_future tests/unit/test_macro_memory.py::TestMacroMemoryLocalFallback::test_get_recent_no_as_of_date_returns_all tests/unit/test_macro_memory.py::TestMacroMemoryLocalFallback::test_corrupt_local_file_logs_warning -v
```

Expected: all 4 FAIL (missing parameter / wrong behavior).

- [ ] **Step 1.3: Implement `as_of_date` in `MacroMemory.get_recent()` and `_load_recent_local()`**

In `tradingagents/memory/macro_memory.py`, replace:

```python
def get_recent(self, limit: int = 3) -> list[dict[str, Any]]:
    """Return most recent macro states, newest first.

    Args:
        limit: Maximum number of results.
    """
    if self._col is not None:
        from pymongo import DESCENDING

        cursor = (
            self._col.find(
                {},
                {"_id": 0},
            )
            .sort("regime_date", DESCENDING)
            .limit(limit)
        )
        return list(cursor)
    else:
        return self._load_recent_local(limit)
```

With:

```python
def get_recent(
    self, limit: int = 3, *, as_of_date: str | None = None
) -> list[dict[str, Any]]:
    """Return most recent macro states, newest first.

    Args:
        limit:       Maximum number of results.
        as_of_date:  ISO date string (YYYY-MM-DD). When provided, only records
                     with ``regime_date <= as_of_date`` are returned. This
                     prevents future context leakage in backtests.
    """
    if self._col is not None:
        from pymongo import DESCENDING

        query: dict[str, Any] = {}
        if as_of_date:
            query["regime_date"] = {"$lte": as_of_date}
        cursor = (
            self._col.find(query, {"_id": 0})
            .sort("regime_date", DESCENDING)
            .limit(limit)
        )
        return list(cursor)
    else:
        return self._load_recent_local(limit, as_of_date=as_of_date)
```

Also replace `_load_recent_local` and `_load_all_local`:

```python
def _load_all_local(self) -> list[dict[str, Any]]:
    """Load all records from the local JSON file."""
    if not self._fallback_path.exists():
        return []
    try:
        return json.loads(self._fallback_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "MacroMemory: local file %s is malformed or unreadable — returning empty: %s",
            self._fallback_path,
            exc,
        )
        return []

def _load_recent_local(
    self, limit: int, *, as_of_date: str | None = None
) -> list[dict[str, Any]]:
    """Load and sort all records by regime_date descending from the local file."""
    records = self._load_all_local()
    if as_of_date:
        records = [r for r in records if r.get("regime_date", "") <= as_of_date]
    records.sort(key=lambda r: r.get("regime_date", ""), reverse=True)
    return records[:limit]
```

- [ ] **Step 1.4: Add `as_of_date` to `build_macro_context()`**

Replace:

```python
def build_macro_context(self, limit: int = 3) -> str:
    ...
    recent = self.get_recent(limit=limit)
```

With:

```python
def build_macro_context(self, limit: int = 3, *, as_of_date: str | None = None) -> str:
    """Build a human-readable context string from recent macro states.
    ...
    Args:
        limit:       How many past states to include.
        as_of_date:  ISO date string. When provided, only states on or before
                     this date are included. Prevents future leakage in backtests.
    ...
    """
    recent = self.get_recent(limit=limit, as_of_date=as_of_date)
```

- [ ] **Step 1.5: Run tests to verify they pass**

```bash
/opt/miniconda3/envs/tradingagents/bin/python -m pytest tests/unit/test_macro_memory.py -v
```

Expected: all PASS.

- [ ] **Step 1.6: Commit**

```bash
git add tradingagents/memory/macro_memory.py tests/unit/test_macro_memory.py
git commit -m "feat: add as_of_date filter to MacroMemory to prevent future leakage"
```

---

## Task 2: Add `as_of_date` filter to `ReflexionMemory`

**Files:**
- Modify: `tradingagents/memory/reflexion.py`
- Test: `tests/unit/test_reflexion_memory.py`

- [ ] **Step 2.1: Write failing tests**

```python
# In tests/unit/test_reflexion_memory.py — add as new test functions

def test_get_history_excludes_future_decisions(tmp_path):
    """get_history(as_of_date=...) must not return decisions after that date."""
    m = ReflexionMemory(fallback_path=tmp_path / "reflexion.json")
    m.record_decision("AAPL", "2026-01-10", "BUY", "Jan call", run_id="r1")
    m.record_decision("AAPL", "2026-03-15", "HOLD", "Q1 hold", run_id="r2")
    m.record_decision("AAPL", "2026-04-20", "SELL", "Future sell", run_id="r3")

    history = m.get_history("AAPL", limit=10, as_of_date="2026-03-20")
    dates = [r["decision_date"] for r in history]
    assert "2026-04-20" not in dates
    assert "2026-03-15" in dates
    assert "2026-01-10" in dates

def test_build_context_excludes_future(tmp_path):
    """build_context(as_of_date=...) must not mention future decisions."""
    m = ReflexionMemory(fallback_path=tmp_path / "reflexion.json")
    m.record_decision("AAPL", "2026-03-15", "HOLD", "Q1 hold rationale", run_id="r1")
    m.record_decision("AAPL", "2026-04-20", "SELL", "Future sell rationale", run_id="r2")

    ctx = m.build_context("AAPL", limit=10, as_of_date="2026-03-20")
    assert "Future sell rationale" not in ctx
    assert "Q1 hold rationale" in ctx

def test_get_history_no_as_of_date_returns_all(tmp_path):
    """get_history() without as_of_date returns all decisions (backward-compat)."""
    m = ReflexionMemory(fallback_path=tmp_path / "reflexion.json")
    m.record_decision("AAPL", "2026-01-10", "BUY", "Early", run_id="r1")
    m.record_decision("AAPL", "2026-04-20", "SELL", "Late", run_id="r2")
    history = m.get_history("AAPL", limit=10)
    assert len(history) == 2

def test_corrupt_local_reflexion_logs_warning(tmp_path, caplog):
    """Corrupt local JSON must log a warning, not silently return []."""
    import logging
    bad_path = tmp_path / "corrupt_reflexion.json"
    bad_path.write_text("[{broken", encoding="utf-8")
    m = ReflexionMemory(fallback_path=bad_path)
    with caplog.at_level(logging.WARNING, logger="tradingagents.memory.reflexion"):
        history = m.get_history("AAPL")
    assert history == []
    assert any("corrupt" in r.message.lower() or "malformed" in r.message.lower()
               for r in caplog.records)
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
/opt/miniconda3/envs/tradingagents/bin/python -m pytest tests/unit/test_reflexion_memory.py::test_get_history_excludes_future_decisions tests/unit/test_reflexion_memory.py::test_build_context_excludes_future tests/unit/test_reflexion_memory.py::test_get_history_no_as_of_date_returns_all tests/unit/test_reflexion_memory.py::test_corrupt_local_reflexion_logs_warning -v
```

Expected: all 4 FAIL.

- [ ] **Step 2.3: Implement `as_of_date` in `ReflexionMemory.get_history()` and `_load_local()`**

In `tradingagents/memory/reflexion.py`, replace `get_history`:

```python
def get_history(
    self,
    ticker: str,
    limit: int = 10,
    *,
    as_of_date: str | None = None,
) -> list[dict[str, Any]]:
    """Return the most recent decisions for *ticker*, newest first.

    Args:
        ticker:      Ticker symbol.
        limit:       Maximum number of results.
        as_of_date:  ISO date string (YYYY-MM-DD). When provided, only decisions
                     with ``decision_date <= as_of_date`` are returned. Prevents
                     future leakage in backtests.
    """
    if self._col is not None:
        from pymongo import DESCENDING

        query: dict[str, Any] = {"ticker": ticker.upper()}
        if as_of_date:
            query["decision_date"] = {"$lte": as_of_date}
        cursor = (
            self._col.find(query, {"_id": 0})
            .sort("decision_date", DESCENDING)
            .limit(limit)
        )
        return list(cursor)
    else:
        return self._load_local(ticker.upper(), limit, as_of_date=as_of_date)
```

Replace `_load_all_local` to warn on corruption:

```python
def _load_all_local(self) -> list[dict[str, Any]]:
    """Load all records from the local JSON file."""
    if not self._fallback_path.exists():
        return []
    try:
        return json.loads(self._fallback_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "ReflexionMemory: local file %s is malformed or unreadable — returning empty: %s",
            self._fallback_path,
            exc,
        )
        return []
```

Replace `_load_local` to accept `as_of_date`:

```python
def _load_local(
    self, ticker: str, limit: int, *, as_of_date: str | None = None
) -> list[dict[str, Any]]:
    """Load and filter records for a ticker from the local file."""
    records = self._load_all_local()
    filtered = [r for r in records if r.get("ticker") == ticker]
    if as_of_date:
        filtered = [r for r in filtered if r.get("decision_date", "") <= as_of_date]
    filtered.sort(key=lambda r: r.get("decision_date", ""), reverse=True)
    return filtered[:limit]
```

- [ ] **Step 2.4: Add `as_of_date` to `build_context()`**

Replace:

```python
def build_context(self, ticker: str, limit: int = 3) -> str:
    ...
    history = self.get_history(ticker, limit=limit)
```

With:

```python
def build_context(
    self, ticker: str, limit: int = 3, *, as_of_date: str | None = None
) -> str:
    """Build a human-readable context string from past decisions.
    ...
    Args:
        ticker:      Ticker symbol.
        limit:       How many past decisions to include.
        as_of_date:  ISO date string. When provided, only decisions on or before
                     this date are included. Prevents future leakage in backtests.
    ...
    """
    history = self.get_history(ticker, limit=limit, as_of_date=as_of_date)
```

- [ ] **Step 2.5: Run tests to verify they pass**

```bash
/opt/miniconda3/envs/tradingagents/bin/python -m pytest tests/unit/test_reflexion_memory.py -v
```

Expected: all PASS.

- [ ] **Step 2.6: Commit**

```bash
git add tradingagents/memory/reflexion.py tests/unit/test_reflexion_memory.py
git commit -m "feat: add as_of_date filter to ReflexionMemory to prevent future leakage"
```

---

## Task 3: Forward `analysis_date` to memory calls in summary agents

**Files:**
- Modify: `tradingagents/agents/portfolio/macro_summary_agent.py`
- Modify: `tradingagents/agents/portfolio/micro_summary_agent.py`
- Test: `tests/unit/test_summary_agents.py`

- [ ] **Step 3.1: Write failing tests**

```python
# In tests/unit/test_summary_agents.py — add new test class

class TestSummaryAgentMemoryFiltering:
    """Verify that summary agents forward analysis_date as as_of_date to memory."""

    def test_macro_summary_forwards_date_to_memory(self):
        """macro_summary_agent must call build_macro_context(as_of_date=analysis_date)."""
        from unittest.mock import MagicMock, patch
        from tradingagents.agents.portfolio.macro_summary_agent import create_macro_summary_agent

        mock_memory = MagicMock()
        mock_memory.build_macro_context.return_value = "past context"

        fake_llm_response = MagicMock()
        fake_llm_response.content = "MACRO REGIME: neutral\nKEY NUMBERS: VIX 20\nTOP 3 THEMES:\n1. t\n2. t\n3. t\nMACRO-ALIGNED TICKERS: none\nREGIME MEMORY NOTE: none"
        mock_llm = MagicMock()
        mock_llm.__or__ = MagicMock(return_value=MagicMock(invoke=MagicMock(return_value=fake_llm_response)))

        node = create_macro_summary_agent(mock_llm, macro_memory=mock_memory)

        state = {
            "analysis_date": "2026-03-20",
            "scan_summary": {
                "executive_summary": "Test summary",
                "macro_context": {},
                "key_themes": [],
                "stocks_to_investigate": [],
                "risk_factors": [],
            },
            "messages": [],
        }
        node(state)

        mock_memory.build_macro_context.assert_called_once()
        call_kwargs = mock_memory.build_macro_context.call_args
        assert call_kwargs.kwargs.get("as_of_date") == "2026-03-20"

    def test_micro_summary_forwards_date_to_memory(self):
        """micro_summary_agent must call build_context(as_of_date=analysis_date) per ticker."""
        from unittest.mock import MagicMock
        from tradingagents.agents.portfolio.micro_summary_agent import create_micro_summary_agent

        mock_memory = MagicMock()
        mock_memory.build_context.return_value = "ticker context"

        fake_result = MagicMock()
        fake_result.content = "HOLDINGS TABLE:\n| TICKER | ACTION | KEY NUMBER | FLAG | MEMORY |\n|--------|--------|------------|------|--------|\nCANDIDATES TABLE:\n| TICKER | CONVICTION | THESIS ANGLE | KEY NUMBER | FLAG | MEMORY |\n|--------|------------|--------------|------------|------|--------|"
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = fake_result
        mock_llm = MagicMock()
        mock_llm.__or__ = MagicMock(return_value=mock_chain)

        node = create_micro_summary_agent(mock_llm, micro_memory=mock_memory)

        import json
        state = {
            "analysis_date": "2026-03-20",
            "holding_reviews": json.dumps({"AAPL": {"recommendation": "HOLD", "confidence": "high"}}),
            "prioritized_candidates": "[]",
            "ticker_analyses": {},
            "messages": [],
        }
        node(state)

        mock_memory.build_context.assert_called()
        for call in mock_memory.build_context.call_args_list:
            assert call.kwargs.get("as_of_date") == "2026-03-20"
```

- [ ] **Step 3.2: Run tests to verify they fail**

```bash
/opt/miniconda3/envs/tradingagents/bin/python -m pytest tests/unit/test_summary_agents.py::TestSummaryAgentMemoryFiltering -v
```

Expected: FAIL — `build_macro_context` called without `as_of_date`.

- [ ] **Step 3.3: Update `macro_summary_agent.py` to pass `as_of_date`**

In `tradingagents/agents/portfolio/macro_summary_agent.py`, inside `macro_summary_node`, replace:

```python
        if macro_memory is not None:
            past_context = macro_memory.build_macro_context(limit=3)
```

With:

```python
        if macro_memory is not None:
            past_context = macro_memory.build_macro_context(
                limit=3, as_of_date=state.get("analysis_date") or None
            )
```

- [ ] **Step 3.4: Update `micro_summary_agent.py` to pass `as_of_date`**

In `tradingagents/agents/portfolio/micro_summary_agent.py`, inside `micro_summary_node`, replace:

```python
        if micro_memory is not None:
            for ticker in all_tickers:
                ticker_memory_dict[ticker] = micro_memory.build_context(ticker, limit=2)
```

With:

```python
        if micro_memory is not None:
            for ticker in all_tickers:
                ticker_memory_dict[ticker] = micro_memory.build_context(
                    ticker, limit=2, as_of_date=analysis_date or None
                )
```

- [ ] **Step 3.5: Run tests to verify they pass**

```bash
/opt/miniconda3/envs/tradingagents/bin/python -m pytest tests/unit/test_summary_agents.py -v
```

Expected: all PASS.

- [ ] **Step 3.6: Commit**

```bash
git add tradingagents/agents/portfolio/macro_summary_agent.py tradingagents/agents/portfolio/micro_summary_agent.py tests/unit/test_summary_agents.py
git commit -m "feat: forward analysis_date as as_of_date to macro and micro memory calls"
```

---

## Task 4: Seed `run_id` in `PortfolioGraph.run()`

**Files:**
- Modify: `tradingagents/graph/portfolio_graph.py`
- Test: `tests/unit/test_portfolio_graph_state.py`

- [ ] **Step 4.1: Write failing test**

```python
# In tests/unit/test_portfolio_graph_state.py — add new test class or functions

class TestPortfolioGraphRunIdProvenance:
    """run_id must be seeded into state so memory persistence carries run provenance."""

    def test_run_seeds_provided_run_id(self):
        """PortfolioGraph.run(run_id=...) must include run_id in initial state."""
        from unittest.mock import MagicMock, patch

        # Patch graph.invoke to capture the state it receives
        captured = {}

        def fake_invoke(state):
            captured.update(state)
            return state

        with patch("tradingagents.graph.portfolio_graph.PortfolioGraph.__init__", return_value=None):
            pg = object.__new__(__import__("tradingagents.graph.portfolio_graph", fromlist=["PortfolioGraph"]).PortfolioGraph)
            pg.debug = False
            mock_graph = MagicMock()
            mock_graph.invoke.side_effect = fake_invoke
            pg.graph = mock_graph

            pg.run(
                portfolio_id="port-1",
                date="2026-03-20",
                prices={"AAPL": 180.0},
                scan_summary={"executive_summary": "test"},
                run_id="run-abc-123",
            )

        assert captured.get("run_id") == "run-abc-123"

    def test_run_generates_run_id_when_not_provided(self):
        """PortfolioGraph.run() without run_id must auto-generate a non-empty run_id."""
        from unittest.mock import MagicMock, patch

        captured = {}

        def fake_invoke(state):
            captured.update(state)
            return state

        with patch("tradingagents.graph.portfolio_graph.PortfolioGraph.__init__", return_value=None):
            pg = object.__new__(__import__("tradingagents.graph.portfolio_graph", fromlist=["PortfolioGraph"]).PortfolioGraph)
            pg.debug = False
            mock_graph = MagicMock()
            mock_graph.invoke.side_effect = fake_invoke
            pg.graph = mock_graph

            pg.run(
                portfolio_id="port-1",
                date="2026-03-20",
                prices={},
                scan_summary={},
            )

        run_id = captured.get("run_id")
        assert run_id and isinstance(run_id, str) and len(run_id) > 0
```

- [ ] **Step 4.2: Run tests to verify they fail**

```bash
/opt/miniconda3/envs/tradingagents/bin/python -m pytest tests/unit/test_portfolio_graph_state.py::TestPortfolioGraphRunIdProvenance -v
```

Expected: FAIL — `run()` doesn't accept `run_id`, `captured` has no `run_id` key.

- [ ] **Step 4.3: Add `run_id` parameter to `PortfolioGraph.run()`**

In `tradingagents/graph/portfolio_graph.py`, replace:

```python
    def run(
        self,
        portfolio_id: str,
        date: str,
        prices: dict[str, float],
        scan_summary: dict[str, Any],
    ) -> dict[str, Any]:
        """Run the full portfolio manager workflow.

        Args:
            portfolio_id: ID of the portfolio to manage.
            date: Analysis date string (YYYY-MM-DD).
            prices: Current EOD prices (ticker → price).
            scan_summary: Macro scan output from ScannerGraph (contains
                          ``stocks_to_investigate`` and optionally
                          ``price_histories``).

        Returns:
            Final LangGraph state dict containing all workflow outputs.
        """
        initial_state: dict[str, Any] = {
            "portfolio_id": portfolio_id,
            "analysis_date": date,
            "prices": prices,
            "scan_summary": scan_summary,
            "messages": [],
            "portfolio_data": "",
            "risk_metrics": "",
            "holding_reviews": "",
            "prioritized_candidates": "",
            "macro_brief": "",
            "micro_brief": "",
            "macro_memory_context": "",
            "micro_memory_context": "",
            "pm_decision": "",
            "cash_sweep": "",
            "execution_result": "",
            "sender": "",
            "ticker_analyses": {},
        }
```

With:

```python
    def run(
        self,
        portfolio_id: str,
        date: str,
        prices: dict[str, float],
        scan_summary: dict[str, Any],
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Run the full portfolio manager workflow.

        Args:
            portfolio_id: ID of the portfolio to manage.
            date:         Analysis date string (YYYY-MM-DD).
            prices:       Current EOD prices (ticker → price).
            scan_summary: Macro scan output from ScannerGraph.
            run_id:       Optional run identifier for traceability. Auto-generated
                          (UUID4) when not provided so memory records always carry
                          run provenance.

        Returns:
            Final LangGraph state dict containing all workflow outputs.
        """
        import uuid
        effective_run_id = run_id if run_id else str(uuid.uuid4())
        initial_state: dict[str, Any] = {
            "portfolio_id": portfolio_id,
            "analysis_date": date,
            "prices": prices,
            "scan_summary": scan_summary,
            "run_id": effective_run_id,
            "messages": [],
            "portfolio_data": "",
            "risk_metrics": "",
            "holding_reviews": "",
            "prioritized_candidates": "",
            "macro_brief": "",
            "micro_brief": "",
            "macro_memory_context": "",
            "micro_memory_context": "",
            "pm_decision": "",
            "cash_sweep": "",
            "execution_result": "",
            "sender": "",
            "ticker_analyses": {},
        }
```

- [ ] **Step 4.4: Run tests to verify they pass**

```bash
/opt/miniconda3/envs/tradingagents/bin/python -m pytest tests/unit/test_portfolio_graph_state.py -v
```

Expected: all PASS.

- [ ] **Step 4.5: Commit**

```bash
git add tradingagents/graph/portfolio_graph.py tests/unit/test_portfolio_graph_state.py
git commit -m "feat: seed run_id into PortfolioGraph initial state for memory provenance"
```

---

## Task 5: Write PM decisions to `micro_reflexion` after execution

**Files:**
- Modify: `tradingagents/graph/portfolio_setup.py`
- Test: `tests/portfolio/test_portfolio_setup.py`

- [ ] **Step 5.1: Write failing test**

```python
# In tests/portfolio/test_portfolio_setup.py — add new test class

class TestRecordPmDecisionsNode:
    """record_pm_decisions_node must write buy/sell/hold decisions to micro_memory."""

    def _make_state(self, pm_decision: dict) -> dict:
        import json
        return {
            "portfolio_id": "port-1",
            "analysis_date": "2026-03-20",
            "run_id": "run-test-123",
            "pm_decision": json.dumps(pm_decision),
            "prices": {},
            "messages": [],
            "portfolio_data": "{}",
            "risk_metrics": "{}",
            "holding_reviews": "{}",
            "prioritized_candidates": "[]",
            "macro_brief": "",
            "micro_brief": "",
            "macro_memory_context": "",
            "micro_memory_context": "",
            "cash_sweep": "",
            "execution_result": "{}",
            "sender": "",
            "ticker_analyses": {},
        }

    def test_records_buy_decision(self):
        """BUY orders must be written to micro_memory as BUY decisions."""
        from unittest.mock import MagicMock
        from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

        mock_memory = MagicMock()
        setup = PortfolioGraphSetup(agents={}, repo=None, config={}, micro_memory=mock_memory)
        node = setup._make_record_pm_decisions_node()

        state = self._make_state({
            "buys": [{"ticker": "XOM", "rationale": "Energy play", "shares": 5.0, "entry_price": 118.0, "limit_price": 120.0, "max_chase_price": 120.0, "order_type": "limit", "valid_as_of": "2026-03-20", "price_target": 120.0, "stop_loss": 108.0, "take_profit": 138.0, "sector": "Energy", "thesis": "Oil", "macro_alignment": "risk-off", "memory_note": "", "position_sizing_logic": "2%"}],
            "sells": [],
            "holds": [],
        })

        node(state)

        mock_memory.record_decision.assert_any_call(
            "XOM", "2026-03-20", "BUY",
            rationale="Energy play",
            confidence="high",
            source="portfolio",
            run_id="run-test-123",
        )

    def test_records_sell_decision(self):
        """SELL orders must be written to micro_memory as SELL decisions."""
        from unittest.mock import MagicMock
        from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

        mock_memory = MagicMock()
        setup = PortfolioGraphSetup(agents={}, repo=None, config={}, micro_memory=mock_memory)
        node = setup._make_record_pm_decisions_node()

        state = self._make_state({
            "buys": [],
            "sells": [{"ticker": "AAPL", "rationale": "Overvalued", "shares": 10.0, "macro_driven": True}],
            "holds": [],
        })
        node(state)

        mock_memory.record_decision.assert_any_call(
            "AAPL", "2026-03-20", "SELL",
            rationale="Overvalued",
            confidence="medium",
            source="portfolio",
            run_id="run-test-123",
        )

    def test_records_hold_decision(self):
        """HOLD decisions must be written to micro_memory as HOLD decisions."""
        from unittest.mock import MagicMock
        from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

        mock_memory = MagicMock()
        setup = PortfolioGraphSetup(agents={}, repo=None, config={}, micro_memory=mock_memory)
        node = setup._make_record_pm_decisions_node()

        state = self._make_state({
            "buys": [],
            "sells": [],
            "holds": [{"ticker": "MSFT", "rationale": "Thesis intact"}],
        })
        node(state)

        mock_memory.record_decision.assert_any_call(
            "MSFT", "2026-03-20", "HOLD",
            rationale="Thesis intact",
            confidence="medium",
            source="portfolio",
            run_id="run-test-123",
        )

    def test_no_memory_no_crash(self):
        """record_pm_decisions_node must not crash when micro_memory is None."""
        from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

        setup = PortfolioGraphSetup(agents={}, repo=None, config={}, micro_memory=None)
        node = setup._make_record_pm_decisions_node()
        state = self._make_state({"buys": [], "sells": [], "holds": []})
        result = node(state)  # must not raise
        assert isinstance(result, dict)

    def test_memory_failure_does_not_crash_pipeline(self):
        """record_pm_decisions_node must not propagate exceptions from micro_memory."""
        from unittest.mock import MagicMock
        from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

        mock_memory = MagicMock()
        mock_memory.record_decision.side_effect = RuntimeError("DB unavailable")
        setup = PortfolioGraphSetup(agents={}, repo=None, config={}, micro_memory=mock_memory)
        node = setup._make_record_pm_decisions_node()

        state = self._make_state({
            "buys": [{"ticker": "XOM", "rationale": "test", "shares": 5.0, "entry_price": 118.0, "limit_price": 120.0, "max_chase_price": 120.0, "order_type": "limit", "valid_as_of": "2026-03-20", "price_target": 120.0, "stop_loss": 108.0, "take_profit": 138.0, "sector": "Energy", "thesis": "Oil", "macro_alignment": "risk-off", "memory_note": "", "position_sizing_logic": "2%"}],
            "sells": [],
            "holds": [],
        })
        result = node(state)  # must not raise
        assert isinstance(result, dict)
```

- [ ] **Step 5.2: Run tests to verify they fail**

```bash
/opt/miniconda3/envs/tradingagents/bin/python -m pytest tests/portfolio/test_portfolio_setup.py::TestRecordPmDecisionsNode -v
```

Expected: FAIL — `_make_record_pm_decisions_node` does not exist.

- [ ] **Step 5.3: Implement `_make_record_pm_decisions_node()` in `PortfolioGraphSetup`**

In `tradingagents/graph/portfolio_setup.py`, add this factory method to `PortfolioGraphSetup` (after `_make_execute_trades_node`):

```python
    def _make_record_pm_decisions_node(self) -> Callable[[PortfolioManagerState], dict[str, Any]]:
        micro_memory = self._micro_memory

        def record_pm_decisions_node(state: PortfolioManagerState) -> dict[str, Any]:
            """Write final PM decisions to micro_reflexion memory.

            Runs after execute_trades. Fails silently — memory persistence
            must never break the portfolio pipeline.
            """
            if micro_memory is None:
                return {"sender": "record_pm_decisions"}

            analysis_date = state.get("analysis_date") or ""
            run_id = state.get("run_id")
            pm_decision_str = state.get("pm_decision") or "{}"

            try:
                decisions = json.loads(pm_decision_str)
            except (json.JSONDecodeError, TypeError):
                logger.warning("record_pm_decisions_node: could not parse pm_decision JSON")
                return {"sender": "record_pm_decisions"}

            buys = decisions.get("buys") or []
            sells = decisions.get("sells") or []
            holds = decisions.get("holds") or []

            for order in buys:
                ticker = (order.get("ticker") or "").strip().upper()
                if not ticker:
                    continue
                try:
                    micro_memory.record_decision(
                        ticker, analysis_date, "BUY",
                        rationale=order.get("rationale") or "",
                        confidence="high",
                        source="portfolio",
                        run_id=run_id,
                    )
                except Exception:
                    logger.warning(
                        "record_pm_decisions_node: failed to record BUY for %s", ticker,
                        exc_info=True,
                    )

            for order in sells:
                ticker = (order.get("ticker") or "").strip().upper()
                if not ticker:
                    continue
                try:
                    micro_memory.record_decision(
                        ticker, analysis_date, "SELL",
                        rationale=order.get("rationale") or "",
                        confidence="medium",
                        source="portfolio",
                        run_id=run_id,
                    )
                except Exception:
                    logger.warning(
                        "record_pm_decisions_node: failed to record SELL for %s", ticker,
                        exc_info=True,
                    )

            for order in holds:
                ticker = (order.get("ticker") or "").strip().upper()
                if not ticker:
                    continue
                try:
                    micro_memory.record_decision(
                        ticker, analysis_date, "HOLD",
                        rationale=order.get("rationale") or "",
                        confidence="medium",
                        source="portfolio",
                        run_id=run_id,
                    )
                except Exception:
                    logger.warning(
                        "record_pm_decisions_node: failed to record HOLD for %s", ticker,
                        exc_info=True,
                    )

            return {"sender": "record_pm_decisions"}

        return record_pm_decisions_node
```

- [ ] **Step 5.4: Wire `record_pm_decisions` into the graph after `execute_trades`**

In `tradingagents/graph/portfolio_setup.py`, inside `setup_graph()`, find where `execute_trades` is registered and add the new node. Replace the existing topology wiring section:

```python
        workflow.add_node("execute_trades", self.agents.get("execute_trades") or self._make_execute_trades_node())
```

With:

```python
        workflow.add_node("execute_trades", self.agents.get("execute_trades") or self._make_execute_trades_node())
        workflow.add_node("record_pm_decisions", self._make_record_pm_decisions_node())
```

Find the edge that connects `execute_trades` to `END` and change it to route through `record_pm_decisions` first. Look for:

```python
        workflow.add_edge("execute_trades", END)
```

Replace with:

```python
        workflow.add_edge("execute_trades", "record_pm_decisions")
        workflow.add_edge("record_pm_decisions", END)
```

- [ ] **Step 5.5: Run tests to verify they pass**

```bash
/opt/miniconda3/envs/tradingagents/bin/python -m pytest tests/portfolio/test_portfolio_setup.py -v
```

Expected: all PASS.

- [ ] **Step 5.6: Commit**

```bash
git add tradingagents/graph/portfolio_setup.py tests/portfolio/test_portfolio_setup.py
git commit -m "feat: write PM buy/sell/hold decisions to micro_reflexion after execution"
```

---

## Task 6: Full regression run

**Files:** None (verification only)

- [ ] **Step 6.1: Run the full non-integration test suite**

```bash
/opt/miniconda3/envs/tradingagents/bin/python -m pytest tests/ -v -m "not integration" 2>&1 | tail -20
```

Expected: all PASS, no regressions.

- [ ] **Step 6.2: Run the specific review verification suite**

```bash
/opt/miniconda3/envs/tradingagents/bin/python -m pytest tests/unit/test_pydantic_schema.py tests/unit/test_summary_agents.py tests/portfolio/test_portfolio_setup.py tests/unit/test_output_validation.py tests/unit/test_macro_memory.py tests/unit/test_reflexion_memory.py tests/unit/test_portfolio_graph_state.py -v
```

Expected: all PASS.

- [ ] **Step 6.3: Final commit if anything was missed**

```bash
git status
# stage and commit any remaining changes
```
