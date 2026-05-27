from unittest.mock import MagicMock, patch
import pytest

from tradingagents.persistence.db import connect as iic_connect
from tradingagents.persistence import store


@pytest.mark.unit
def test_morning_digest_now_invokes_compose_and_delivers(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(tmp_path / "data"))
    import importlib, tradingagents.default_config as dc
    importlib.reload(dc)

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.upsert_watchlist(conn, ticker="AAPL", ttl_until=None, tags=["user"])

    with patch("cli.morning._build_secretary") as builder, \
         patch("cli.morning._build_channels") as channels:
        sec = MagicMock()
        sec.compose_morning_digest.return_value = "br1"
        builder.return_value = (sec, conn)

        ch_cli = MagicMock(); ch_cli.send.return_value = 1
        ch_email = MagicMock(); ch_email.send.return_value = 2
        channels.return_value = {"cli": ch_cli, "email": ch_email}

        (tmp_path / "data" / "briefs").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "briefs" / "br1.md").write_text("BODY")
        # Insert brief row so load_brief works
        store.insert_brief(
            conn, brief_id="br1", mode="morning_digest", scope='["AAPL"]',
            generated_ts="2026-05-27T07:00:00+00:00",
            content_path="briefs/br1.md", run_ids=["r1"],
        )

        from cli.morning import morning_digest_now
        morning_digest_now(dry_run=False)

    sec.compose_morning_digest.assert_called_once()
    ch_cli.send.assert_called_once()
    ch_email.send.assert_called_once()


@pytest.mark.unit
def test_morning_digest_dry_run_skips_sends(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(tmp_path / "data"))
    import importlib, tradingagents.default_config as dc
    importlib.reload(dc)

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.upsert_watchlist(conn, ticker="AAPL", ttl_until=None, tags=["user"])

    with patch("cli.morning._build_secretary") as builder, \
         patch("cli.morning._build_channels") as channels:
        sec = MagicMock()
        sec.compose_morning_digest.return_value = "br1"
        builder.return_value = (sec, conn)

        ch_cli = MagicMock()
        channels.return_value = {"cli": ch_cli}

        (tmp_path / "data" / "briefs").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "briefs" / "br1.md").write_text("BODY")

        from cli.morning import morning_digest_now
        morning_digest_now(dry_run=True)

    sec.compose_morning_digest.assert_called_once()
    ch_cli.send.assert_not_called()


@pytest.mark.unit
def test_digest_tail_prints_latest(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(tmp_path / "data"))
    import importlib, tradingagents.default_config as dc
    importlib.reload(dc)

    conn = iic_connect(str(tmp_path / "iic.db"))
    (tmp_path / "data" / "briefs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "briefs" / "br1.md").write_text("LATEST DIGEST")

    store.insert_brief(
        conn, brief_id="br1", mode="morning_digest", scope='["AAPL"]',
        generated_ts="2026-05-27T07:00:00+00:00",
        content_path="briefs/br1.md", run_ids=["r1"],
    )

    from cli.morning import digest_tail
    digest_tail()
    captured = capsys.readouterr()
    assert "LATEST DIGEST" in captured.out
