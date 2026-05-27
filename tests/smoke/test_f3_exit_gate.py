"""F3 exit-gate smoke — synthetic data through the evaluator end-to-end."""

import json
import pytest
import fakeredis.aioredis
from datetime import datetime, timezone, timedelta

from tradingagents.persistence.db import connect
from tradingagents.persistence.store import upsert_ticker
from tradingagents.sensing.envelope import Envelope


pytestmark = pytest.mark.smoke


def _llm():
    def call(_p):
        return json.dumps({"salience": 0.9, "matched_tickers": ["AAPL"],
                            "mentioned_tickers": [{"ticker": "AAPL",
                                                    "confidence": 0.95}],
                            "reason": "test"})
    return call


async def test_f3_smoke_synthetic_24h_window(tmp_path):
    from tradingagents.sensing.triage import Triage
    from tradingagents.sensing.embeddings import MockEmbedder
    from scripts.f3_exit_gate import evaluate

    db = tmp_path / "iic.db"
    conn = connect(str(db))
    upsert_ticker(conn, ticker="AAPL", exchange="NASDAQ",
                  name="Apple Inc.", aliases=[], active=True)

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    t = Triage(conn=conn, redis=redis, embedder=MockEmbedder(),
               llm_call=_llm(),
               data_dir=str(tmp_path / "data"))

    # Push 120 unique events + 80 duplicates of the first 80 of them.
    base = datetime.now(timezone.utc) - timedelta(hours=12)
    uniques = []
    for i in range(120):
        env = Envelope(
            source="polygon_news",
            ingested_ts=(base + timedelta(seconds=i)).isoformat(),
            external_id=f"pn:{i}", text=f"Apple update #{i} unique content body",
            source_tags={}, raw_path="",
        )
        uniques.append(env)
        await t.process_one(env)
    for i in range(80):
        await t.process_one(uniques[i])  # exact replay → duplicate

    res = evaluate(db_path=str(db), since=base - timedelta(minutes=1),
                   check_systemd=False)
    assert res.events_total == 200
    assert res.duplicates == 80
    assert res.active == 120
    assert res.autos >= 1
    assert res.passed_auto is True
