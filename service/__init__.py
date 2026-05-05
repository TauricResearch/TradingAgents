"""FastAPI service exposing TradingAgents runs over REST + WebSockets.

This package is the long-term replacement for the Streamlit GUI. The
expensive backend modules (``runner_worker``, ``brief``, ``chat``,
``export``, ``charts``, ``storage``) live under ``gui/`` for now and
are imported here directly — they're framework-independent Python.

Layout:
    service/
        app.py              FastAPI app + CORS + router includes
        runner_pool.py      In-process registry of running analyses
        schemas.py          Pydantic request/response models
        routers/
            health.py
            runs.py         POST/GET runs + WS /runs/{id}/stream
            briefs.py
            chat.py         GET messages + WS /runs/{id}/chat for streaming answers
            notes.py
            settings.py
            memory.py
            charts.py       Ticker vs SPY/QQQ comparison
            exports.py      Per-format download endpoints
"""
