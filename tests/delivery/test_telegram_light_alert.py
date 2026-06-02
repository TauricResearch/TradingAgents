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


@pytest.mark.unit
def test_light_alert_keyboard_odd_ticker_count_layout():
    pytest.importorskip("telegram")
    from tradingagents.delivery.telegram import _make_light_alert_keyboard

    kb = _make_light_alert_keyboard("lb1", ["NVDA", "PANW", "CRWD"])
    rows = kb.inline_keyboard
    # 3 tickers -> [2 buttons][1 button][all/dismiss row]
    assert len(rows) == 3
    assert len(rows[0]) == 2
    assert len(rows[1]) == 1
    assert rows[1][0].callback_data == "act:lb1:run_full_study:CRWD"
    # final row is the all/dismiss controls
    assert [b.callback_data for b in rows[2]] == [
        "act:lb1:run_full_study:__all__",
        "act:lb1:run_full_study:__dismiss__",
    ]
