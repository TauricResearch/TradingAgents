import json
import pytest
import fakeredis.aioredis
from unittest.mock import patch, MagicMock

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
async def test_x_emits_envelope_for_each_tweet(conn, tmp_path, monkeypatch):
    from tradingagents.sensing.adapters.x import XAdapter
    monkeypatch.setenv("X_BEARER_TOKEN", "fake")

    tweet = MagicMock()
    tweet.id = 7777
    tweet.text = "$AAPL ripping on earnings"
    tweet.created_at.isoformat.return_value = "2026-05-26T12:00:00+00:00"
    tweet.author_id = 99
    response = MagicMock(); response.data = [tweet]

    fake_client = MagicMock()
    fake_client.search_recent_tweets.return_value = response
    with patch("tradingagents.sensing.adapters.x.tweepy.Client",
               return_value=fake_client):
        r = fakeredis.aioredis.FakeRedis(decode_responses=True)
        a = XAdapter(query="$AAPL OR $TSLA",
                      staging_root=str(tmp_path / "s"), stream="ingest:raw")
        n = await a.poll_once(redis=r, conn=conn)
    assert n == 1
    env = json.loads((await r.xrange("ingest:raw"))[0][1]["data"])
    assert env["source"] == "x"
    assert env["external_id"] == "x:7777"


@pytest.mark.unit
def test_x_main_exits_zero_when_disabled(monkeypatch, capsys):
    """When the adapter is disabled, _main returns cleanly (exit 0)."""
    from tradingagents.sensing.adapters import x as xmod
    from tradingagents.default_config import DEFAULT_CONFIG
    monkeypatch.setitem(DEFAULT_CONFIG["sensing_adapters_enabled"], "x", False)
    # _main should return None (no SystemExit raised).
    assert xmod._main() is None
