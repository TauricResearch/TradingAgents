import json
import pytest
import fakeredis.aioredis
from datetime import datetime, timezone

from tradingagents.sensing.envelope import Envelope


def _env(text="Apple beats", source="polygon_news"):
    return Envelope(
        source=source,
        ingested_ts=datetime.now(timezone.utc).isoformat(),
        external_id="x:1", text=text, source_tags={}, raw_path="p",
    )


@pytest.fixture
def llm_factory():
    counter = {"n": 0}
    def factory(prompt: str) -> str:
        counter["n"] += 1
        return json.dumps({
            "salience": 0.85,
            "matched_tickers": ["AAPL"],
            "mentioned_tickers": [{"ticker": "AAPL", "confidence": 0.95}],
            "reason": "beats consensus",
        })
    return factory, counter


@pytest.mark.unit
async def test_salience_first_call_invokes_llm(llm_factory):
    from tradingagents.sensing.salience import SalienceScorer
    factory, counter = llm_factory
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    s = SalienceScorer(redis=r, llm_call=factory, cache_ttl_seconds=86400)
    result = await s.score(env=_env(), watchlist=["AAPL"], macro_context="")
    assert result.salience == pytest.approx(0.85)
    assert counter["n"] == 1


@pytest.mark.unit
async def test_salience_second_call_hits_cache(llm_factory):
    from tradingagents.sensing.salience import SalienceScorer
    factory, counter = llm_factory
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    s = SalienceScorer(redis=r, llm_call=factory, cache_ttl_seconds=86400)
    env = _env(text="Same text")
    await s.score(env=env, watchlist=["AAPL"], macro_context="")
    await s.score(env=env, watchlist=["AAPL"], macro_context="")
    assert counter["n"] == 1


@pytest.mark.unit
async def test_salience_handles_malformed_llm_json():
    from tradingagents.sensing.salience import SalienceScorer
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    s = SalienceScorer(
        redis=r,
        llm_call=lambda _: "not valid json at all",
        cache_ttl_seconds=86400,
    )
    result = await s.score(env=_env(), watchlist=[], macro_context="")
    assert 0.0 <= result.salience <= 0.3
    assert result.mentioned_tickers == []
    assert "fallback" in result.reason.lower() or "parse" in result.reason.lower()
