"""SEL-TA-NFR-004 — Distinct immutable fresh-run artifacts.

Fit: two same-ticker/date runs produce two isolated directories and the first
artifact bytes stay unchanged; the manifest records input provenance/result and
never the portfolio payload; a config-only change alters exactly one manifest
key; a prompt-template change alters the prompt hash; a published INCOMPLETE
manifest carries no final rating; and the R13a/R13b/R14 persistence-failure
contracts hold (critical failure => INCOMPLETE/PERSISTENCE_ERROR/NOT_RUN with
nothing published; best-effort failure keeps the outcome; terminal-event write
failure records terminal_event.durable=false).

Enforcing design: runapi/persist.publish_run single-commit (INV-12/INV-14),
runapi/execution.run_analysis_api, runapi/events.EventSink.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import GOOD_STATE, make_engine

from tradingagents.portfolio import PortfolioContext
from tradingagents.runapi.execution import run_analysis_api
from tradingagents.runapi.input_service import freeze_explicit

pytestmark = pytest.mark.unit

DATE = "2026-11-12"


def _run(tmp_path, portfolio=None, *, config=None, raises=None):
    factory, runner = make_engine(GOOD_STATE, raises=raises)
    ctx = freeze_explicit("AAPL", DATE, portfolio).confirm()
    base = {"results_dir": str(tmp_path), "selected_analysts": ["market"]}
    if config:
        base.update(config)
    return run_analysis_api(ctx, config=base, selected_analysts=["market"],
                            graph_factory=factory, engine_runner=runner)


def _manifest(tmp_path, result):
    return json.loads((tmp_path / "AAPL" / result.run_id / "manifest.json").read_text())


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


# TC-NFR004-c: completed runs carry a rating and no stop_reason.
def test_tc_nfr004_c_conditional_manifest_fields_completed(tmp_path):
    result = _run(tmp_path)
    data = _manifest(tmp_path, result)
    assert data["run_outcome"] == "COMPLETED"
    assert data["stop_reason"] is None
    assert data["final_rating"] == "Hold"


# TC-NFR004-d: changing one config value alters exactly that key in effective_config.
def test_tc_nfr004_d_config_only_change_differs_in_one_key(tmp_path):
    baseline = _manifest(tmp_path, _run(tmp_path))
    changed = _manifest(tmp_path, _run(tmp_path, config={"max_debate_rounds": 3}))

    base_cfg = baseline["effective_config"]
    changed_cfg = changed["effective_config"]
    assert base_cfg["max_debate_rounds"] != changed_cfg["max_debate_rounds"]
    diff = {key for key in set(base_cfg) | set(changed_cfg)
            if base_cfg.get(key) != changed_cfg.get(key)}
    assert diff == {"max_debate_rounds"}, diff
    # IDs/timing/results are excluded from the config comparison by construction.
    assert baseline["run_id"] != changed["run_id"]


# TC-NFR004-e: a prompt-template change alters the recorded prompt hash.
def test_tc_nfr004_e_prompt_template_change_changes_hash(tmp_path, monkeypatch):
    baseline = _manifest(tmp_path, _run(tmp_path))

    import pathlib

    original_read_text = pathlib.Path.read_text

    def tampered_read_text(self, *args, **kwargs):
        text = original_read_text(self, *args, **kwargs)
        # Simulate editing one prompt-bearing template file.
        if self.name == "portfolio_manager.py":
            return text + "\n# simulated prompt edit\n"
        return text

    monkeypatch.setattr(pathlib.Path, "read_text", tampered_read_text)
    edited = _manifest(tmp_path, _run(tmp_path))

    assert baseline["prompt_hash"] != edited["prompt_hash"]
    # Only the hash changes; the effective config is untouched by a template edit.
    assert baseline["effective_config"] == edited["effective_config"]


# TC-NFR004-f: a published INCOMPLETE manifest has no final rating.
def test_tc_nfr004_f_published_incomplete_manifest_has_no_rating(tmp_path):
    result = _run(tmp_path, raises=RuntimeError("engine failed"))

    assert result.run_outcome == "INCOMPLETE"
    assert result.final_rating is None
    assert result.stop_reason is not None
    assert result.output_check == "NOT_RUN"

    data = _manifest(tmp_path, result)
    assert data["run_outcome"] == "INCOMPLETE"
    assert data["final_rating"] is None
    assert data["stop_reason"] is not None
    assert data["output_check"] == "NOT_RUN"


# TC-NFR004-g: R13a (critical staging/commit failure) -> INCOMPLETE/
# PERSISTENCE_ERROR/NOT_RUN, nothing published, no rating.
def test_tc_nfr004_g_r13a_critical_publish_failure_publishes_nothing(tmp_path, monkeypatch):
    from tradingagents.runapi import persist

    def failing_rename(*_args, **_kwargs):
        raise OSError("simulated disk full at commit")

    # R13a: the single commit (directory rename) fails before publication.
    monkeypatch.setattr(persist.os, "rename", failing_rename)
    result = _run(tmp_path)

    assert result.run_outcome == "INCOMPLETE"
    assert result.stop_reason == "PERSISTENCE_ERROR"
    assert result.output_check == "NOT_RUN"
    assert result.final_rating is None
    assert result.manifest_path is None
    assert result.report_path is None

    # No published run directory, and the staging area is not treated as published.
    assert not (tmp_path / "AAPL" / result.run_id).exists()
    assert not (tmp_path / "_staging" / result.run_id).exists()


# TC-NFR004-h: R13b (best-effort sink failure) keeps the run outcome.
def test_tc_nfr004_h_r13b_best_effort_failure_preserves_outcome(tmp_path, monkeypatch):
    import pathlib

    original_write_text = pathlib.Path.write_text

    def flaky_write_text(self, *args, **kwargs):
        # Fail only the best-effort state sink; report/manifest still publish.
        if self.name == "state.json":
            raise OSError("simulated best-effort state write failure")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "write_text", flaky_write_text)
    result = _run(tmp_path)

    # Outcome unchanged: still a completed publish with its rating.
    assert result.run_outcome == "COMPLETED"
    assert result.stop_reason is None
    assert result.final_rating == "Hold"
    data = _manifest(tmp_path, result)
    assert data["run_outcome"] == "COMPLETED"
    assert data["final_rating"] == "Hold"

    # The best-effort failure is recorded in the events, not fatal.
    events = (tmp_path / "AAPL" / result.run_id / "events.jsonl").read_text()
    assert "BEST_EFFORT_FAILED:state.json" in events


# TC-NFR004-i: R14 (terminal-event write failure) publishes, keeps the outcome,
# and records terminal_event.durable=false.
def test_tc_nfr004_i_r14_terminal_event_failure_marks_non_durable(tmp_path, monkeypatch):
    from tradingagents.runapi import events as events_module

    original_replace = events_module.os.replace

    def flaky_replace(src, dst, *args, **kwargs):
        # Fail only the events.jsonl temp->final replace (terminal-event append).
        if Path(dst).name == "events.jsonl":
            raise OSError("simulated terminal-event append failure")
        return original_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(events_module.os, "replace", flaky_replace)
    result = _run(tmp_path)

    # The run still publishes with its logical outcome (not PERSISTENCE_ERROR).
    assert result.run_outcome == "COMPLETED"
    assert result.final_rating == "Hold"
    data = _manifest(tmp_path, result)
    assert data["run_outcome"] == "COMPLETED"
    # Non-durable terminal event is stated in the manifest.
    assert data["terminal_event"]["logical"] == "run.terminal"
    assert data["terminal_event"]["durable"] is False
    # A completed run is still a real, published artifact.
    assert (tmp_path / "AAPL" / result.run_id / "reports" / "complete_report.md").exists()
