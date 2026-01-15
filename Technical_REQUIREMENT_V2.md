# TRADING AGENT SYSTEM OVERHAUL: Technical Requirements Document (v3.0)

**Status:** ✅ COMPLETE / PRODUCTION-READY
**Objective:** The system is now a deterministic, institutional-grade decision engine.

---

## 1. CORE ARCHITECTURE: The Data Registrar (Immutable Reality)
**Goal:** Prevent hallucination, time-drift, and "dirty reads" by freezing the state of the world before any agent wakes up.

### 1.1. Canonical Data Fetching
- **Requirement:** The graph must execute a `DataRegistrar` node exactly once at the `START`.
- **Constraint:** Downstream agents (`Market`, `News`, `Fundamentals`) are **FORBIDDEN** from calling external data tools. They must strictly read from `state["fact_ledger"]`.
- **Scope:** The Registrar must fetch and bundle:
    - Price Data (OHLCV + Technicals)
    - Fundamental Data (Balance Sheet, Income, Cash Flow)
    - News & Sentiment (Raw text/JSON)
    - Insider Transactions

### 1.2. Cryptographic Auditability & Schema
- **Requirement:** The `FactLedger` must be cryptographically sealed and include explicit freshness metadata.

**Schema Definition:**
```json
{
  "ledger_id": "UUID-v4",
  "created_at": "ISO-8601 UTC Timestamp",
  "freshness": {
    "price_age_seconds": 32.5,       // Allow max 60s
    "fundamentals_age_hours": 6.0,   // Allow max 24h
    "news_age_hours": 1.0            // Allow max 4h
  },
  "source_versions": {
    "price": "yfinance_v2@2026-01-15T...",
    "news": "serper@2026-01-15T..."
  },
  "data_payload": { ... },           // The actual data content
  "hash": "SHA-256(data_payload)"    // Hash of PAYLOAD ONLY (Metadata excluded)
}
```

### 1.3. The "Fail-Fast" Kill Switch
- **Requirement:** If any critical data source fails or exceeds freshness limits:
    - The system must **ABORT IMMEDIATELY** (Raise Exception).
    - No LLM agents shall be invoked.
    - No partial degradation is allowed for trading decisions.

---

## 2. EXECUTION LAYER: The Omnipotent Gatekeeper
**Goal:** Separate "Decision Generation" (LLM) from "Decision Authorization" (Python). Stop the Trader from executing invalid or dangerous orders.

### 2.1. Machine-Readable Return Codes (Enums)
- **Requirement:** The Gatekeeper must return specific `ExecutionResult` Enums, never generic strings.

**Codes:**
- `APPROVED`: Trade passes all checks.
- `ABORT_COMPLIANCE`: Insider flag or restricted list hit.
- `ABORT_DATA_GAP`: Data found to be stale or missing during verification.
- `ABORT_LOW_CONFIDENCE`: Trader confidence < 0.7.
- `ABORT_DIVERGENCE`: Analyst disagreement exceeds threshold.
- `BLOCKED_TREND`: "Don't Fight the Tape" rule triggered.

### 2.2. Consensus Divergence Check (Normalized)
- **Requirement:** Quantify disagreement between Bull and Bear analysts to detect "Epistemic Uncertainty."
- **Formula:** `Divergence_Score = abs(Bull_Score - Bear_Score) * mean_confidence`

**Logic:**
- High Disagreement + High Confidence = **DANGER** (ABORT).
- High Disagreement + Low Confidence = **NOISE** (Ignore/Size Down).

### 2.3. Deterministic Trend Override (Counterfactuals)
- **Requirement:** Block "SELL" orders on high-growth assets in strong uptrends using `FactLedger` data.

**Logging Requirement:** When a trade is blocked, log the Counterfactual:
```json
{
  "event": "TRADE_BLOCKED",
  "rule": "STRONG_UPTREND_PROTECTION",
  "original_intent": "SELL 100 SHARES",
  "executed_action": "HOLD",
  "counterfactual_outcome": "Would have sold into a +30% growth/bull regime."
}
```

