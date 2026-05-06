"""Real-time price + news WebSocket endpoints.

    GET  /streaming/state        — last-known snapshot for all watched tickers (REST, fast)
    WS   /streaming/{ticker}     — combined price + news stream for one ticker
    WS   /streaming/price/{ticker}
    WS   /streaming/news/{ticker}
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from service.streaming import broadcaster

router = APIRouter(prefix="/streaming", tags=["streaming"])


@router.get("/state")
def state() -> Dict[str, Any]:
    """Return the last-known price snapshot for every ticker we've polled."""
    out = {}
    for ticker, st in broadcaster._state.items():  # internal access; small surface
        if st.last_price is None:
            continue
        out[ticker] = {
            "ticker": ticker,
            "price": st.last_price,
            "change": st.last_change,
            "change_pct": st.last_change_pct,
            "volume": st.last_volume,
            "polled_at": st.last_polled,
        }
    return {"prices": out}


async def _stream_channel(ws: WebSocket, channel: str, ticker: str) -> None:
    """Subscribe to one channel, forward events to the WS until disconnect."""
    await ws.accept()
    q = await broadcaster.subscribe(channel, ticker)
    try:
        while True:
            ev = await q.get()
            await ws.send_text(json.dumps(ev, default=str))
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.unsubscribe(channel, ticker, q)
        try:
            await ws.close()
        except RuntimeError:
            pass


@router.websocket("/price/{ticker}")
async def price_stream(ws: WebSocket, ticker: str) -> None:
    await _stream_channel(ws, "price", ticker)


@router.websocket("/news/{ticker}")
async def news_stream(ws: WebSocket, ticker: str) -> None:
    await _stream_channel(ws, "news", ticker)


@router.websocket("/{ticker}")
async def combined_stream(ws: WebSocket, ticker: str) -> None:
    """Convenience: subscribes to both ``price`` and ``news`` for a ticker
    and multiplexes both streams onto a single WebSocket."""
    await ws.accept()
    pq = await broadcaster.subscribe("price", ticker)
    nq = await broadcaster.subscribe("news", ticker)
    try:
        async def relay(q):
            while True:
                ev = await q.get()
                await ws.send_text(json.dumps(ev, default=str))
        await asyncio.gather(relay(pq), relay(nq))
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.unsubscribe("price", ticker, pq)
        await broadcaster.unsubscribe("news", ticker, nq)
        try:
            await ws.close()
        except RuntimeError:
            pass
