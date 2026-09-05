# PR5: Local Research Cockpit

This change adds a small local web cockpit without coupling it to the original
TradingAgents graph or CLI.  It reads only the JSONL artifacts produced by the
new research-platform boundary:

- normalized prices, fundamentals, and news;
- structured agent output envelopes;
- provenance already captured in those artifacts.

The cockpit is intentionally read-only. Starting it does not invoke a market
data provider, an LLM, or a TradingAgents workflow. This makes it suitable for
reviewing a prior research run, including when the provider is unavailable.

## Run locally

Populate a local artifact store through `run_ticker_research(..., store=...)`,
then run:

```powershell
python -m tradingagents.research_platform.cockpit --data-dir .research-data
```

Open `http://127.0.0.1:8765`. The ticker selector is derived from the cached
artifact files. The page shows a 90-bar closing-price view, current cached
fundamentals, recent news, and structured Agent output. A missing cache is a
normal empty state, not an error.

## Scope boundary

The implementation is confined to `tradingagents/research_platform/cockpit.py`
and uses only the existing `JsonArtifactStore` and typed contracts. It does not
alter the legacy TradingAgents agent graph, its prompts, or dataflow behavior.
