"""Salience scoring: cheap-LLM call per event with Redis caching.

The cache key is ``salience:<source>:<sha256(text)[:32]>`` so identical text
across sources still hits separately (different prompts), but re-deliveries
of the exact same source+text envelope are free.

LLM responses are parsed leniently — malformed JSON degrades to a
low-confidence fallback so a flaky model never stalls the pipeline.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import List, Sequence

import redis.asyncio as aioredis

from .envelope import Envelope
from .prompts import build_salience_prompt


@dataclass
class MentionedTicker:
    ticker: str
    confidence: float


@dataclass
class SalienceResult:
    salience: float
    matched_tickers: List[str] = field(default_factory=list)
    mentioned_tickers: List[MentionedTicker] = field(default_factory=list)
    reason: str = ""
    source: str = "llm"  # "llm" | "cache" | "fallback"


def _cache_key(env: Envelope) -> str:
    h = hashlib.sha256(env.text.encode("utf-8")).hexdigest()[:32]
    return f"salience:{env.source}:{h}"


def _parse(blob: str) -> SalienceResult:
    data = json.loads(blob)
    return SalienceResult(
        salience=float(data["salience"]),
        matched_tickers=list(data.get("matched_tickers", [])),
        mentioned_tickers=[
            MentionedTicker(ticker=m["ticker"], confidence=float(m["confidence"]))
            for m in data.get("mentioned_tickers", [])
        ],
        reason=str(data.get("reason", "")),
    )


def _serialize(r: SalienceResult) -> str:
    return json.dumps({
        "salience": r.salience,
        "matched_tickers": r.matched_tickers,
        "mentioned_tickers": [
            {"ticker": m.ticker, "confidence": m.confidence}
            for m in r.mentioned_tickers
        ],
        "reason": r.reason,
    })


class SalienceScorer:
    """Wraps any sync/async LLM call. Caches results in Redis."""

    def __init__(
        self,
        *,
        redis: aioredis.Redis,
        llm_call,  # Callable[[str], str | Awaitable[str]]
        cache_ttl_seconds: int,
    ) -> None:
        self._redis = redis
        self._llm = llm_call
        self._ttl = cache_ttl_seconds

    async def _invoke_llm(self, prompt: str) -> str:
        out = self._llm(prompt)
        if hasattr(out, "__await__"):
            out = await out
        return out

    async def score(
        self,
        *,
        env: Envelope,
        watchlist: Sequence[str],
        macro_context: str,
    ) -> SalienceResult:
        key = _cache_key(env)
        cached = await self._redis.get(key)
        if cached:
            result = _parse(cached)
            result.source = "cache"
            return result

        prompt = build_salience_prompt(env=env, watchlist=watchlist,
                                       macro_context=macro_context)
        try:
            raw = await self._invoke_llm(prompt)
            result = _parse(raw)
            result.source = "llm"
        except Exception as e:
            # Don't stall the pipeline — degrade to a fallback that flows through.
            result = SalienceResult(
                salience=0.1, matched_tickers=[], mentioned_tickers=[],
                reason=f"parse-fallback: {type(e).__name__}",
                source="fallback",
            )

        await self._redis.setex(key, self._ttl, _serialize(result))
        return result
