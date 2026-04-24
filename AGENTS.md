## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `PYTHONPATH=. /opt/miniconda3/bin/python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current

## scanner determinism

Daily scanner runs must be deterministic and fail loudly when required context is missing.

Rules:
- Do not add fallbacks for deterministic scan context. `scan_date` and `run_id` must be seeded at scan start and propagated through `ScannerState`.
- Scanner, summarizer, industry, and macro nodes must fail with a clear reason if `scan_date`, `run_id`, or required upstream graph evidence is missing.
- Do not substitute wall-clock dates such as `today`, `datetime.now()`, or `time.strftime()` when a scan date is missing or invalid.
- Do not use latest-run, latest-date, active-run-logger, or cross-run disk lookup as a fallback for scanner graph state.
- Tools should receive the propagated scan date. If tools cannot run with that context, fail the node and persist/report the reason rather than synthesizing fallback evidence.
