"""SEL-TA-FR-002 — Explicit mode confirmation / consent gate.

Fit: only Yes starts one graph; No/EOF starts zero; noninteractive neither/both
flags or --portfolio without --portfolio-as-of give a readable input error and
zero graph/LLM calls; a valid --without-portfolio starts once with None.

Enforcing design: runapi/execution.run_analysis_api rejects non-CONFIRMED
(INV-09); the flag rules live at the CLI boundary and are checked structurally
here against the committed CLI contract.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

import cli.main as m
from tradingagents.runapi.context import ConsentState
from tradingagents.runapi.input_service import freeze_explicit

pytestmark = pytest.mark.unit

DATE = "2026-11-12"


# TC-FR002-a: an unconﬁrmed (FROZEN) context is rejected by the run entry.
def test_tc_fr002_a_frozen_context_cannot_run():
    from tradingagents.runapi.execution import run_analysis_api

    frozen = freeze_explicit("AAPL", DATE, None)
    assert frozen.consent_state == ConsentState.FROZEN
    with pytest.raises(ValueError, match="confirmed"):
        run_analysis_api(frozen)


# TC-FR002-b: a confirmed no-portfolio context runs (graph invoked exactly once).
def test_tc_fr002_b_confirmed_context_runs_once(tmp_path, monkeypatch):
    from conftest import GOOD_STATE, confirmed_context, make_engine

    factory, runner = make_engine(GOOD_STATE)
    from tradingagents.runapi.execution import run_analysis_api

    result = run_analysis_api(
        confirmed_context(), config={"results_dir": str(tmp_path)},
        graph_factory=factory, engine_runner=runner,
    )
    assert result.run_outcome == "COMPLETED"
    assert result.input_mode == "NO_PORTFOLIO"


# TC-FR002-c: the mode/as-of guards in resolve_run_context reject conflicting or
# unattended-incomplete input with a typed error (zero graph, zero LLM calls).
# Boundary adjusted from the CLI wiring to the guard that actually enforces
# contract §4 (see plan change log).
def test_tc_fr002_c_flag_conflicts_raise_typed_error(tmp_path):
    from cli.input_ui import resolve_run_context
    from tradingagents.runapi.result import InputError

    good = tmp_path / "good.json"
    good.write_text('{"positions": []}')

    with pytest.raises(InputError) as both:
        resolve_run_context("AAPL", DATE, portfolio_path=str(good), without_portfolio=True,
                            interactive=False)
    assert both.value.kind == "FLAG_CONFLICT"

    with pytest.raises(InputError) as no_asof:
        resolve_run_context("AAPL", DATE, portfolio_path=str(good), interactive=False)
    assert no_asof.value.kind == "AS_OF_MISMATCH"


# TC-FR002-d: a valid --without-portfolio starts exactly one run with None.
def test_tc_fr002_d_without_portfolio_runs_with_none(tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(m, "run_analysis", lambda **k: captured.append(k))
    runner = CliRunner()

    result = runner.invoke(m.app, ["--without-portfolio"])

    assert result.exit_code == 0
    assert captured and captured[0]["portfolio"] is None
