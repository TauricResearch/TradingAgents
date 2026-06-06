<div align="center">

# 🤖 trading-agent

**Fondo d'investimento autonomo** — multi-agente LLM + motore deterministico.
Paper trading, mid-term swing, equity-first.

`alpha v0` · 216 test verdi · Python 3.13 · LangGraph · OpenRouter/DeepSeek

</div>

---

Questo repository è costruito **a immagine del design** descritto nella wiki del
progetto (`trading-agent-wiki`): la topologia degli agenti, lo state, i nodi e
gli edge corrispondono al canvas `architettura.canvas`, non alla struttura del
fork TradingAgents da cui siamo partiti (di cui resta solo l'infrastruttura
riusabile: client LLM e connettori dati).

## 🧠 Come ragiona

Tutto è deterministico **tranne il cervello** (gli agenti LLM). Il cervello
riempie la tesi (`ResearchState`); il resto — sizing, livelli, ordine,
esecuzione, uscite — è codice testato.

```
loop autonomo (periodical synthesis)
  └─ Trigger Engine   (checkpoint · price-alert · screening)
       └─ coda di priorità
            └─ BRAIN per ticker  ── warm start: extractor pre-lanciati → 1° contesto
                 ├─ Market · Sentiment      (Analyst Research)
                 ├─ Technical · Fondamentali (Analyst Technical)
                 │     ↑ ogni agente chiama i propri tool (Extractors set) → DB
                 │       e mantiene un context state cucito sul suo compito
                 ├─ Portfolio Manager  (aggrega direction/conviction + livelli ATR)
                 └─ Risk Analyst  (bear + Statuto: R:R · cash 10% · VaR · settore)
                      └─ Investment State → Trade deterministico (equity / opzioni su Strong)
                           └─ broker (paper) → uscite TP/SL · disinvestimento rating
                                └─ DecisionLog (substrato di apprendimento)
```

## 🗺️ Mappa del codice

| Pacchetto | Ruolo |
|-----------|-------|
| `storage/` | DB-first (4 aree + scheda ticker + research_state), SQLite→Postgres/Timescale |
| `domain/` | `ResearchState`, enum, risk engine (ATR, sizing, guardrail Statuto) |
| `indicators/` | ATR/RSI/SMA/EMA… (`compute_indicator`) |
| `ingestion/` | extractor → DB (prezzi · news · fondamentali · macro · social), DB-first |
| `tools/` · `brain/tooling.py` | Extractors set: tool che gli agenti chiamano (real-time-first + write-through) |
| `brain/` | il grafo nostro (LangGraph): 2 desk → PM → Risk; context per-agente |
| `execution/` | Trade deterministico, costi (net-EV), uscite, disinvestimento, mantainer |
| `broker/` | adapter intercambiabile (PaperBroker · Alpaca) |
| `orchestration/` | Trigger Engine + cycle runner |
| `backtesting/` | validatore deterministico delle soglie |
| `app.py` · `cli.py` | entrypoint runnabile + loop autonomo |

Mappa completa canvas↔codice: vedi `trading-agent-wiki` → `system/canvas-code-mapping`.

## 🚀 Avvio

```bash
uv sync                                   # dipendenze

# .env (vedi .env.example): serve almeno OPENROUTER_API_KEY
#   (DB: SQLite locale di default; opzionali FRED_API_KEY, ALPACA_*)

# un ciclo
uv run python -m tradingagents.cli AAPL MSFT --start 2024-01-01

# loop autonomo (paper) ogni ora
uv run python -m tradingagents.cli AAPL MSFT --loop 3600
```

## ✅ Test

```bash
uv run pytest -m "not integration"   # offline, deterministici (no rete, no chiavi)
uv run pytest -m integration         # rete: yfinance · Alpaca · LLM
```

I test offline non richiedono né rete né chiavi: il brain è testato con un LLM
finto, i vendor con fetcher finti. Sono l'**oracolo** che verifica che il codice
rispetti il design della wiki.

## 🛣️ Roadmap (prossimi sviluppi)

- **Dashboard read-only** in stile **SFC fund (Streamlit)** — vista di sola
  lettura su portafoglio, NAV, performance/attribuzione, decisioni e trade
  (da sviluppare in un secondo momento).
- **Observability & evaluation**: imparare a usare **LangSmith** e **LangGraph
  Studio** per il tracing dei grafi, il debug degli agenti e la valutazione
  (eval) prima di consolidare i prompt.
- **Memoria inter-task** degli agenti (imparare dai casi passati) e
  **deduplicazione** sistematica di ogni informazione nel DB.
- Esecuzione live: **IBKR** adapter, esecuzione reale catena opzioni, broker
  reale al posto del simulatore paper.
- **Taratura dei numeri** in backtest (rischio, R:R, soglie, cadenze).

## ⚠️ Stato

`alpha v0`: la catena gira **end-to-end** su paper trading simulato. Non è ancora
un deploy 24/7 production-grade (vedi roadmap). I numeri sono default da tarare.
