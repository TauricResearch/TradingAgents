# Structured Contracts Rollout Learnings

Date: 2026-04-03
Branch at merge time: `codex/structured-contracts-plan`
Merged PR: `#182`

## Why the rollout was necessary

The pipeline was carrying too much meaning in rewritten prose between nodes.
That created two distinct failure modes:

- hallucination by restating upstream content in a new form
- aborts or silent stalls because later nodes had to infer machine state from narrative text

The strongest architectural correction was to make contracts explicit and deterministic, then treat prose as presentation instead of state.

## What worked

### 1. Structured contracts reduced ambiguity quickly

The biggest improvement came from making node outputs machine-readable and preserving them in state:

- `market_report_structured`
- `news_report_structured`
- deterministic downstream packet assembly

Once these existed, downstream nodes no longer had to guess whether a node succeeded, failed, or partially completed from raw text alone.

### 2. Removing summary rewrites was the right move

The `Research Packet Summary` path was a real hallucination surface.
Even when upstream reports were acceptable, summary generation created a second interpretation layer.

The better pattern was:

- keep scanner context and analyst outputs as canonical inputs
- build the downstream packet deterministically
- let downstream nodes consume facts first

Summary text can still exist as a derived artifact, but not as the contract that drives the graph.

### 3. Live debugging needed direct graph execution

API-backed runs were not reliable enough for deep debugging because event visibility was incomplete.
Direct LangGraph execution was the only trustworthy way to answer:

- did the node actually run
- what prompt was really sent
- which node did the graph route to next

Lesson: when the UI/API event stream is suspect, debug the graph directly before changing routing logic.

### 4. Timeout guards are necessary, but they change observability

Adding timeout wrappers around direct model invokes helped prevent indefinite stalls.
But this likely weakened callback visibility for the backend event layer.

Lesson: safety wrappers around LLM calls must be treated as part of the tracing contract, not only the runtime contract.

### 5. Injected artifacts are useful, but only if they mirror the real contract

Injecting a saved market report made controlled testing much easier.
But the injected path was incomplete because it did not automatically hydrate `scanner_context_packet`.

Lesson: a test injection path should reproduce the production handoff as closely as possible, or it will hide contract bugs.

## What still failed

### 1. API-backed live event visibility remained weak

The graph could progress in direct execution while `run_events.jsonl` showed only `__system__` events.
That means the main remaining problem is not just graph logic; it is the runtime observability path.

### 2. Vendor-backed scanner enrichment is still brittle

`scanner_context_packet` could still degrade to partial output such as:

- `Date: N/A`
- `Filtered Economic Events: N/A`

The packet still worked, but it was not consistently complete.

### 3. There is still too much concentration in `langgraph_engine.py`

The file is doing too much:

- event mapping
- run orchestration
- checkpoint persistence
- packet building
- injected artifact handling
- scan-state and rerun logic

That makes runtime bugs harder to isolate than they need to be.

## Practical rules learned from this rollout

### Rule 1: Upstream nodes own facts

If a node discovers or validates a fact, that node should own the structured field for it.
Downstream nodes should select, weigh, or reject those facts, not rewrite them into a new implied contract.

### Rule 2: Status must be explicit

Every important node should expose enough structured state to distinguish:

- completed
- empty
- failed
- aborted
- timeout fallback

Blank strings are not a valid state contract.

### Rule 3: Prompt checks should be done on real rendered prompts

Prompt templates looked correct in code, but the meaningful check was always the rendered prompt from a real run or direct node invocation.

### Rule 4: Live validation should move top-down

The correct order was:

1. fix an upstream node
2. validate that node in isolation
3. inspect checkpoint and prompt artifacts
4. move one boundary downstream

This prevented chasing symptoms produced by lower nodes.

### Rule 5: Deterministic packet builders are safer than summary prompts

If the handoff can be assembled by code, it should be.
Prompted summary generation should not be the default mechanism for inter-node state transfer.

## Recommended next engineering moves

### 1. Fix the live event contract

The next runtime fix should focus on:

- timeout-guarded LLM invocations
- LangGraph event emission
- backend event mapping and persistence

The handoff for that work is in:

- [022-live-run-issue-handoff.md](/Users/Ahmet/Repo/TradingAgents/docs/agent/plans/022-live-run-issue-handoff.md)

### 2. Complete explicit status contracts across all analyst and downstream nodes

The remaining path should keep replacing inferred prose state with bounded structured state.

### 3. Refactor `langgraph_engine.py` last

Do the split after live-run behavior is stable enough to lock down with regression tests.
Refactoring earlier would increase motion while the runtime contract is still changing.

## Short version

The core lesson is simple:

The graph became more reliable when it stopped passing rewritten prose as state.

The remaining hard problem is not the contract design anymore.
It is making the live runtime expose the real node/model/tool activity consistently enough to debug and trust.
