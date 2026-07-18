# TradingAgents Local Web Handoff

Last updated: 2026-07-18

## Goal

Build a localhost-only web application that starts from the terminal, accepts a stock and analysis inputs, runs the real TradingAgents workflow, and visualizes agent outputs, debate turns, data/tool calls, run inputs, and final artifacts with clear role icons.

## Current phase

The user explicitly approved the corrected formal specification on 2026-07-18. The implementation plan is complete at `docs/superpowers/plans/2026-07-18-local-web-workbench-implementation.md`. Story A1 is implemented: programmatic tuple/exception/checkpoint contracts, explicit report publication, legacy root CLI dispatch, explicit `analyze` dispatch, checkpoint/config option routing, and configured save/display choices are now protected by tests. The configured-run path now also carries a canonical `asset_type`, fixing a pre-existing failure that would have blocked JSON-configured CLI and web runs. Phase A continues with runtime preflight and event/lifecycle contracts.

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
- The authoritative interpreter is `/Users/david/miniconda3/bin/python` (Python 3.13.5) from a login shell; it provides pytest and LangGraph.
- The focused pre-change legacy baseline passed with 41 tests. After Story A1, the expanded legacy matrix passed with 43 tests and the A1/relevant compatibility matrix passed with 97 tests.
- Typer's prior single-command collapse made `tradingagents [OPTIONS]` work while README-documented `tradingagents analyze [OPTIONS]` failed. The callback/group boundary now supports both, so adding `web` will not silently break the legacy root invocation.
- Configured selections previously omitted `asset_type` and used only A-share ticker normalization. They now use the canonical CLI normalizer and explicitly classify stock versus crypto.

## Pending decisions

None. Material product and architecture decisions are approved. Pause only if implementation evidence exposes a new choice that would change the agreed scope or truthfulness of the audit trail.

## Next steps

1. Implement Story A2 web runtime capability preflight and dependency floors.
2. Implement Story A3 event, role, request, and lifecycle contracts.
3. Keep this file current after every implementation phase and record exact verification evidence.

## Notes

- The standard brainstorming visual-companion launcher is missing from the installed skill package. A local static mockup server will be used as a fallback for visual comparisons.
