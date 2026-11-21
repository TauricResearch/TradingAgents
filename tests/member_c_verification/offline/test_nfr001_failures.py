"""SEL-TA-NFR-001 — Reliable external-failure handling.

Fit: typed incomplete results rather than escaping exceptions; a workflow
returning unreadable final text completes with REVIEW + NEEDS_REVIEW; raised
data/internal errors map to their stop_reason; a recoverable optional-data
sentinel is not reclassified as fatal.

Enforcing design: runapi/finalize.classify_exception + run_analysis_api (INV-07).
Uses the shared boundary with an injected scripted engine, no network.
"""

from __future__ import annotations

import pytest
from conftest import GOOD_STATE, confirmed_context, make_engine

from tradingagents.runapi.execution import run_analysis_api
from tradingagents.runapi.finalize import classify_exception

pytestmark = pytest.mark.unit

DATE = "2026-11-12"


def _run(tmp_path, state=None, *, raises=None):
    factory, runner = make_engine(state or {}, raises=raises)
    return run_analysis_api(
        confirmed_context(), config={"results_dir": str(tmp_path), "selected_analysts": ["market"]},
        selected_analysts=["market"], graph_factory=factory, engine_runner=runner,
    )


# TC-NFR001-a: unreadable final text still completes, as REVIEW + NEEDS_REVIEW.
def test_tc_nfr001_a_unreadable_final_text_is_review(tmp_path):
    state = {**GOOD_STATE, "final_trade_decision": "no decision here", "final_rating": None}
    result = _run(tmp_path, state)
    assert result.run_outcome == "COMPLETED"
    assert result.final_rating == "REVIEW"
    assert result.output_check == "NEEDS_REVIEW"


# TC-NFR001-b: an ordinary internal exception returns INTERNAL_ERROR, not an escape.
def test_tc_nfr001_b_internal_exception_is_typed(tmp_path):
    result = _run(tmp_path, raises=RuntimeError("boom"))
    assert result.run_outcome == "INCOMPLETE"
    assert result.stop_reason == "INTERNAL_ERROR"
    assert result.output_check == "NOT_RUN"
    assert result.final_rating is None


# TC-NFR001-c: an unrecovered vendor/data exception maps to DATA_FAILURE.
def test_tc_nfr001_c_vendor_exception_is_data_failure():
    from tradingagents.dataflows.errors import NoMarketDataError

    assert classify_exception(NoMarketDataError("no data")) == "DATA_FAILURE"


# TC-NFR001-d: exhausted model/provider errors map to MODEL_FAILURE.
# A provider-library exception (module-based) and a timeout (name-based) both
# classify as MODEL_FAILURE; a bare ConnectionError is genuinely INTERNAL_ERROR.
class ProviderResponseError(Exception):
    pass


ProviderResponseError.__module__ = "openai._base_client"


@pytest.mark.parametrize("exc", [TimeoutError("t"), ProviderResponseError("exhausted")])
def test_tc_nfr001_d_model_failures(exc):
    assert classify_exception(exc) == "MODEL_FAILURE"


def test_tc_nfr001_d2_bare_connection_error_is_internal():
    assert classify_exception(ConnectionError("c")) == "INTERNAL_ERROR"


# TC-NFR001-e: no exception escapes the public entry for a raised engine error.
def test_tc_nfr001_e_no_exception_escapes(tmp_path):
    try:
        result = _run(tmp_path, raises=ValueError("unexpected"))
    except Exception as exc:  # noqa: BLE001 - the point of the test
        pytest.fail(f"run_analysis_api leaked {type(exc).__name__}: {exc}")
    assert result.run_outcome == "INCOMPLETE"
