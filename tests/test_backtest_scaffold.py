"""Phase 5 — backtest scaffolding tests.

No LLM invocations: only the metrics math, fixture IO, and grid expansion.
A real sweep is intentional and lives outside the test suite.
"""

from __future__ import annotations

import math

import pytest

from tradingagents.backtest import metrics, sweep
from tradingagents.backtest.data_collector import (
    HistoricalContract,
    fixtures_dir,
    list_fixtures,
    load_contract,
    save_contract,
)


def _record(side, p_committee, p_market, outcome, stake=10.0, conf="medium"):
    realized = (10.0 if (side != "PASS" and side == outcome) else 0.0) - (
        stake if side != "PASS" else 0.0
    )
    return metrics.BacktestRecord(
        contract_id="KXBTCD-26MAY05-T100000",
        decision_date="2026-05-05",
        side=side,
        p_yes_committee=p_committee,
        p_yes_market=p_market,
        edge_bps=(p_committee - p_market) * 10000,
        confidence=conf,
        kelly_fraction=0.04,
        stake_usd=stake if side != "PASS" else 0.0,
        settlement_outcome=outcome,
        realized_pnl_usd=realized,
    )


@pytest.mark.unit
class TestMetrics:
    def test_summary_with_mixed_outcomes(self):
        records = [
            _record("YES", 0.62, 0.55, "YES"),
            _record("YES", 0.62, 0.55, "NO"),
            _record("NO", 0.30, 0.45, "NO"),
            _record("PASS", 0.50, 0.50, "YES"),
        ]
        df = metrics.to_df(records)
        s = metrics.summary(df)
        assert s["n_decisions"] == 4
        assert s["n_executed"] == 3
        assert s["n_passed"] == 1
        assert math.isclose(s["hit_rate"], 2 / 3)

    def test_calibration_returns_table(self):
        records = [_record("YES", 0.7, 0.5, "YES") for _ in range(5)]
        df = metrics.to_df(records)
        cal = metrics.calibration(df, bins=5)
        # Check there's a bin with 0.6 < p_predicted ≤ 0.8 and all 5 trades there.
        nonempty = cal[cal["n_trades"] > 0]
        assert len(nonempty) == 1
        assert int(nonempty.iloc[0]["n_trades"]) == 5
        assert math.isclose(nonempty.iloc[0]["empirical_win_rate"], 1.0)


@pytest.mark.unit
class TestFixtures:
    def test_save_and_load_roundtrip(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "tradingagents.backtest.data_collector.fixtures_dir",
            lambda: tmp_path,
        )
        original = HistoricalContract(
            contract_id="KXBTCD-26MAY05-T100000",
            decision_date="2026-05-05",
            settlement_outcome="YES",
            kalshi_p_yes_at_decision=0.55,
            candles_to_decision=[
                {"time": "2026-05-04T00:00:00+00:00", "open": 80000, "high": 81000,
                 "low": 79500, "close": 80500, "volume": 12345.6},
            ],
        )
        save_contract(original, name="sample.json")
        assert "sample.json" in list_fixtures()
        loaded = load_contract("sample.json")
        assert loaded.contract_id == original.contract_id
        assert loaded.settlement_outcome == "YES"


@pytest.mark.unit
class TestGridExpansion:
    def test_empty_grid_yields_single_empty_combo(self):
        combos = sweep._expand_grid({})
        assert combos == [{}]

    def test_two_axis_grid_yields_cartesian_product(self):
        combos = sweep._expand_grid({"a": [1, 2], "b": [10, 20, 30]})
        assert len(combos) == 6
        # Order is stable within an axis.
        assert {tuple(sorted(c.items())) for c in combos} == {
            (("a", 1), ("b", 10)),
            (("a", 1), ("b", 20)),
            (("a", 1), ("b", 30)),
            (("a", 2), ("b", 10)),
            (("a", 2), ("b", 20)),
            (("a", 2), ("b", 30)),
        }

    def test_pareto_mask_keeps_dominant_rows(self):
        import pandas as pd
        df = pd.DataFrame([
            {"hit_rate": 0.50, "total_pnl_usd": 100.0},
            {"hit_rate": 0.55, "total_pnl_usd": 90.0},   # not dominated
            {"hit_rate": 0.45, "total_pnl_usd": 80.0},   # dominated by row 0
            {"hit_rate": 0.60, "total_pnl_usd": 110.0},  # dominates 0 & 1 & 2
        ])
        mask = sweep.pareto_mask(df)
        # Rows 1 and 3 should be on the frontier; row 0 dominated by row 3,
        # row 2 dominated by row 0 (and 3). Allow either of {row 0, row 1, row 3}
        # to be on the frontier depending on tie-handling, but row 2 must not.
        assert mask.loc[3]
        assert not mask.loc[2]
