"""Behavioral regressions for B's integration review; synthetic inputs only."""

import importlib.util
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.context import ContextBudgetError, bound_agent_prompt, protect_context
from tradingagents.dataflows.config import run_config
from tradingagents.portfolio import PortfolioContext
from tradingagents.runapi.events import EventSink
from tradingagents.runapi.persist import PersistenceError, publish_run
from tradingagents.runapi.redact import Redactor


def test_concurrent_publish_collision_preserves_owner(tmp_path):
    staged, release = Event(), Event()

    class BlockingRedactor(Redactor):
        def scrub(self, value):
            staged.set()
            assert release.wait(10)
            return super().scrub(value)

    def publish(redactor):
        return publish_run(
            tmp_path, "AAPL", "shared", "report", None, {}, EventSink("shared", "AAPL"), redactor
        )

    with ThreadPoolExecutor() as pool:
        owner = pool.submit(publish, BlockingRedactor())
        assert staged.wait(10)
        try:
            with pytest.raises(PersistenceError):
                publish(Redactor())
            assert (tmp_path / "_staging" / "shared").is_dir()
        finally:
            release.set()
        assert owner.result().report_path.read_text() == "report"


def test_symlink_escape_preserves_outside(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_text("keep")
    root = tmp_path / "results"
    root.mkdir()
    (root / "_staging").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        publish_run(root, "AAPL", "run", "report", None, {}, EventSink("run", "AAPL"), Redactor())
    assert (outside / "sentinel").read_text() == "keep"


def test_redaction_reaches_real_events(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "event-canary-synthetic-98765")
    events = EventSink("run", "AAPL", Redactor())
    events.emit("engine", "diagnostic", "OPENAI_API_KEY=event-canary-synthetic-98765")
    assert events.write_to(tmp_path / "events.jsonl")
    text = (tmp_path / "events.jsonl").read_text()
    assert "event-canary-synthetic-98765" not in text and "[REDACTED]" in text


@pytest.mark.parametrize("retry", [True, False])
def test_picker_shows_file_error_and_retry_or_cancel(monkeypatch, retry):
    import cli.input_ui as ui
    from cli.input_ui import RunCancelled
    from tradingagents.runapi.result import InputError

    service = MagicMock()
    service.discover.return_value = [Path("bad.json")]
    service.read_file.side_effect = InputError("MALFORMED_JSON", "bad.json: invalid JSON")
    printed = []
    monkeypatch.setattr(ui.console, "print", lambda message: printed.append(str(message)))
    answers = iter(["1", "n"])
    monkeypatch.setattr(ui.typer, "prompt", lambda *a, **k: next(answers))
    monkeypatch.setattr(ui, "_confirm", lambda *a: retry)
    if retry:
        assert ui._choose_file(service, True) is None
    else:
        with pytest.raises(RunCancelled):
            ui._choose_file(service, True)
    assert any("bad.json: invalid JSON" in line for line in printed)
    assert not any("Choose one of the listed numbers" in line for line in printed)


def test_run_scoped_budget_preserves_middle_facts_and_resets():
    prompt = "opening" * 1000 + protect_context("EXPLICIT FLAT; CASH UNKNOWN") + "old debate" * 3000
    with run_config({"context_cap_tokens": 400, "compaction_threshold_tokens": 350}):
        bounded = bound_agent_prompt(prompt)
        assert len(bounded) <= 1600
        assert "EXPLICIT FLAT; CASH UNKNOWN" in bounded
    with run_config({"context_cap_tokens": 24000, "compaction_threshold_tokens": 19200}):
        assert bound_agent_prompt(prompt) == prompt
    with (
        run_config({"context_cap_tokens": 5, "compaction_threshold_tokens": 4}),
        pytest.raises(ContextBudgetError),
    ):
        bound_agent_prompt(prompt)


def test_analyst_guard_includes_rendered_system_template():
    from tradingagents.agents.analysts.turn import take_turn

    prompt = ChatPromptTemplate.from_messages(
        [("system", "instructions" * 1000), MessagesPlaceholder("messages")]
    )
    llm = MagicMock()
    with (
        run_config({"context_cap_tokens": 100, "compaction_threshold_tokens": 80}),
        pytest.raises(ContextBudgetError),
    ):
        take_turn(prompt, llm, [], [HumanMessage(content="hello")])
    llm.bind_tools.assert_called_once()  # binding is allowed, but no model invocation
    llm.bind_tools.return_value.invoke.assert_not_called()


@pytest.mark.parametrize(
    "book, marker",
    [
        (None, "Do not imply"),
        ({"positions": []}, "no nonzero target position"),
        ({"positions": [{"ticker": "MSFT", "quantity": 5}]}, "no nonzero target position"),
        ({"positions": [{"ticker": "AAPL", "quantity": 0}]}, "no nonzero target position"),
        ({"positions": [{"ticker": "AAPL", "quantity": 10}]}, "supplied signed quantities"),
        ({"positions": [{"ticker": "AAPL", "quantity": -10}]}, "supplied signed quantities"),
    ],
)
def test_trader_and_pm_receive_protected_ownership_facts(book, marker):
    from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
    from tradingagents.agents.trader.trader import create_trader

    portfolio = PortfolioContext.model_validate(book) if book is not None else None
    state = {
        "company_of_interest": "AAPL",
        "market_report": "",
        "investment_plan": "trim your existing position",
        "trader_investment_plan": "retain existing exposure",
        "portfolio_context": portfolio.render("AAPL") if portfolio else "",
        "risk_debate_state": dict.fromkeys(
            [
                "history",
                "aggressive_history",
                "conservative_history",
                "neutral_history",
                "current_aggressive_response",
                "current_conservative_response",
                "current_neutral_response",
            ],
            "debate" * 5000,
        ),
    }
    state["risk_debate_state"].update(count=1, latest_speaker="Neutral")
    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError
    llm.invoke.return_value = AIMessage(content="**Rating**: Hold")
    with run_config({"context_cap_tokens": 3000, "compaction_threshold_tokens": 2500}):
        create_trader(llm)(state)
        create_portfolio_manager(llm)(state)
    for call in llm.invoke.call_args_list:
        prompt = call.args[0]
        text = prompt if isinstance(prompt, str) else "\n".join(m["content"] for m in prompt)
        assert marker in text
        assert "<protected_context>" in text
        assert len(text) <= 12000


def _scoring_fixture(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "member_c_verification" / "live"
    monkeypatch.syspath_prepend(str(path))
    spec = importlib.util.spec_from_file_location(
        "review_exit_fixture", path / "test_score_gov004_exitcodes.py"
    )
    helper = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = helper
    spec.loader.exec_module(helper)
    root = tmp_path / "evidence"
    scorer = helper._fresh_scorer(root, monkeypatch)
    rows = []
    for case in helper.FIXED_CASES:
        marker = helper.CHALLENGE_MARKERS.get(case)
        for label in ("a", "b"):
            rows.append(
                helper._make_run(
                    root,
                    case,
                    f"{case}-{label}",
                    challenge_marker=marker,
                    challenge_reached=True if marker else None,
                )
            )
    helper._write_evidence(root, "1", rows)
    scores = root / "gov004_scores.json"
    helper._scores_all_pass(scores, [row["run_id"] for row in rows])
    return helper, scorer, root, scores, rows


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "duplicate",
        "unknown",
        "na",
        "boolean",
        "citation",
        "empty_manifest",
        "wrong_report",
        "hash",
        "critical",
        "late_cohort",
        "wrong_revision",
    ],
)
def test_invalid_scoring_cannot_pass(tmp_path, monkeypatch, defect):
    import json

    helper, scorer, root, scores, rows = _scoring_fixture(tmp_path, monkeypatch)
    assert scorer.main(["score", str(scores)]) == 0
    data = json.loads(scores.read_text())
    if defect == "missing":
        data["answers"].pop()
    if defect == "duplicate":
        data["answers"].append(data["answers"][0])
    if defect == "unknown":
        data["answers"][0]["case_id"] = "unrelated"
    if defect == "na":
        data["answers"][0]["score"] = None
    if defect == "boolean":
        data["answers"][0]["score"] = True
    if defect == "citation":
        data["answers"][0]["citation"] = "fabricated quote"
    if defect == "critical":
        data["answers"][0]["score"] = 0  # R1; caller cannot hide it with critical=False
    if defect in {"empty_manifest", "hash", "wrong_report", "wrong_revision"}:
        p = Path(rows[0]["manifest_path"])
        manifest = json.loads(p.read_text())
        if defect == "empty_manifest":
            manifest = {}
        if defect == "wrong_report":
            manifest["run_id"] = "unrelated"
        if defect == "wrong_revision":
            manifest["source_revision"] = "git:other"
        p.write_text(json.dumps(manifest) + " ")
    if defect == "late_cohort":
        p = root / "cohort.json"
        cohort = json.loads(p.read_text())
        cohort["frozen_at_utc"] = "2027-01-01T00:00:00Z"
        p.write_text(json.dumps(cohort))
    scores.write_text(json.dumps(data))
    assert scorer.main(["score", str(scores)]) == 1


