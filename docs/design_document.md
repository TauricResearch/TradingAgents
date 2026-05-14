# Design Document: Productization & Hybrid UI Architecture

## Objective
Evolve the TradingAgents CLI framework into a multi-user, productized web application. This involves optimizing the underlying LangGraph pipeline for speed, enabling modular independent agent execution, and introducing a database for multi-tenancy, authentication, and user-isolated memory.

## Scope & Impact
- **LangGraph Orchestration (`tradingagents/graph/setup.py`)**: Refactoring from a sequential chain to a parallel fan-out/fan-in architecture. Adding early-exit (`standalone`) capabilities.
- **Backend API (`ui/backend/main.py`)**: Enhancing the job triggering mechanism to pass specific analyst targets to Kubernetes jobs. Integrating database sessions and authentication.
- **Database Layer**: Introducing PostgreSQL with an ORM (SQLAlchemy) to handle user profiles, session tracking, job metadata, and user-isolated memory logs.
- **CLI/Entrypoint (`cli/main.py`)**: Exposing new arguments (`--analysts`, `--standalone`) to facilitate targeted execution by the backend.

## Proposed Solution: The Hybrid Architecture

### 1. The Execution Engine (Parallel & Modular Graph)
- **Parallel Analysts**: Market, Sentiment, News, and Fundamentals analysts will fan-out and execute concurrently. This reduces the initial data-gathering and reporting phase from ~4-5 minutes down to ~60-90 seconds.
- **Modular Paths**: The graph will accept a `standalone` flag and an `analysts` list. If `standalone=True`, the graph processes only the requested analysts and routes directly to the `END` node, skipping the Research Manager and Trading Teams.
- **Headless K8s Jobs**: The UI backend will trigger ephemeral Kubernetes Jobs matching the user's specific workflow configuration.

### 2. The Database Strategy
- **System**: PostgreSQL (Pre-existing instance will be used).
- **Core Entities**:
  - `User`: Handles authentication and profiles.
  - `JobMeta`: Tracks Kubernetes Job IDs, requested tickers, requested analysts, and status (Pending, Running, Completed, Failed).
  - `Portfolio`: User-isolated watchlists (replacing the global `portfolio.txt`).
  - `MemoryLog`: User-isolated historical decisions and alpha returns (replacing the global `trading_memory.md`).
- **Heavy Data**: Markdown reports and JSON states will continue to live in the Longhorn shared volume (or an S3-compatible store). The DB will only store reference URIs to these files.
