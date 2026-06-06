from unittest.mock import MagicMock, patch

from tradingagents.analysis_pack.store import create_analysis_pack
from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.secretary.service import Secretary


def test_compose_refinement_threads_parent_analysis_pack(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    data_dir = tmp_path / "data"
    store.insert_event(
        conn,
        event_id="ev1",
        source="rss",
        ingested_ts="2026-06-01T00:00:00+00:00",
        salience=0.9,
        raw_path=None,
        status="triaged",
        deduped_of=None,
    )
    pack_id = create_analysis_pack(
        conn=conn,
        data_dir=data_dir,
        event_id="ev1",
        ticker="NVDA",
        trade_date="2026-06-01",
        source_run_ids=["r1"],
        content={
            "ticker": "NVDA",
            "event_context": "event",
            "reports": {"news_report": "news"},
        },
    )
    store.insert_brief(
        conn,
        brief_id="full1",
        mode="event_alert",
        scope="NVDA",
        generated_ts="2026-06-01T00:00:00+00:00",
        content_path="briefs/full1.md",
        run_ids=["r1"],
    )
    store.update_brief_analysis_pack(conn, brief_id="full1", analysis_pack_id=pack_id)
    sec = Secretary(conn=conn, data_dir=str(data_dir), llm=MagicMock())

    with patch("tradingagents.secretary.service.run_one_ticker") as run_one:
        run_one.return_value = (
            ["r2"],
            {"consensus": "c", "divergence": "d", "recommendation": "r"},
        )
        sec.compose_refinement(
            parent_brief_id="full1",
            overrides={"risk_tilt": "more_aggressive"},
            reply_text="more aggressive",
        )

    called_config = run_one.call_args.kwargs["config"]
    assert "prior_analysis_pack" in called_config
    assert called_config["prior_analysis_pack"]["content"]["reports"]["news_report"] == "news"
