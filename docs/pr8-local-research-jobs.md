# PR8: Local Research Jobs

The cockpit can now submit one bounded local research job. The job runner uses
the existing `run_ticker_research` workflow with the direct yfinance provider,
the JSONL artifact store, and the immutable run archive.

Jobs run one at a time in the local process. This keeps vendor requests and
cache writes predictable for a personal workstation. The cockpit exposes the
live job state as `queued`, `running`, `succeeded`, or `failed`; a provider
error is presented as a failed job rather than crashing the server.

The run button does not call the legacy TradingAgents graph, invoke an LLM, or
submit anything to a broker. A successful job persists normalized artifacts,
a Markdown report under `reports/`, and one archived bundle under `runs/`.
Job status itself is intentionally process-local; the report and archive are
the durable record after a server restart.
