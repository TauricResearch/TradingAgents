import json

from scripts.export_mt5_signal_levels_only import _make_signal


def test_make_signal_shape():
    levels = {
        "regime": "trend",
        "bias": "long",
        "entry_price": 2350.0,
        "stop_loss": 2338.0,
        "take_profit_1": 2362.0,
        "take_profit_2": 2375.0,
        "rr_target": 2.0,
        "regime_confidence": 0.8,
        "trailing_stop_atr_mult": 2.0,
        "entry_condition": "Trend long (confirmation): wait for close above ... then retest ...",
        "anchors": {"atr": 8.0, "atr_pct": 0.02, "swing_low": 2300.0, "swing_high": 2345.0},
    }
    sig = _make_signal(levels, symbol_mt5="XAUUSD", risk_usd=10.0, max_positions=2)
    assert sig["symbol"] == "XAUUSD"
    assert sig["action"] == "BUY"
    assert sig["pending_type"] == "BUY_STOP"
    assert json.loads(json.dumps(sig))["trailing"]["enabled"] is True
