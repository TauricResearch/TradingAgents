import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
def test_deepdive_invokes_three_personas_then_secretary(tmp_path, monkeypatch):
    # Point the config at a temp DB and data dir.
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(tmp_path / "data"))

    from cli.deepdive import run_deepdive

    # Patch the engine so we don't actually call DeepSeek. Post-F4, the
    # per-persona helper lives in persona_runner; cli.deepdive now calls
    # run_personas_parallel directly. Patch the parallel helper.
    fake_run_ids = ["run1", "run2", "run3"]

    def fake_run_parallel(**kwargs):
        # Validate the helper got the personas we expect, return canned ids.
        personas = kwargs["personas"]
        return [fake_run_ids[i] for i in range(len(personas))]

    fake_secretary = MagicMock()
    fake_secretary.compose_deep_dive.return_value = "brief123"

    with patch("cli.deepdive.run_personas_parallel", side_effect=fake_run_parallel), \
         patch("cli.deepdive._build_secretary", return_value=fake_secretary):
        brief_id = run_deepdive(ticker="AAPL", trade_date="2026-05-25", parallel=False)

    assert brief_id == "brief123"
    fake_secretary.compose_deep_dive.assert_called_once()
    call_kwargs = fake_secretary.compose_deep_dive.call_args.kwargs
    assert call_kwargs["ticker"] == "AAPL"
    assert sorted(call_kwargs["run_ids"]) == sorted(fake_run_ids)


@pytest.mark.unit
def test_deepdive_typer_command_exists():
    """The Typer app must expose `deepdive` as a registered command."""
    from cli.main import app
    cmd_names = {info.name for info in app.registered_commands}
    assert "deepdive" in cmd_names
