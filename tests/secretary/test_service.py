import pytest
import uuid
from unittest.mock import MagicMock
from datetime import datetime, timezone


@pytest.fixture
def db_and_dirs(tmp_path):
    from tradingagents.persistence.db import connect
    conn = connect(str(tmp_path / "iic.db"))
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "runs").mkdir()
    (data_dir / "briefs").mkdir()
    return conn, str(data_dir)


@pytest.mark.unit
def test_compose_deep_dive_writes_brief_row_and_md(db_and_dirs):
    """End-to-end with mocked LLM and pre-seeded run rows."""
    from tradingagents.secretary.service import Secretary
    from tradingagents.persistence import store

    conn, data_dir = db_and_dirs
    # Seed three runs and their per-analyst markdown.
    run_ids = []
    for pid in ("macro", "value", "momentum"):
        rid = uuid.uuid4().hex
        run_ids.append(rid)
        now = datetime.now(timezone.utc).isoformat()
        store.insert_run(conn, run_id=rid, ticker="AAPL", persona_id=pid,
                         started_ts=now, artifact_dir=f"runs/{rid}")
        store.finalize_run(conn, run_id=rid, ended_ts=now, status="complete",
                           decision="BUY" if pid != "macro" else "SELL")

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(content="""
## Consensus
Cashflow is strong.

## Divergence
Macro says SELL.

## Recommendation
HOLD — low-confidence call.
""")
    sec = Secretary(conn=conn, data_dir=data_dir, llm=fake_llm)
    brief_id = sec.compose_deep_dive(
        ticker="AAPL",
        run_ids=run_ids,
        trade_date="2026-05-25",
    )
    # DB row exists
    row = conn.execute("SELECT * FROM briefs WHERE brief_id=?",
                       (brief_id,)).fetchone()
    assert row is not None
    assert row["mode"] == "deep_dive"
    assert row["scope"] == "AAPL"
    # Markdown on disk
    from pathlib import Path
    md_path = Path(data_dir) / row["content_path"]
    assert md_path.exists()
    text = md_path.read_text(encoding="utf-8")
    assert "AAPL" in text
    assert "Consensus" in text
    assert "Divergence" in text


@pytest.mark.unit
def test_compose_deep_dive_delivers_when_enabled(db_and_dirs, monkeypatch):
    """When requested, deep-dive composition fans out through delivery channels."""
    from tradingagents.secretary.service import Secretary
    from tradingagents.persistence import store

    conn, data_dir = db_and_dirs
    run_ids = []
    for pid in ("macro", "value", "momentum"):
        rid = uuid.uuid4().hex
        run_ids.append(rid)
        now = datetime.now(timezone.utc).isoformat()
        store.insert_run(conn, run_id=rid, ticker="AAPL", persona_id=pid,
                         started_ts=now, artifact_dir=f"runs/{rid}")
        store.finalize_run(conn, run_id=rid, ended_ts=now, status="complete",
                           decision="BUY" if pid != "macro" else "SELL")

    monkeypatch.setattr(
        "tradingagents.secretary.service.synthesize_brief",
        lambda **kw: {
            "consensus": "Cashflow is strong.",
            "divergence": "Macro says SELL.",
            "recommendation": "HOLD - low-confidence call.",
        },
    )

    sent = []

    class FakeChannel:
        def __init__(self, name):
            self.name = name

        def send(self, *, brief, mode, body):
            sent.append({"brief": brief, "mode": mode, "body": body})
            return store.insert_delivery(
                conn,
                brief_id=brief["brief_id"],
                channel=self.name,
                status="sent",
                sent_ts=datetime.now(timezone.utc).isoformat(),
                channel_ref=self.name,
                skip_reason=None,
            )

    monkeypatch.setattr(
        "tradingagents.secretary.service._build_channel",
        lambda name, conn, config: FakeChannel(name),
    )

    sec = Secretary(conn=conn, data_dir=data_dir, llm=MagicMock())
    brief_id = sec.compose_deep_dive(
        ticker="AAPL",
        run_ids=run_ids,
        trade_date="2026-05-25",
        deliver=True,
    )

    assert sent
    assert {call["mode"] for call in sent} == {"deep_dive"}
    assert all(call["brief"]["brief_id"] == brief_id for call in sent)
    assert all(call["brief"]["tickers"][0]["ticker"] == "AAPL" for call in sent)
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM deliveries WHERE brief_id = ? AND status = 'sent'",
        (brief_id,),
    ).fetchone()
    assert row["n"] == len(sent)

