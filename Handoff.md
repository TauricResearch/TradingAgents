# TradingAgents Local Web Handoff

Last updated: 2026-07-18

## Goal

Build a localhost-only web application that starts from the terminal, accepts a stock and analysis inputs, runs the real TradingAgents workflow, and visualizes agent outputs, debate turns, data/tool calls, run inputs, and final artifacts with clear role icons.

## Current phase

Formal specification review exceeded the normal five-round limit once under continued-goal execution. The exceptional review confirmed task-token coverage and runtime floors, then found one final boundary issue: LangGraph internal branch/control channels must not count as business state. The spec now derives `BusinessStateProjectionV1` strictly from declared inherited `AgentState` fields, persists its schema hash, and excludes all framework-only channels from state hashes and pending-write mutation tests. No further automated review is scheduled; human review is now required.

## Confirmed constraints

- Localhost only; no hosted site or production deployment.
- The web UI must run the real TradingAgents graph rather than a simulated demo.
- Debate turns, agent output, tool/data calls, inputs, progress, and final reports must be inspectable.
- The UI should be compact, clear, visually polished, and use distinct role icons.
- Decisions should start from the real objective, constraints, observable runtime events, and failure conditions.
- Only one analysis may be active at a time in the first local version.
- Completed and failed runs remain available for history and report review.
- API keys remain in `.env` or the local config file. The browser only receives configured/missing status and never receives or stores secret values.
- The application will use a full local website architecture: FastAPI backend plus React, TypeScript, and Vite frontend.
- The richer frontend is intentional because debate visualization requires interactive filtering, expandable tool/data calls, live state, and historical replay.
- The website remains localhost-only and is not deployed or publicly hosted.
- The approved runtime boundary is React UI -> FastAPI REST/SSE -> single-run manager -> background worker -> shared AnalysisRunner -> real LangGraph.
- Every run has an independent `run_id` directory with a non-secret input/status snapshot, append-only event log, and report artifacts.
- The built React assets are served by FastAPI for normal use; Node is only needed for frontend development/building.
- The approved event model uses an append-only, versioned event envelope with monotonic sequence numbers for SSE delivery and historical replay.
- Graph node updates are the authority for actor identity; callbacks add tool lifecycle details; debate cards use per-turn current responses rather than cumulative history.
- Large tool results are stored as referenced run data files, while SSE carries a safe summary and reference.
- UI feedback: replace placeholder glyphs with 13 distinctive custom role icons that share one coherent visual language.
- UI feedback: every role needs an auditable input view showing the exact evidence, upstream reports, tool results, and instruction context it actually received, including source and time-range metadata. Examples include company overview, balance sheet, income statement, cash flow, market data, and technical indicators.
- The input view must help the user verify data accuracy; a tool-call list alone is insufficient.
- Per-role input capture is now designed as two layers: a node-entry whitelist snapshot for the actual state fields each role reads, plus an LLM-start callback snapshot for the fully formatted prompt/messages actually sent to the model.
- Shared financial tables and large tool results are content-addressed artifacts; role events reference their hashes instead of duplicating data.
- Sentiment Analyst direct news/social prefetches and Evidence Steward advisor/enrichment calls require explicit observer injection because the current graph callbacks do not see them.
- Aggregate role-card status is separate from immutable logical turn lifecycles, so repeated Bull/Bear and risk rounds remain auditable.
- Resume is restricted to interrupted runs and requires a canonical full-config/runtime fingerprint plus event-log/checkpoint correlation reconciliation.
- News-result caching is run-scoped; same-run cache hits reference the original raw and normalized artifacts.
- `AnalysisResult` represents success only. Web cancellation/failure state stays in the run store, while programmatic tuple and exception behavior remain compatible.
- Checkpoint-enabled web runs use synchronous durability and never treat ordinary stream updates as durable commits.
- Every observed graph task carries a reserved checkpoint commit token; recovery classifies JSONL tails as committed, pending-apply, or abandoned without rewriting history.
- Resume fingerprints include Python runtime identity and the installed transitive dependency closure with package metadata digests.
- The V2 visual mockup exposes all 13 roles separately, uses custom inline SVG icons, and adds a role audit inspector with data fields, upstream inputs, prompt view, and raw vendor values.
- V2 browser QA passed on 2026-07-18: Playwright confirmed all 13 role nodes are present, role selection switches the input composition, raw-value and main inspector tabs work, and closed tool details expand correctly.
- The only initial browser console error was a missing favicon; the mockup now uses an empty data favicon and reloads without console errors.
- The user approved the V2 visual layout, custom 13-role icon system, and per-role input audit interaction on 2026-07-18.

## Repository evidence gathered

- `TradingAgentsGraph` already accepts callback handlers and exposes the LangGraph workflow.
- The CLI already streams graph chunks, classifies AI/tool messages, tracks agent status, records data-progress events, and writes reports.
- Final state already contains analyst reports, investment debate state, trader plan, risk debate state, and final trade decision.
- The current data-progress sink is process-global, so concurrent web runs need isolation or an explicit single-active-run rule.
- The project is currently Python-only; no frontend framework or web server dependency is installed.
- The CLI already extracts agent messages, tool arguments, tool results, debate state, risk state, and data-vendor progress from the real graph stream.
- The synchronous LangGraph stream must run in a worker thread so the web server event loop stays responsive.
- A shared `AnalysisRunner`/event adapter should serve both CLI and Web paths to avoid creating a third execution implementation.

## Pending decisions

The user must review the corrected written specification and either approve it as the human override after the review-limit escalation or request changes. Implementation planning remains blocked until that approval.

## Next steps

1. Obtain explicit user approval of the corrected written specification.
2. After user approval, create the detailed implementation plan.

## Notes

- The standard brainstorming visual-companion launcher is missing from the installed skill package. A local static mockup server will be used as a fallback for visual comparisons.
