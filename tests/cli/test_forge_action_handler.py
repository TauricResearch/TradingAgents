from unittest.mock import MagicMock, patch
import pytest


@pytest.mark.unit
def test_action_handler_run_loops_until_keyboard_interrupt(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(tmp_path / "data"))
    import importlib, tradingagents.default_config as dc
    importlib.reload(dc)

    call_count = {"n": 0}
    def fake_tick(**kwargs):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise KeyboardInterrupt
    with patch("tradingagents.orchestrator.action_handler.tick", side_effect=fake_tick), \
         patch("time.sleep", return_value=None), \
         patch("cli.action_handler._build_secretary", return_value=MagicMock()):
        from cli.action_handler import action_handler_run
        action_handler_run()
    assert call_count["n"] == 2
