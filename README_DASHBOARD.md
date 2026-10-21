# Koral Equities — premium local AI equity trading desk

This is a **local, browser-based dashboard** for the GBP £10,000 TradingAgents paper account. It is not connected to Trading 212 or any other broker. It never sends a real order. The interface shows **actual** values from `~/.tradingagents/paper/portfolio.json` and empty states before the first trading session; there is no fabricated performance chart.

## Windows: run it

From the TradingAgents repository root, after downloading the updated `feature/gbp-paper-equities-v1` branch:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\koral-equities.exe
```

Your browser opens at **http://127.0.0.1:8765**. Press `Ctrl+C` in the PowerShell terminal to stop the local server.

**Already ran `tradingagents-paper init`?** Do not run it again. The dashboard loads that same saved portfolio file automatically. It does not overwrite it.

If you receive "not recognized" when launching, rerun the `pip install -e .` command inside the updated branch's folder, then retry. To choose another port, pass `--port 8766`. To open the URL manually, use `--no-browser`. To read a different simulated account, use `--state C:\path\to\portfolio.json`.

## Dashboard sections

- **Overview:** GBP equity, total return, cash, win rate and risk guardrail status, plus an equity curve versus SPY (price-only benchmark, GBP).
- **Activity:** decisions, queued and filled simulated orders, model errors, and drawdown halts from the paper ledger.
- **Intelligence:** the framework's six research responsibilities, plus ticker-specific **recorded** AI ratings. These roles are informational, not independent autonomous broker accounts.
- **Portfolio:** open positions, pending orders, exits and downloadable trade-history CSV files. Position P&L uses the last saved marks, before a hypothetical exit fee.
- **Journal:** locally saved HTML reports from completed analyses.

Click **Run AI scan** after 5:30 p.m. in New York on a trading day. It launches the existing paper CLI as a local subprocess, reading your `.env` or previously authorised ChatGPT provider. You can change the watchlist before submitting. A running-scan banner shows the log and the dashboard refreshes automatically. If it fails, the error log is shown; no trade is invented.

**Important:** analysis is user-initiated while the dashboard is running, not scheduled. The 2% risk figure is a *planned stop-loss budget*, not a guaranteed maximum loss. Prices, USD/GBP, stop fills and spreads are simulated by the underlying daily-bar paper engine. The broker connection and all real ISA holdings remain completely outside this application.

## Architecture

`tradingagents/paper/dashboard.py` is a localhost-only Python HTTP service. `tradingagents/paper/web/index.html`, `styles.css` and `app.js` render the UI without an extra web framework or npm install. It reads the existing `Book` and uses the existing CLI for simulated research. The HTTP API is bound to `127.0.0.1`, sets restrictive browser security headers, and requires a same-origin request to start a scan. Do not expose the server through a public tunnel or reverse proxy.

## Test

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q tests/test_paper_dashboard.py
```


## Persistent scan notifications and AI provider setup

- **Scan results no longer disappear on polling.** After a completed scan (success or failure), the full log remains in the dashboard until **OK · Dismiss** is clicked. Use **Copy log** to share diagnostic output. Dismissal is remembered within that browser tab; a new scan gets its own report.
- API/preflight errors displayed as a small notification also have an **OK** button and remain visible until acknowledged. Routine success messages may still fade.
- If you see `OpenAI API mode is selected but OPENAI_API_KEY is missing`, the provider setting has not been persisted. If you previously signed in with the ChatGPT subscription integration, add `TRADINGAGENTS_LLM_PROVIDER=chatgpt` to the project's `.env`, and **restart the dashboard**. An environment variable set via `$env:TRADINGAGENTS_LLM_PROVIDER = "chatgpt"` applies only to that PowerShell session. The subscription integration must be available to your account and authorised first.
- Alternatively use a separate `OPENAI_API_KEY` if choosing OpenAI's API mode; never paste private tokens into the dashboard, GitHub, or screenshots.
- This preflight only diagnoses missing OpenAI API-key configuration. It does not prove ChatGPT authentication or model/data-provider access works. No real account or trading settings are modified by these UI changes.