def test_failed_retries_remain_in_overall_denominator(tmp_path, monkeypatch, capsys):
    helper, scorer, root, scores, rows = _scoring_fixture(tmp_path, monkeypatch)
    import json

    failures = [
        dict(row, run_id=row["run_id"] + "-retry", outcome="INCOMPLETE", output_check="NOT_RUN")
        for row in rows
    ]
    (root / "gov004_retries.json").write_text(json.dumps({"kind": "formal", "cases": failures}))
    assert scorer.main(["score", str(scores)]) == 1
    assert "Overall completion: 10/20" in capsys.readouterr().out


def test_evidence_package_is_portable(tmp_path, monkeypatch):
    import importlib
    import shutil

    helper, scorer, root, scores, rows = _scoring_fixture(tmp_path, monkeypatch)
    exporter = importlib.import_module("package_gov004")
    destination = tmp_path / "package"
    exporter.package(root, destination, scores)
    moved = tmp_path / "fresh-checkout-evidence"
    destination.rename(moved)
    shutil.rmtree(root)  # No original absolute paths may be needed.
    monkeypatch.setattr(scorer, "EVIDENCE_ROOT", moved)
    assert scorer.main(["score", str(moved / "gov004_scores.json")]) == 0
    assert (moved / "integrity.json").is_file()


