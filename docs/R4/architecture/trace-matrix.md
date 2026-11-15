# R4 Requirement Trace Matrix

This matrix covers the R4 contribution only. The requirement is in [requirements.yaml](../req/requirements.yaml). The tests below use local fixed prices; live evidence is listed separately.

| Acceptance point | Implementation | Verification |
| --- | --- | --- |
| R4-A1: default five sessions, override, and rejection of nonpositive values | [`default_config.py`](../../../tradingagents/default_config.py) | Default, override, and invalid-value cases in [`test_cost_adjusted_returns.py`](../../../tests/test_cost_adjusted_returns.py) |
| R4-A2: round-trip cost deduction and matching alpha adjustment | `apply_trading_costs` in [`settlement.py`](../../../tradingagents/memory/settlement.py) | `test_round_trip_cost_example`, `test_negative_return_and_total_loss` |
| R4-A3: gross behavior when the switch is off | `settle_pending` in [`settlement.py`](../../../tradingagents/memory/settlement.py) | `test_switch_off_preserves_gross_settlement` |
| R4-A4: minimum commission converted using assumed notional | `apply_trading_costs` in [`settlement.py`](../../../tradingagents/memory/settlement.py) | `test_minimum_commission_uses_assumed_notional_per_side` |
| R4-A5: pending before maturity, one settlement after maturity, gross/net reflection inputs | [`settlement.py`](../../../tradingagents/memory/settlement.py), [`reflection.py`](../../../tradingagents/memory/reflection.py) | `test_incomplete_window_stays_pending_without_reflection`, `test_cost_adjusted_settlement_passes_both_values_and_writes_net`, `test_reflection_shows_gross_and_net_with_regional_benchmark` |

Manual live verification has three levels: `tests/test_cost_adjusted_returns_live.py` calls the course model with simulated prices; `tests/verify_r4_yahoo_live.py` settles using real Yahoo historical prices and generates a reflection; `tests/verify_r4_cli_live.py` runs the full CLI. The run record is `R4测试记录.md` in the parent directory and contains no API key. Default CI excludes tests marked `integration`; an offline pass must not be reported as a live pass.
