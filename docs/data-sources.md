# Data Sources Inventory

> **Purpose:** Single source of truth for all financial data sources reviewed, their status, and integration notes.
> Update this file when a new source is added or an existing source changes status.

---

## Active Integrations

| Source | Type | Status | Used by | Notes |
|--------|------|--------|---------|-------|
| **yfinance** | Python package | Active | `tradingagents/dataflows/y_finance.py`, `scripts/py/get_price.py` | OHLCV, financials, news, insider transactions |
| **Alpha Vantage** | REST API | Active | `tradingagents/dataflows/alpha_vantage_*.py` | Fundamentals, indicators, news via `ALPHA_VANTAGE_API_KEY` |

---

## In Implementation (Phase 1)

| Source | Type | Status | Target file | Notes |
|--------|------|--------|-------------|-------|
| **EODHD SDK** | npm `eodhd` | In progress | `src/server/lib/eodhd.ts` | Pricing, fundamentals, insider transactions, technical indicators |

Brief: `briefs/eodhd-pricing-brief.md`
Key: `EODHD_API_KEY` (Skate)

---

## Local Tools (Implemented)

| Tool | Path | Notes |
|------|------|-------|
| **kpdf** | `scripts/kpdf.ts` | PDF extraction CLI. Bun + `@kreuzberg/node`. Formats: markdown, json (structured nodes), text. Run `bun run scripts/kpdf.ts --help` for usage. |
| **kreuzberg** | npm binary | Full Kreuzberg CLI (installed with `@kreuzberg/node`). Run `kreuzberg mcp` for MCP server mode (stdio, JSON-RPC 2.0). |

## Future Candidates (Phase 2+)

| Source | Type | Status | Rationale | Notes |
|--------|------|--------|-----------|-------|
| **EODHD historical OHLCV** | SDK | Future | Replaces Python `get_YFin_data_online` call — single call, typed | Phase 2 |
| **EODHD insider transactions** | SDK | Future | `client.insiderTransactions()` — SEC Form 4, no additional API | Phase 2 |
| **EODHD technical indicators** | SDK | Future | `client.technical()` — 15+ indicators (SMA, EMA, RSI, MACD, BB, etc.) | Phase 2 |
| **EODHD screener** | SDK | Future | `client.screener()` — momentum-ranked watchlist for Prospects pipeline | Phase 2 |
| **EODHD momentum signals** | SDK + server-side | Future | SMA 20/50 crossover + ROC-10 — concrete signal model from `docs/momentum-trading-with-eodhd.md` | Phase 2 |
| **EODHD WebSocket** | SDK | Future | `client.websocket()` — real-time US trades, forex, crypto feeds | Phase 3 |
| **Kreuzberg document intelligence** | MCP | Future | `kreuzberg mcp` for PDF/DOCX ingestion into analysis pipeline (SEC filings, earnings PDFs) | Phase 4 |

---

## Archived (Not Integrated)

| Source | URL | Date | Reason not integrated |
|--------|-----|------|----------------------|
| **Meyka** | meyka.com | 2026-05-19 | AI chatbot API only — not a structured data endpoint. EODHD already covers insider transactions via `client.insiderTransactions()`. Pay-per-token model adds cost without adding data. |
| **secfilingdata.com** | api.secfilingdata.com | 2026-05-19 | Raw SEC Form 4 API — no SDK, no Bun/TypeScript wrapper. EODHD covers this. |

---

## External Reference Articles (Not Integrations)

| Doc | Source | Date | Key takeaway |
|-----|--------|------|--------------|
| `docs/momentum-trading-with-eodhd.md` | Kevin Meneses, CodeX | 2026-05-01 | Exchange code corrections (LSE, XETRA, TSX), momentum signal model (SMA 20/50 + ROC-10) |
| `docs/meyka-insider-tracker.md` | Huzaifa Zahoor, Meyka | 2026-03-24 | Insider trading context (legal Form 4 filings). No new integration data. |

---

## Data Source Decision Framework

When evaluating a new data source, apply this filter before drafting a brief:

1. **Does EODHD already cover it?** → Likely archive. EODHD SDK is the preferred integration point.
2. **Is there a typed SDK for Bun/TypeScript?** → Preferred over raw REST + manual parsing.
3. **Is it available via the Python `tradingagents/` package?** → Only for analysis pipeline. Dashboard uses TypeScript.
4. **Is there a free tier for testing?** → Required before CI integration.
5. **Is the secret stored in Skate?** → Required before production use.

---

*Last updated: 2026-05-19*