# Handoff Report: End-to-End (E2E) Test Architecture for Continuous Trading Analyst MVP

## Executive Summary
This report analyzes `advanced_agent.py` and the existing tests in `tests/` to establish a blueprint for testing the continuous trading analyst MVP. It recommends an isolated, deterministic, and crash-resilient E2E test structure leveraging stateful LLM mocking, localized directory containment, and controlled queue-driven event loops.

---

## 1. Observation

### Agent Architecture and Dependencies
- **Entry Point & Flow**: `AdvancedTradingAgent.run()` (in `advanced_agent.py:45`) orchestrates stock selection, runs a graph analysis, and synthesizes a final decision.
- **LLM Calls**:
  - `select_top_stocks` (in `advanced_agent.py:22`) invokes the LLM (`self.llm.invoke`) to select 1 stock ticker in JSON format.
  - `TradingAgentsGraph.propagate()` (in `trading_graph.py:321`) invokes multiple sub-agents and tool nodes within a `StateGraph`.
  - `AdvancedTradingAgent.run()` performs a final LLM invoke (`self.llm.invoke` at `advanced_agent.py:98`) to construct the allocation strategy.
- **I/O & Persistence**:
  - `advanced_agent_history.json` is loaded and saved directly under `self.config["results_dir"]` (in `advanced_agent.py:75-115`).
  - `full_states_log_{trade_date}.json` is saved under `self.config["results_dir"] / safe_ticker / "TradingAgentsStrategy_logs"` (in `trading_graph.py:454-460`).
  - `TradingMemoryLog` (in `tradingagents/agents/utils/memory.py`) manages an append-only markdown log file under `self.config["memory_log_path"]`.
  - Crash-resilient checkpointer (`SqliteSaver`) is conditionally compiled for the graph using `self.config["data_cache_dir"]` (in `trading_graph.py:337-342`).

### Existing Test Patterns in `tests/`
- **LLM Mocking**:
  - `tests/conftest.py:58-66` defines `mock_llm_client`, which monkeypatches the factory:
    ```python
    @pytest.fixture()
    def mock_llm_client():
        client = MagicMock()
        client.get_llm.return_value = MagicMock()
        with patch("tradingagents.llm_clients.factory.create_llm_client", return_value=client):
            yield client
    ```
  - `tests/test_structured_agents.py:106-121` uses custom structured mock setups that bind `with_structured_output` to return typed Pydantic models (e.g. `TraderProposal` or `SentimentReport`) or fall back to free-text on errors.
- **Data & Configuration Isolation**:
  - `tests/conftest.py:38-55` resets global dataflows config between tests.
  - `tests/test_memory_log.py` utilizes pytest's `tmp_path` fixture to dynamically test file reads/writes on temporary paths.
- **Event Loop & Resume Behavior**:
  - `tests/test_checkpoint_resume.py` mocks a basic state graph and simulates a crash via a mutable global flag (`_should_crash`), testing that subsequent invocations successfully resume from the checkpointed state.

---

## 2. Logic Chain

1. **Deterministic E2E Verification**: The agent undergoes sequential LLM interactions (stock selection -> sub-agent propagation -> final decision). E2E tests cannot query live APIs due to cost, performance, and non-determinism. Therefore, E2E tests must intercept all internal LLM calls via a stateful Mock LLM Router that inspects prompt contents to return appropriate mock outputs (e.g., JSON lists, Pydantic objects, or final markdown text).
2. **Concurrent & Isolated Logging Verification**: The agent writes history files, state logs, and markdown memories to disk. By default, these paths default to the user's home directory (`~/.tradingagents`). To prevent test leakage and allow concurrent execution, tests must dynamically construct a dictionary pointing these settings to a temporary folder (`tmp_path`), allowing direct assertion on file creation and contents.
3. **Continuous Execution Testing**: A continuous trading analyst MVP processes ticks/events in a loop. Running an unconstrained `while True` loop hangs tests. To verify the event loop, it must be designed with test hooks: either a queue-draining mechanism that exits when empty, a `max_cycles` parameter, or a stop event. Fast-forwarding sleeps using mocked time ensures fast execution.
4. **Crash-Resilience Integration**: Since the main agent graph supports checkpointing, E2E tests must verify the resume cycle by forcing an error midway through execution, confirming the database checkpoint exists, and resuming the execution to check that final states are computed without duplicate node runs.

---

## 3. Caveats
- **Historical Backtesting vs E2E**: This recommendation covers system-level integration (E2E) testing. It assumes actual Yahoo Finance (`yfinance`) calls made by tools (e.g., return fetching in Phase B) are mocked out or use local caching so tests do not hit the live internet.
- **External Message Brokers**: If the continuous analyst MVP uses an external broker (like Redis or RabbitMQ) for event delivery, those must be mocked or tested using lightweight in-memory replacements (like `mockredis`).

---

## 4. Conclusion & Recommendations

