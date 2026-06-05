# trading-agent

Fondo d'investimento autonomo (paper trading), multi-agente LLM + motore
deterministico. Questo repository è stato **ricostruito a immagine del design**
descritto nella wiki del progetto (`trading-agent-wiki`): la topologia degli
agenti, lo state, i nodi e gli edge corrispondono alla wiki, non alla struttura
del fork TradingAgents da cui siamo partiti.

> Stato: **alpha v0** — la catena gira end-to-end su paper trading. I numeri
> (soglie, rischio) sono default da tarare in backtest; alcuni vendor dati sono
> ancora da collegare.

## Come gira (la catena)

```
yfinance → price_bars → indicatori/ATR → screening → ticker_card
   → Trigger Engine → coda di priorità → BRAIN (2 desk → PM → Risk gate)
   → cost gate (net-EV) → Trade deterministico → broker (paper) → reconcile
```

Tutto è deterministico tranne il **brain** (gli agenti LLM). Il brain riempie la
tesi (`ResearchState`); il resto — sizing, livelli, ordine, esecuzione — è codice
testato.

## Mappa del codice → wiki

| Pacchetto | Cosa | Pagina wiki |
|-----------|------|-------------|
| `storage/` | DB-first (4 aree + scheda ticker + research_state) | data-layer, db-access-performance |
| `domain/` | `ResearchState`, enum `Direction`, risk engine (ATR, sizing, guardrail) | state-schemas, position-sizing |
| `indicators/` | ATR/RSI/SMA/EMA… (`compute_indicator`) | tools-inventory (fam. B) |
| `ingestion/` | OHLCV→DB (DB-first) + screening deterministico | data-layer, parallelism-design |
| `brain/` | **grafo nostro**: 2 desk → PM aggrega → Risk gate singolo | agents, agent-behaviors, system-prompts |
| `execution/` | Trade deterministico, costi (net-EV), portfolio injection | execution, cost-accounting |
| `broker/` | adapter intercambiabile (PaperBroker, Alpaca) + commissioni | execution |
| `orchestration/` | Trigger Engine + cycle runner (`run_cycle`) | trigger-engine, parallelism-design |
| `app.py` / `cli.py` | entrypoint runnabile | architecture |

### Riusato dal fork (infra, non riscritto)
`llm_clients/` (multi-provider, OpenRouter/DeepSeek), `dataflows/` (vendor:
yfinance, Alpha Vantage, Finnhub, Reddit, StockTwits, stockstats),
`brain/structured.py` (output JSON strict).

## Avvio rapido

```bash
# 1. dipendenze (uv)
uv sync

# 2. configurare .env (vedi .env.example): provider LLM + chiavi
#    TRADINGAGENTS_LLM_PROVIDER=openrouter + modello DeepSeek + OPENROUTER_API_KEY
#    (DB: SQLite locale di default; TRADINGAGENTS_DATABASE_URL per Postgres/Timescale)

# 3. un ciclo live su paper trading
uv run python -m tradingagents.cli AAPL MSFT --start 2024-01-01
```

## Test

```bash
uv run pytest -m "not integration"   # offline, deterministici
uv run pytest -m integration         # rete (yfinance, Alpaca, LLM)
```

I test offline non richiedono né rete né chiavi: il brain è testato con un LLM
finto, i vendor con fetcher finti. Sono l'**oracolo** che verifica che il codice
rispetti il design della wiki.
