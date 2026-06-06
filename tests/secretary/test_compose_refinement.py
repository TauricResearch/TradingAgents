from unittest.mock import MagicMock, patch
import pytest

from tradingagents.persistence.db import connect as iic_connect
from tradingagents.persistence import store


def _seed_parent(conn, brief_id="b1", depth=0, mode="deep_dive"):
    store.insert_brief(
        conn, brief_id=brief_id, mode=mode, scope="AAPL",
        generated_ts="2026-05-27T12:00:00+00:00",
        content_path=f"briefs/{brief_id}.md", run_ids=["rp"],
    )
    if depth:
        conn.execute(
            "UPDATE briefs SET refine_depth = ? WHERE brief_id = ?",
            (depth, brief_id),
        )
        conn.commit()


@pytest.mark.unit
def test_compose_refinement_writes_child_brief_with_parent_link(tmp_path):
    from tradingagents.secretary.service import Secretary

    conn = iic_connect(str(tmp_path / "iic.db"))
    data_dir = tmp_path / "data"
    _seed_parent(conn)

    def fake_run_ticker(*, ticker, trade_date, config, conn, data_dir):
        store.insert_run(conn, run_id="rc", ticker=ticker, persona_id="macro",
                         started_ts="2026-05-27T13:00:00+00:00",
                         artifact_dir="runs/rc")
        store.finalize_run(conn, run_id="rc",
                           ended_ts="2026-05-27T13:05:00+00:00",
                           status="ok", decision="SELL", confidence=0.6)
        return ["rc"], {"consensus": "C", "divergence": "D",
                        "recommendation": "SELL", "raw": ""}

    overrides = {"personas": ["macro"], "risk_tilt": "more_conservative",
                 "horizon": None, "analysts": None,
                 "interpretation": "Macro-only, conservative."}
    with patch("tradingagents.secretary.service.run_one_ticker", side_effect=fake_run_ticker):
        sec = Secretary(conn=conn, data_dir=str(data_dir), llm=MagicMock())
        new_id = sec.compose_refinement(
            parent_brief_id="b1", overrides=overrides,
            reply_text="just macro, more conservative",
        )

    row = conn.execute(
        "SELECT mode, parent_brief_id, refine_depth, refine_overrides "
        "FROM briefs WHERE brief_id = ?", (new_id,),
    ).fetchone()
    assert row[0] == "deep_dive"
    assert row[1] == "b1"
    assert row[2] == 1
    import json as _j
    assert _j.loads(row[3])["risk_tilt"] == "more_conservative"


@pytest.mark.unit
def test_compose_refinement_depth_cap_raises(tmp_path):
    from tradingagents.secretary.service import Secretary, RefinementDepthExceeded

    conn = iic_connect(str(tmp_path / "iic.db"))
    data_dir = tmp_path / "data"
    _seed_parent(conn, depth=3)

    sec = Secretary(conn=conn, data_dir=str(data_dir), llm=MagicMock())
    with pytest.raises(RefinementDepthExceeded):
        sec.compose_refinement(
            parent_brief_id="b1",
            overrides={"personas": None, "risk_tilt": None, "horizon": None,
                       "analysts": None, "interpretation": ""},
            reply_text="more refinement",
        )


@pytest.mark.unit
def test_compose_refinement_does_not_modify_persona_yaml(tmp_path):
    """Overrides are in-memory only — persona YAML files on disk unchanged."""
    from tradingagents.secretary.service import Secretary

    conn = iic_connect(str(tmp_path / "iic.db"))
    _seed_parent(conn)

    yaml_dir = tmp_path / "personas"
    yaml_dir.mkdir()
    (yaml_dir / "macro.yaml").write_text("id: macro\nllm:\n  deep_think_llm: x\n")
    before = (yaml_dir / "macro.yaml").read_text()

    def fake_run(*, ticker, trade_date, config, conn, data_dir):
        store.insert_run(conn, run_id="rc", ticker=ticker, persona_id="macro",
                         started_ts="2026-05-27T13:00:00+00:00", artifact_dir="runs/rc")
        store.finalize_run(conn, run_id="rc",
                           ended_ts="2026-05-27T13:05:00+00:00",
                           status="ok", decision="HOLD", confidence=0.5)
        return ["rc"], {"consensus": "", "divergence": "", "recommendation": "HOLD", "raw": ""}

    with patch("tradingagents.secretary.service.run_one_ticker", side_effect=fake_run):
        sec = Secretary(conn=conn, data_dir=str(tmp_path / "data"), llm=MagicMock())
        sec.compose_refinement(
            parent_brief_id="b1",
            overrides={"personas": ["macro"], "risk_tilt": None, "horizon": None,
                       "analysts": None, "interpretation": ""},
            reply_text="just macro",
        )
    after = (yaml_dir / "macro.yaml").read_text()
    assert before == after
