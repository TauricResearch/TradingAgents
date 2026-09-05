# PR10: Optional Structured Narrative Agents

PR10 adds an optional OpenAI-backed research narrative to the local personal
research platform. It is an additive adapter under `tradingagents/research_platform`.
The existing TradingAgents agent flow remains untouched.

## Operating modes

- `deterministic` is the default. It makes no LLM request and preserves the
  existing data, report, manual-decision, risk, and backtest behavior.
- `openai_narrative` is explicitly selected for a local research job. It adds
  one validated `cockpit_panel` output after normalized data collection.

To enable the OpenAI mode, set both environment variables before starting the
cockpit:

```powershell
$env:OPENAI_API_KEY = "..."
$env:TRADINGAGENTS_RESEARCH_OPENAI_MODEL = "your-structured-output-capable-model"
```

The adapter uses this repository's capability-aware `OpenAIClient` and its
structured-output support. It does not run in deterministic mode, does not
create `TradeSignal` records, and cannot bypass manual decisions, risk review,
or the backtest layer. If required environment variables are missing, the
selected local job fails with a clear configuration message.

## Data boundary

Only normalized price bars, the most recent fundamental snapshot, and news
items already collected for the run enter the prompt. The provider response is
parsed into a small Pydantic schema and stored as an `AgentOutputEnvelope` with
the deterministic evidence references used by that run. The resulting report
and immutable archive therefore retain the provider, model, mode, and prompt
version metadata alongside the generated narrative.
