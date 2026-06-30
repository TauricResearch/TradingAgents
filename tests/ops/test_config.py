from decimal import Decimal
from ops.config import OpsConfig, load_config

def test_default_config_matches_spec():
    cfg = OpsConfig()
    # Spec section 3 defaults
    assert cfg.deny_list == {
        "SPOT",
        "TQQQ", "SQQQ", "UPRO", "SPXU", "UVXY", "SVXY",
        "SOXL", "SOXS", "LABU", "LABD", "TNA", "TZA",
        "TMF", "TMV", "QLD", "QID",
    }
    assert cfg.per_position_cap_pct == Decimal("0.10")
    assert cfg.per_trade_dollar_floor == Decimal("5")
    assert cfg.max_open_positions == 5
    assert cfg.cash_reserve_pct == Decimal("0.20")
    assert cfg.daily_drawdown_pct == Decimal("-0.07")
    assert cfg.weekly_drawdown_pct == Decimal("-0.15")
    assert cfg.per_position_stop_pct == Decimal("-0.08")
    assert cfg.broker_mode == "paper"

def test_load_config_reads_env_overrides(monkeypatch):
    monkeypatch.setenv("OPS_BROKER_MODE", "robinhood")
    monkeypatch.setenv("OPS_PER_POSITION_CAP_PCT", "0.05")
    cfg = load_config()
    assert cfg.broker_mode == "robinhood"
    assert cfg.per_position_cap_pct == Decimal("0.05")
