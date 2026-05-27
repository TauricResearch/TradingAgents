from unittest.mock import MagicMock, patch
import io
import pytest

from tradingagents.persistence.db import connect as iic_connect
from tradingagents.persistence import store


@pytest.mark.unit
def test_post_delivery_prompts_backtest_yes_writes_action(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(tmp_path / "data"))
    import importlib, tradingagents.default_config as dc
    importlib.reload(dc)

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b1", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-27T12:00:00+00:00",
        content_path="briefs/b1.md", run_ids=["r1"],
    )

    fake_in = io.StringIO("y\n\n")
    monkeypatch.setattr("sys.stdin", fake_in)

    from cli.deepdive import post_delivery_prompts
    post_delivery_prompts(brief_id="b1", conn=conn)

    actions = conn.execute(
        "SELECT action_type, state FROM brief_actions"
    ).fetchall()
    types = sorted([(a[0], a[1]) for a in actions])
    assert ("run_backtest", "accepted") in types


@pytest.mark.unit
def test_post_delivery_prompts_refinement_loop(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(tmp_path / "data"))
    import importlib, tradingagents.default_config as dc
    importlib.reload(dc)

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b1", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-27T12:00:00+00:00",
        content_path="briefs/b1.md", run_ids=["r1"],
    )

    fake_in = io.StringIO("n\nmore aggressive\n\n")
    monkeypatch.setattr("sys.stdin", fake_in)

    from cli.deepdive import post_delivery_prompts
    post_delivery_prompts(brief_id="b1", conn=conn)

    refinements = conn.execute(
        "SELECT action_type, action_params FROM brief_actions WHERE action_type = 'refine_brief'"
    ).fetchall()
    assert len(refinements) == 1
    import json as _j
    assert _j.loads(refinements[0][1])["reply_text"] == "more aggressive"


@pytest.mark.unit
def test_post_delivery_prompts_empty_input_skips_everything(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(tmp_path / "data"))
    import importlib, tradingagents.default_config as dc
    importlib.reload(dc)

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b1", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-27T12:00:00+00:00",
        content_path="briefs/b1.md", run_ids=["r1"],
    )

    fake_in = io.StringIO("\n\n")
    monkeypatch.setattr("sys.stdin", fake_in)

    from cli.deepdive import post_delivery_prompts
    post_delivery_prompts(brief_id="b1", conn=conn)

    assert conn.execute("SELECT COUNT(*) FROM brief_actions").fetchone()[0] == 0
