import pytest
from datetime import datetime, timezone, timedelta

from tradingagents.persistence.db import connect
from tradingagents.persistence.store import insert_event, insert_event_embedding


def _insert_with_vec(conn, *, event_id, vec, ingested_ts=None):
    ts = ingested_ts or datetime.now(timezone.utc).isoformat()
    insert_event(conn, event_id=event_id, source="rss", ingested_ts=ts,
                 salience=0.5, raw_path=f"data/events/{event_id}.json",
                 status="triaged", deduped_of=None)
    cur = conn.execute(
        "INSERT INTO vec_index (embedding) VALUES (?)",
        (bytes(__import__("struct").pack(f"{len(vec)}f", *vec)),),
    )
    insert_event_embedding(conn, event_id=event_id, vec_id=cur.lastrowid)
    return cur.lastrowid


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
def test_stage2_no_neighbor_returns_none(conn):
    from tradingagents.sensing.dedupe import DedupeStage2
    from tradingagents.sensing.embeddings import MockEmbedder
    ds2 = DedupeStage2(conn=conn, embedder=MockEmbedder(),
                       cosine_threshold=0.92, window_hours=24)
    assert ds2.check("first item ever") is None


@pytest.mark.unit
def test_stage2_identical_text_is_duplicate(conn):
    from tradingagents.sensing.dedupe import DedupeStage2
    from tradingagents.sensing.embeddings import MockEmbedder
    emb = MockEmbedder()
    vec = emb.embed("Apple beats earnings")
    _insert_with_vec(conn, event_id="ev-1", vec=vec)
    ds2 = DedupeStage2(conn=conn, embedder=emb,
                       cosine_threshold=0.92, window_hours=24)
    assert ds2.check("Apple beats earnings") == "ev-1"


@pytest.mark.unit
def test_stage2_dissimilar_text_is_not_duplicate(conn):
    from tradingagents.sensing.dedupe import DedupeStage2
    from tradingagents.sensing.embeddings import MockEmbedder
    emb = MockEmbedder()
    _insert_with_vec(conn, event_id="ev-1", vec=emb.embed("Apple beats"))
    ds2 = DedupeStage2(conn=conn, embedder=emb,
                       cosine_threshold=0.92, window_hours=24)
    assert ds2.check("Federal Reserve raises rates 25 bps") is None


@pytest.mark.unit
def test_stage2_window_excludes_old_events(conn):
    from tradingagents.sensing.dedupe import DedupeStage2
    from tradingagents.sensing.embeddings import MockEmbedder
    emb = MockEmbedder()
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    _insert_with_vec(conn, event_id="ev-old", vec=emb.embed("xyz"),
                     ingested_ts=old_ts)
    ds2 = DedupeStage2(conn=conn, embedder=emb,
                       cosine_threshold=0.92, window_hours=24)
    assert ds2.check("xyz") is None  # outside 24h window


@pytest.mark.unit
def test_stage2_record_inserts_embedding_and_returns_vec_id(conn):
    from tradingagents.sensing.dedupe import DedupeStage2
    from tradingagents.sensing.embeddings import MockEmbedder
    insert_event(conn, event_id="ev-new", source="rss",
                 ingested_ts=datetime.now(timezone.utc).isoformat(),
                 salience=0.5, raw_path="p", status="triaged", deduped_of=None)
    ds2 = DedupeStage2(conn=conn, embedder=MockEmbedder(),
                       cosine_threshold=0.92, window_hours=24)
    vec_id = ds2.record(text="anything", event_id="ev-new")
    assert isinstance(vec_id, int)
    row = conn.execute(
        "SELECT vec_id FROM event_embeddings WHERE event_id='ev-new'"
    ).fetchone()
    assert row["vec_id"] == vec_id
