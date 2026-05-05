from tradingagents.agents.utils.trade_filter_calibration import evaluate_config
from tradingagents.agents.utils.trade_filter_calibration import TradeCalibrationRow


def test_evaluate_config_selects_higher_scores():
    rows = [
        TradeCalibrationRow(
            ticker="AAA",
            date="2026-01-01",
            r_mult=1.0,
            market_q=0.9,
            execution_q=0.9,
            signal_q=0.9,
            hard_reject=False,
        ),
        TradeCalibrationRow(
            ticker="BBB",
            date="2026-01-02",
            r_mult=-1.0,
            market_q=0.2,
            execution_q=0.2,
            signal_q=0.2,
            hard_reject=False,
        ),
    ]
    res = evaluate_config(
        rows,
        w_market=0.5,
        w_execution=0.3,
        w_signal=0.2,
        threshold=0.7,
        min_count=1,
        objective="mean_r",
    )
    assert res["n"] == 1
    assert res["mean_r"] > 0