For the continuous trading analyst MVP, structure the E2E tests using the following components:

### A. E2E Test Directory Layout
```
tests/
├── e2e/
│   ├── __init__.py
│   ├── conftest.py  # E2E-specific fixtures
│   └── test_continuous_trading_analyst.py  # The E2E scenarios
```

### B. LLM Mocking Strategy
Create a `StatefulMockLLM` that intercepts standard `invoke` and `with_structured_output` calls, routing them based on prompt matching:

```python
import json
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage
from tradingagents.agents.schemas import SentimentReport, SentimentBand, ResearchPlan, TraderProposal, TraderAction, PortfolioRating

class StatefulMockLLM:
    def __init__(self):
        self.invocations = []
        
    def invoke(self, messages, *args, **kwargs):
        prompt = str(messages)
        self.invocations.append(prompt)
        
        # 1. Stock Selection
        if "Select exactly 1 stock ticker" in prompt:
            return AIMessage(content='["AAPL"]')
            
        # 2. Final Decision Synthesis
        if "allocation strategy" in prompt:
            return AIMessage(content="FINAL TRANSACTION PROPOSAL: **BUY** AAPL. Allocate 10% cash.")
            
        return AIMessage(content="Default mock textual response.")

    def with_structured_output(self, schema, *args, **kwargs):
        mock_runnable = MagicMock()
        
        def structured_invoke(messages, *args, **kwargs):
            prompt = str(messages)
            self.invocations.append(prompt)
            
            # Match schema type to return appropriate dummy Pydantic objects
            if "SentimentReport" in str(schema):
                return SentimentReport(
                    overall_band=SentimentBand.BULLISH,
                    overall_score=8.5,
                    confidence="high",
                    narrative="Market sentiment is overwhelmingly bullish."
                )
            if "ResearchPlan" in str(schema):
                return ResearchPlan(
                    recommendation=PortfolioRating.OVERWEIGHT,
                    rationale="Sound fundamentals.",
                    strategic_actions="Gradually build position."
                )
            if "TraderProposal" in str(schema):
                return TraderProposal(
                    action=TraderAction.BUY,
                    reasoning="Support level held."
                )
            return MagicMock()
            
        mock_runnable.invoke.side_effect = structured_invoke
        return mock_runnable
```

### C. Isolated Configuration & Assertion
Leverage pytest fixtures to completely isolate output directories:

```python
import pytest
import os
import json

@pytest.fixture
def e2e_config(tmp_path):
    return {
        "results_dir": str(tmp_path / "logs"),
        "data_cache_dir": str(tmp_path / "cache"),
        "memory_log_path": str(tmp_path / "memory" / "trading_memory.md"),
        "llm_provider": "openai",
        "deep_think_llm": "gpt-5.5",
        "quick_think_llm": "gpt-5.4-mini",
        "checkpoint_enabled": True
    }
```

Verify outputs exist and conform to schemas:
```python
def test_agent_outputs_created(e2e_config):
    # Run agent...
    # Assert files exist:
    history_file = os.path.join(e2e_config["results_dir"], "advanced_agent_history.json")
    assert os.path.exists(history_file)
    with open(history_file, "r") as f:
        history = json.load(f)
        assert len(history) > 0
        assert history[0]["selected_stocks"] == ["AAPL"]
```

### D. Event Loop Testing Strategy
Ensure the continuous loop coordinator takes a queue and termination controls:

```python
class ContinuousTradingAnalyst:
    def __init__(self, agent, event_queue, stop_event=None, max_cycles=None):
        self.agent = agent
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.max_cycles = max_cycles
        
    def start_loop(self):
        cycles = 0
        while not (self.stop_event and self.stop_event.is_set()):
            if self.max_cycles and cycles >= self.max_cycles:
                break
            try:
                event = self.event_queue.get(timeout=0.1)
                self.agent.run(event["portfolio"], event["date"])
                cycles += 1
            except queue.Empty:
                break
```

In the E2E test, mock `time.sleep` or use queue draining to run the loop synchronously:
```python
def test_continuous_analyst_loop(e2e_config):
    import queue
    event_queue = queue.Queue()
    event_queue.put({"portfolio": {"cash_usd": 10000}, "date": "2026-06-16"})
    
    agent = AdvancedTradingAgent(config=e2e_config)
    analyst = ContinuousTradingAnalyst(agent, event_queue, max_cycles=1)
    analyst.start_loop()
    
    # Assert queue was processed and logs were written
    assert event_queue.empty()
```

---

## 5. Verification Method

### How to Run Tests
Once the E2E tests are implemented:
1. Run E2E tests specifically using pytest:
   ```bash
   pytest tests/e2e/ -v
   ```
2. Verify no home-directory leakage occurs by ensuring `~/.tradingagents` is untouched during testing.
3. Validate checkpoint functionality by interrupting a running agent graph node (raising an exception in a mocked tool node) and verifying that re-running the test resumes from that node.
