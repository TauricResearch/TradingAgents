# Trading Experiments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add contributor-friendly opt-in research workflows around the existing trading graph.

**Architecture:** Keep `TradingAgentsGraph` as the single-ticker analysis service. Add focused modules under `tradingagents/experiments/`, wire semantic memory and optional visual context into the graph, and expose thin scripts.

**Tech Stack:** Python, SQLite, pandas, yfinance, Backtrader, matplotlib, LangChain messages.

---

### Task 1: Shared Offline Primitives

- [ ] Add failing tests for semantic retrieval, strategy rules, risk parity, and metrics.
- [ ] Implement SQLite hashed-vector memory, JSON rule storage, allocation helpers, and performance metrics.
- [ ] Run focused tests.

### Task 2: Graph Integration

- [ ] Add failing tests for graph semantic-memory lifecycle and prompt rule injection.
- [ ] Wire semantic decision storage, outcome resolution, similar-context retrieval, and rules into existing graph paths.
- [ ] Run focused tests.

### Task 3: Chart Analyst

- [ ] Add failing tests for chart rendering and multimodal message construction.
- [ ] Implement chart rendering and optional visual analysis before debate.
- [ ] Run focused tests.

### Task 4: Orchestration

- [ ] Add failing tests for rating mapping and portfolio coordination.
- [ ] Implement Backtrader simulation, portfolio coordinator, post-mortem generator, and thin scripts.
- [ ] Run focused tests.

### Task 5: Documentation And Verification

- [ ] Document experiment commands and configuration.
- [ ] Run experiment tests and the full test suite.
