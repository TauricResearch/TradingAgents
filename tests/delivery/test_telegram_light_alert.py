import pytest


@pytest.mark.unit
def test_light_alert_keyboard_has_per_ticker_buttons():
    pytest.importorskip("telegram")
    from tradingagents.delivery.telegram import _make_light_alert_keyboard

    kb = _make_light_alert_keyboard("lb1", ["NVDA", "PANW"])
    # Flatten all buttons and collect callback_data
    datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "act:lb1:run_full_study:NVDA" in datas
    assert "act:lb1:run_full_study:PANW" in datas
    assert "act:lb1:run_full_study:__all__" in datas
    assert "act:lb1:run_full_study:__dismiss__" in datas
