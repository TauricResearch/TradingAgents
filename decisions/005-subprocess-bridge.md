# Decision: Subprocess Bridge over Forking the Python Core

**Date:** 2026-05-02
**Status:** Accepted

## Context

The dashboard needs to trigger LLM-powered trading analyses using the upstream `tradingagents` Python package. The options were: fork the package and integrate it directly into the TypeScript codebase, embed it as a Python library called from Bun, or communicate via subprocess.

## Decision

The dashboard communicates with the `tradingagents` package exclusively via subprocess. `scripts/py/analyze_stream.py` is the single bridge — it emits JSON lines to stdout, which the Bun server reads, parses, and forwards as SSE events to the browser. Position context is injected by writing to the memory log before spawning the subprocess (wrap, don't fork).

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| Fork the Python core into TypeScript | Maintenance nightmare — every upstream release would require a re-port; loses Python ecosystem (LangChain, yfinance) |
| Embed Python via `python-bridge` or PyO3 | Adds native module dependency; platform-specific; breaks on Bun runtime |
| HTTP microservice | Adds deployment complexity; subprocess is simpler for single-machine operation |

## Consequences

**What became easier:**
- Zero modification to upstream `tradingagents/` package
- Upstream updates are drop-in (just `uv sync`)
- Python and TypeScript can evolve independently
- SSE streaming is natural — subprocess stdout → Bun → browser

**What became harder:**
- Error handling across the subprocess boundary — Python crashes must be surfaced as SSE `error` events
- No type safety across the boundary — the SSE event schema is a TypeScript type, not enforced at the Python level
- Debugging requires reading both Python stderr and Bun server logs
- Position context injection is fragile — writing to the memory log before spawning relies on file system ordering

**Constraints this imposes:**
- `scripts/py/analyze_stream.py` is the ONLY bridge — no other Python scripts may be called from the server
- Python must run with `PYTHONUNBUFFERED=1` for real-time streaming
- SSE event types (`start`, `agent_report`, `debate_round`, `decision`, `complete`, `error`) are the contract
- Never fork `tradingagents/` core agent logic (stated in AGENTS.md, ARCHITECTURE.md, README.md, and this ADR)

## Related

- Debrief: `debriefs/debrief-dashboard-foundation-2026-05-02.md`
- Architecture: `ARCHITECTURE.md` (SSE Event Schema section)
- Script: `scripts/py/analyze_stream.py`
