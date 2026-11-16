"""SEL-TA-NFR-004 — Distinct immutable fresh-run artifacts.

Fit: two same-ticker/date runs produce two isolated directories and the first
artifact bytes stay unchanged; the manifest records input provenance/result and
never the portfolio payload.

Enforcing design: runapi/persist.publish_run single-commit (INV-12/INV-14).
"""

from __future__ import annotations

import json

import pytest
from conftest import GOOD_STATE, make_engine

from tradingagents.portfolio import PortfolioContext
from tradingagents.runapi.execution import run_analysis_api
from tradingagents.runapi.input_service import freeze_explicit

pytestmark = pytest.mark.unit

DATE = "2026-11-12"


def _run(tmp_path, portfolio=None):
    factory, runner = make_engine(GOOD_STATE)
    ctx = freeze_explicit("AAPL", DATE, portfolio).confirm()
    return run_analysis_api(ctx, config={"results_dir": str(tmp_path), "selected_analysts": ["market"]},
                            selected_analysts=["market"], graph_factory=factory, engine_runner=runner)


# TC-NFR004-a: two same-ticker/date runs get isolated dirs; first bytes unchanged.
def test_tc_nfr004_a_two_runs_isolated(tmp_path):
    first = _run(tmp_path)
    first_bytes = (tmp_path / "AAPL" / first.run_id / "manifest.json").read_bytes()

    second = _run(tmp_path)

    assert first.run_id != second.run_id
    assert first.manifest_path != second.manifest_path
    assert (tmp_path / "AAPL" / first.run_id / "manifest.json").read_bytes() == first_bytes


# TC-NFR004-b: manifest never contains the portfolio payload (holdings/cash list).
def test_tc_nfr004_b_manifest_omits_payload(tmp_path):
    portfolio = PortfolioContext.model_validate({
        "cash": 424242.0, "positions": [{"ticker": "AAPL", "quantity": 77, "average_price": 123.45}]})
    result = _run(tmp_path, portfolio)

    manifest_text = (tmp_path / "AAPL" / result.run_id / "manifest.json").read_text()

    assert "424242" not in manifest_text
    assert "123.45" not in manifest_text
    data = json.loads(manifest_text)
    for forbidden in ("positions", "cash", "portfolio_context"):
        assert forbidden not in data
    assert data["fingerprint_sha256"] and len(data["fingerprint_sha256"]) == 64


# TC-NFR004-c: incomplete runs carry no rating and no stop_reason field for completed.
def test_tc_nfr004_c_conditional_manifest_fields(tmp_path):
    result = _run(tmp_path)
    data = json.loads((tmp_path / "AAPL" / result.run_id / "manifest.json").read_text())
    assert data["run_outcome"] == "COMPLETED"
    assert data["stop_reason"] is None
    assert data["final_rating"] == "Hold"
