"""SEL-TA-FR-006 — Deterministic input provenance.

Fit: canonical fingerprint is SHA-256 over canonical JSON bytes; changing model
prose leaves provenance identical; selecting b yields b's fingerprint and never
a's; None and explicit-empty portfolios produce distinct modes/fingerprints.

Enforcing design: runapi/context.py (INV-04/INV-05) + reporting projection.
"""

from __future__ import annotations

import json

import pytest

from tradingagents.portfolio import PortfolioContext
from tradingagents.runapi.context import snapshot_fingerprint
from tradingagents.runapi.input_service import PortfolioInputService, freeze_explicit

pytestmark = pytest.mark.unit

DATE = "2026-11-12"
# interface-contracts.md §2.2.1 Reason E, verified canonical-bytes example.
REASON_E = (
    "45f07d9eb3359b059525da0cee26f8a9810269dad11ffb4c42e1dcc7072cef72"
)


# TC-FR006-a: fingerprint matches the documented canonical-bytes example.
def test_tc_fr006_a_documented_fingerprint_example():
    book = PortfolioContext.model_validate({
        "cash": 2500.0, "currency": "USD",
        "positions": [{"ticker": "AAPL", "quantity": 10, "average_price": 150.5},
                      {"ticker": "MSFT", "quantity": 5, "average_price": None}],
    })
    digest, _ = snapshot_fingerprint(book)
    assert digest == REASON_E
    assert len(digest) == 64


# TC-FR006-b: reordered input, 1 vs 1.0 and missing-vs-null price give equal digests.
def test_tc_fr006_b_canonicalization_is_order_and_number_stable():
    forward = PortfolioContext.model_validate({
        "cash": 1, "positions": [{"ticker": "MSFT", "quantity": 1, "average_price": 50}]})
    reverse = PortfolioContext.model_validate({
        "cash": 1.0, "positions": [{"ticker": "MSFT", "quantity": 1.0, "average_price": 50.0}]})
    assert snapshot_fingerprint(forward)[0] == snapshot_fingerprint(reverse)[0]

    null_price = PortfolioContext.model_validate({"positions": [{"ticker": "AAPL", "quantity": 10}]})
    explicit_null = PortfolioContext.model_validate(
        {"positions": [{"ticker": "AAPL", "quantity": 10, "average_price": None}]})
    assert snapshot_fingerprint(null_price)[0] == snapshot_fingerprint(explicit_null)[0]


# TC-FR006-c: no-portfolio vs explicit-empty produce distinct mode and fingerprint.
def test_tc_fr006_c_none_and_empty_are_distinct():
    none_ctx = freeze_explicit("AAPL", DATE, None)
    empty_ctx = freeze_explicit("AAPL", DATE, PortfolioContext.model_validate({"positions": []}))

    assert none_ctx.mode.value == "NO_PORTFOLIO"
    assert none_ctx.snapshot is None
    assert none_ctx.safe_input_metadata()["fingerprint_sha256"] is None

    assert empty_ctx.mode.value == "PORTFOLIO_PROVIDED"
    assert empty_ctx.snapshot is not None
    assert len(empty_ctx.safe_input_metadata()["fingerprint_sha256"]) == 64


# TC-FR006-d: selecting b records b's fingerprint, never a's.
def test_tc_fr006_d_selecting_b_uses_b_fingerprint(tmp_path):
    (tmp_path / "a.json").write_text('{"positions": [{"ticker": "AAA", "quantity": 1}]}')
    (tmp_path / "b.json").write_text('{"positions": [{"ticker": "BBB", "quantity": 2}]}')
    service = PortfolioInputService(tmp_path)

    a_ctx = service.freeze_path("AAPL", DATE, tmp_path / "a.json", portfolio_as_of=DATE)
    b_ctx = service.freeze_path("AAPL", DATE, tmp_path / "b.json", portfolio_as_of=DATE)

    assert b_ctx.snapshot.basename == "b.json"
    assert b_ctx.snapshot.fingerprint_sha256 != a_ctx.snapshot.fingerprint_sha256


# TC-FR006-e: two runs over identical portfolio contents/date but different
# scripted model text publish both texts, while input provenance is identical
# once run IDs and timestamps are excluded.
def test_tc_fr006_e_prose_change_leaves_provenance_identical(tmp_path):
    from conftest import make_engine

    from tradingagents.runapi.execution import run_analysis_api

    portfolio = PortfolioContext.model_validate({
        "cash": 2500.0, "currency": "USD",
        "positions": [{"ticker": "AAPL", "quantity": 10, "average_price": 150.5}],
    })
    text_a = "Prose Alpha: hold and reassess next quarter."
    text_b = "Prose Beta: trim into strength but keep a core position."

    def run(text):
        state = {
            "market_report": "MKT",
            "final_trade_decision": f"Rating: Hold\n\n{text}",
            "final_rating": "Hold",
        }
        factory, runner = make_engine(state)
        ctx = freeze_explicit("AAPL", DATE, portfolio).confirm()
        return run_analysis_api(
            ctx, config={"results_dir": str(tmp_path), "selected_analysts": ["market"]},
            selected_analysts=["market"], graph_factory=factory, engine_runner=runner,
        )

    first = run(text_a)
    second = run(text_b)

    # Fresh run ID each, both COMPLETED.
    assert first.run_id != second.run_id
    assert first.run_outcome == second.run_outcome == "COMPLETED"

    def read(result):
        report = (tmp_path / "AAPL" / result.run_id / "reports" / "complete_report.md").read_text()
        manifest = json.loads((tmp_path / "AAPL" / result.run_id / "manifest.json").read_text())
        return report, manifest

    report_a, manifest_a = read(first)
    report_b, manifest_b = read(second)

    # Both different model texts appear in the published reports.
    assert text_a in report_a and text_b not in report_a
    assert text_b in report_b and text_a not in report_b

    # Input provenance fields agree once run ID/timestamps are excluded.
    provenance_keys = ("ticker", "analysis_date", "input_mode", "basename",
                       "fingerprint_sha256", "portfolio_as_of", "as_of_basis")
    for key in provenance_keys:
        assert manifest_a[key] == manifest_b[key], key

    # The provenance fragment in each report (minus the Run ID line) matches.
    def provenance_lines(report):
        return [line for line in report.splitlines()
                if line.startswith("- ") and not line.startswith("- Run ID:")]

    assert provenance_lines(report_a) == provenance_lines(report_b)