def test_content_blocks_keep_their_original_shape():
    blocks = [{"type": "text", "text": "preserve these blocks"}]
    prompt = [{"role": "user", "content": blocks}]
    with run_config({"context_cap_tokens": 100, "compaction_threshold_tokens": 80}):
        assert bound_agent_prompt(prompt) == prompt
    with (
        run_config({"context_cap_tokens": 5, "compaction_threshold_tokens": 4}),
        pytest.raises(ContextBudgetError),
    ):
        bound_agent_prompt(prompt)


def test_cleanup_does_not_delete_a_replaced_staging_directory(tmp_path):
    class ReplacingRedactor(Redactor):
        def scrub(self, value):
            staging = tmp_path / "_staging" / "owned"
            staging.rename(tmp_path / "original-owned")
            staging.mkdir()
            (staging / "sentinel").write_text("belongs to another owner")
            raise RuntimeError("synthetic staging replacement")

    with pytest.raises(PersistenceError):
        publish_run(
            tmp_path,
            "AAPL",
            "owned",
            "report",
            None,
            {},
            EventSink("owned", "AAPL"),
            ReplacingRedactor(),
        )
    assert (tmp_path / "_staging" / "owned" / "sentinel").read_text() == "belongs to another owner"


def test_challenge_boolean_without_input_capture_cannot_pass(tmp_path, monkeypatch):
    import json

    helper, scorer, root, scores, rows = _scoring_fixture(tmp_path, monkeypatch)
    assert scorer.main(["score", str(scores)]) == 0
    path = root / "gov004_T1.json"
    data = json.loads(path.read_text())
    for row in data["cases"]:
        if row["challenge_marker"]:
            row["prompt_capture"]["calls"][0]["marker_hits"] = {}
    path.write_text(json.dumps(data))
    assert scorer.main(["score", str(scores)]) == 1
