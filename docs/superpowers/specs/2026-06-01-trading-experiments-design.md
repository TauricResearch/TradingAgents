# Trading Experiments Design

## Goal

Add opt-in research workflows for historical simulation, multi-asset allocation,
semantic memory, visual chart analysis, and post-mortem rules without changing
the existing single-ticker API.

## Design

The existing `TradingAgentsGraph.propagate()` remains the analysis engine.
New orchestration code lives in `tradingagents/experiments/` and calls the graph
as a service. The default CLI remains unchanged.

Semantic memory uses SQLite and deterministic local hashed embeddings. It stores
pending decisions, resolves outcomes alongside the markdown memory log, and
retrieves the three closest resolved situations. This avoids a service, model
download, or native extension.

Backtests run graph decisions on weekly slices and execute rating-based target
weights through Backtrader. Portfolio coordination runs the graph for each
ticker, computes return correlations, and applies inverse-volatility risk parity
with rating tilts. Both expose small Python APIs and thin scripts.

Charts are optional. Matplotlib renders OHLC candlesticks, EMA, RSI, and MACD.
A visual analyst sends the image to the configured multimodal LLM before the
debate and stores its report in graph state. Unsupported or disabled runs skip
the step cleanly.

Post-mortem generation reads resolved semantic-memory rows and writes compact
JSON rules. Analyst prompts append those rules when present.

## Configuration

All additions are opt-in except semantic memory, which supplements markdown
memory when a database path is configured by default. New paths live under
`~/.tradingagents/`.

## Testing

Unit tests cover embeddings, retrieval, allocation, metrics, chart rendering,
rules, and multimodal message construction without network calls. Existing tests
must remain green.