### 2.4. Abort Semantics
- **Constraint:** `ABORT` != `HOLD`.
    - `HOLD` is a strategic decision to do nothing.
    - `ABORT` is a system failure or safety trigger.
- **Action:** Aborted trades must trigger an alert to the `HumanReviewQueue` (log file or dashboard).

---

## 3. INTELLIGENCE LAYER: Bounded & Conditioned Learning
**Goal:** Prevent "Recency Bias" and "Overfitting" by forcing the Reflector to respect math and regimes.

### 3.1. Agent Attribution Scoring
- **Requirement:** The Reflector must assign performance scores to individual agents based on the outcome.
- **Constraint:** The sum of attribution scores (negative or positive) must not exceed 1.0. (Prevents "blaming everyone" for a single loss).

### 3.2. Regime-Conditioned Memory
- **Requirement:** Every memory/lesson must be tagged with the context in which it was learned.
```json
{ "lesson": "Tighten stops", "regime": "VOLATILE" }
```
- **Retrieval Rule:** The Trader may ONLY retrieve lessons that match the **Current Regime**. (e.g., Do not fetch "Bear Market" lessons during a "Bull Market").

### 3.3. Bounded Parameter Tuning (The Safety Rails)
- **Requirement:** Python code must validate all `UPDATE_PARAMETERS` suggestions from the LLM.

**Velocity Brake:** If a parameter is adjusted in the same direction for 3 consecutive sessions:
1. **FREEZE** that parameter.
2. Flag for Human Review.
*(Reason: Prevents runaway drift or "death-by-a-thousand-tweaks").*

---

## 4. OPERATIONAL SAFETY: The Human Loop
**Goal:** Operationalize human oversight so it isn't just a theoretical concept.

### 4.1. The "Cold" Review Path
- **Requirement:** The system must produce a `human_review.json` log file after every run.

**Content:**
- Any `ABORT_*` events.
- Any `BLOCKED_TREND` overrides.
- Any Parameter updates flagged by the Velocity Brake.
- Any Drift > 20% from baseline defaults.

### 4.2. Hard Stop
- **Requirement:** If the `cash_balance` drops by > 15% in a single session (simulation or live), the `DataRegistrar` MUST refuse to run subsequent sessions until a manual `reset_flags` command is issued.

---

## PHASE 1: THE FOUNDATION (Immutable Reality)
**Objective:** Eliminate hallucination and time-drift by implementing the Data Registrar and killing tool-usage downstream.

### 1.1. Core Schema & State
- **Define Enums:** Implement `ExecutionResult` (`APPROVED`, `ABORT_COMPLIANCE`, `ABORT_DATA_GAP`, etc.) to ensure machine-readable logs.
- **Define Ledger:** Implement `FactLedger` TypedDict with `freshness`, `source_versions`, and `content_hash`.
- **Immutability Guard:** Implement `write_once_enforce` reducer to trigger a hard crash if any agent attempts to mutate the ledger after creation.

### 1.2. The Data Registrar Node
- **Central Fetch:** Move all data fetching logic (`get_stock_data`, `get_fundamentals`, `get_news`, `get_insider`) into `data_registrar.py`.
- **Poisoning Guard:** Implement a check that raises a hard exception if `price_data` or `fundamental_data` is missing or empty (Partial Payload Protection).
- **Hashing:** Implement SHA-256 hashing of the data payload (excluding metadata) for auditability.
- **Freshness:** Implement logic to calculate data age and raise an exception if data is stale (e.g., Price > 60s old).

### 1.3. Analyst Refactoring (The "Lobotomy")
- **Market Analyst:** Remove `get_stock_data` tool binding. Update prompt to ingest `state["fact_ledger"]["price_data"]` directly.
- **Fundamentals Analyst:** Remove `get_fundamentals` tool binding. Update prompt to ingest `state["fact_ledger"]["fundamental_data"]`.
- **News/Social Analysts:** Remove `get_news` tool binding. Update prompt to ingest `state["fact_ledger"]["news_data"]`.
- **Verification:** Assert that no tools are passed to these agents during graph construction.

