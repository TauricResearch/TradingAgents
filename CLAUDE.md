# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TradingAgentsX is a multi-agent AI trading analysis system that simulates real-world investment firm operations. It uses LangGraph to orchestrate 12 specialized AI agents (analysts, researchers, traders, risk managers) that collaborate through structured debate workflows to generate trading decisions.

**Stack**: Python 3.10+ backend (FastAPI) + Next.js 16 frontend (React 19, TypeScript)

## Build & Run Commands

### Backend (FastAPI)
```bash
pip install -e .                                    # Install package in editable mode
pip install -r backend/requirements.txt             # Install backend dependencies
python -m backend                                   # Run server (default: localhost:8000)
python -m backend --host 0.0.0.0 --port 8000 --reload true  # With options
```

### Frontend (Next.js)
```bash
bun install --cwd frontend       # Install dependencies
bun run --cwd frontend dev       # Development server (localhost:3000)
bun run --cwd frontend build     # Production build
bun run --cwd frontend lint      # ESLint
```

### Docker
```bash
cp .env.example .env
docker compose up -d --build
```

### CLI
```bash
tradingagents <commands>         # After pip install -e .
python main.py                   # Standalone analysis
```

## Architecture

### Agent System (`tradingagents/`)
- **12 AI agents** organized into teams using LangGraph orchestration
- `agents/analysts/` - Market, News, Social Media, Fundamentals analysts
- `agents/researchers/` - Bull & Bear case researchers + Research Manager
- `agents/risk_mgmt/` - Aggressive, Conservative, Neutral debaters + Risk Manager
- `agents/trader/` - Final trading decision aggregator
- `graph/trading_graph.py` - Main `TradingAgentsXGraph` class orchestrating the workflow
- `dataflows/` - Data vendor integrations (Yahoo Finance, Alpha Vantage, FinMind, Google News, Reddit)

### Backend (`backend/`)
- `app/main.py` - FastAPI app with security middleware (rate limiting 30/min, security headers)
- `app/api/routes.py` - `/api/analyze`, `/api/task/{id}`, `/api/chat`, `/api/download`
- `app/api/auth.py` - Google OAuth flow
- `app/services/trading_service.py` - Orchestrates agent graph execution
- `app/services/task_manager.py` - Async task lifecycle
- `app/services/pdf_generator.py` - Report generation (complex, 61KB)

### Frontend (`frontend/`)
- `app/` - Next.js App Router pages (analysis, history, auth)
- `components/AgentFlowDiagram.tsx` - 12-agent visualization
- `lib/crypto.ts` - AES-GCM encryption for API keys (BYOK model)
- `lib/reports-db.ts` - IndexedDB wrapper for local report storage
- `contexts/` - AuthContext, LanguageContext

## Key Entry Points

- **Backend**: `python -m backend` → `backend/__main__.py` → `backend/app/main.py`
- **Frontend**: `bun run dev` → `frontend/app/layout.tsx` → `frontend/app/page.tsx`
- **Core Logic**: `TradingAgentsXGraph.propagate(ticker, date)` in `tradingagents/graph/trading_graph.py`

## Environment Variables

Required in `.env` (see `.env.example`):
- LLM API keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, etc.
- Data APIs: `ALPHA_VANTAGE_API_KEY`, `FINMIND_API_KEY`
- Auth: `JWT_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- Config: `NEXT_PUBLIC_API_URL`, `CORS_ORIGINS`, `FRONTEND_URL`

## Key Dependencies

- **Agent Framework**: LangGraph 0.4.8+, LangChain 0.1.0+
- **LLM Providers**: langchain-openai, langchain-anthropic, langchain-google-genai
- **Data**: yfinance, pandas, polars, ChromaDB (vector store)
- **Backend**: FastAPI, SQLAlchemy 2.0+, Redis, asyncpg
- **Frontend**: Next.js 16, React 19, Tailwind CSS 4, shadcn/ui, Dexie.js (IndexedDB)
