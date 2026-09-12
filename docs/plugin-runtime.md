# TradingAgents MCP runtime

Use an activated, dedicated Python environment. Install the optional runtime and launch it with:

```bash
python -m pip install ".[plugin]"
python -m pip check
tradingagents-mcp --state-dir "$HOME/.tradingagents/plugin"
```

The direct launch waits for an MCP client on standard input. An empty terminal that remains open
is not a completed analysis. The server writes only MCP protocol messages to standard output;
diagnostics and logs use standard error.

By default, state is stored at `~/.tradingagents/plugin/`. `--state-dir` takes precedence over
`TRADINGAGENTS_PLUGIN_STATE_DIR`. The runtime creates and verifies that directory is writable, but
does not create a database until a later workflow feature requires one.

`ALPHA_VANTAGE_API_KEY` and `FRED_API_KEY` are optional. `get_capabilities` reports only whether
they are present, never their values. Keyless sources (yfinance, Polymarket, StockTwits, and
Reddit) can still be unavailable or rate-limited; a present key does not establish source
availability.

The package inherits its `.env` lookup from `python-dotenv`: it searches relative to the launch
working directory and its ancestors. For launches outside the checkout, export settings in the
environment instead of depending on a checkout-local `.env` file.

The optional SDK is pinned to `mcp==1.26.0`. `get_capabilities` is the only current MCP tool;
data operations and the full workflow arrive in US-005 onward. Host manifest installation and
activation remain US-018 work and do not provision this Python environment.