### 1.4. Graph Wiring
- **Reroute:** Update `setup.py` to route `START` → `DataRegistrar` → `Market Analyst`.
- **Test:** Execute a run. Verify that if the Registrar fails, the graph aborts immediately and no LLM tokens are consumed.

---

## PHASE 2: THE GUARDRAILS (Execution Gatekeeper)
**Objective:** Separate "Decision Generation" from "Decision Authorization" using deterministic python logic.

### 2.1. Gatekeeper Logic Core
- **Create Class:** Implement `ExecutionGatekeeper` in a new file.
- **Compliance Check:** Scan `fact_ledger["insider_data"]` for restricted flags. Return `ABORT_COMPLIANCE` if found.
- **Data Re-Verification:** Check `fact_ledger["freshness"]` again at the moment of execution. Return `ABORT_DATA_GAP` if expired.

### 2.2. Consensus & Directionality Rules
- **Divergence Logic:** Calculate `Divergence_Score = abs(Bull_Score - Bear_Score) * Confidence`. If `score > Threshold`, return `ABORT_DIVERGENCE`.
- **Direction Consistency:** Compare Trader Direction (Buy/Sell) vs. Mean Analyst Direction.
    - **Rule:** If Trader says "BUY" but Average Analyst says "SELL", return `ABORT_DIRECTION_MISMATCH`.

### 2.3. Deterministic Trend Override
- **Logic:** Implement the "Don't Fight the Tape" rule:
    - `IF (Regime == BULL) AND (Price > 200SMA) AND (Growth > 30%): BLOCK_SELL`.
- **Counterfactual Logging:** If a trade is blocked, log the specific event: `{"event": "BLOCKED_TREND", "intent": "SELL", "action": "HOLD"}`.

### 2.4. Integration
- **Wire Node:** Insert `ExecutionGatekeeper` between `Trader` and `END`.
### 2.4 Phase 2.7: Institutional Safety (Hardening)
- **Pulse Check:** A pre-trade live market verify. Abort if drift > 3%.
- **Market Hours:** Trade only during NYSE sessions (9:30-16:00 EST).
- **Split Check:** Massive drift (>50%) triggers a corporate action abort.
- **Deterministic Flow:** Insider math is computed as a float in the Registrar, not sniffed in the Gatekeeper.

---

**PHASE 2 STATUS:** ✅ 100% VERIFIED via `verify_logic_v2_7.py`.

---

## PHASE 3: THE INTELLIGENCE (Bounded Learning)
**Objective:** Implement safe, attributed parameter tuning that respects market regimes.

### 3.1. Attribution Scoring
- **Reflector Update:** Modify the reflection prompt to output a specific performance score (0.0 - 1.0) for each agent based on the trade outcome.
- **Sparse Scoring:** Enforce a rule that scores must be decisive (e.g., ≥ 0.7 or ≤ 0.3) to prevent "diffuse blame."

### 3.2. Parameter Validator
- **Velocity Brake:** Implement logic to track the last 3 updates for every parameter. If the direction is identical 3x in a row, return `REJECT_UPDATE` (Freeze Parameter).
- **Rollback:** Implement `revert_last_update()` functionality to undo the previous parameter change if performance degrades.

### 3.3. Regime-Conditioned Memory
- **Tagging:** Update the memory saver to tag every lesson with `{"regime": current_regime}`.
- **Retrieval:** Update the Trader's memory retrieval to filter strictly by the `current_regime` (e.g., do not fetch Bear Market lessons during a Bull Market).

---

## PHASE 4: OPERATIONAL SAFETY (The Human Loop)
**Objective:** Make the system observable and manually stoppable.

### 4.1. The "Cold" Review Path
- **Logger:** Create `human_review_logger.py`.
- **Event Hooks:** Wire `ABORT_*`, `BLOCKED_TREND`, and `FREEZE_PARAMETER` events to write to an append-only `human_review.json` file.

### 4.2. Circuit Breakers
- **Sticky Breaker:** Implement a lockfile mechanism.
- **Rule:** If `Cash_Balance` < 85% of starting capital, write a lockfile to disk.
- **Enforcement:** `DataRegistrar` must check for this file on startup and refuse to run until a human manually deletes it.