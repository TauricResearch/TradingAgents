"""SEL-TA-NFR-003 — Credential and holdings privacy.

Fit: four planted secret types across sinks/error paths yield zero values; an
unrelated-holding marker does not appear in report/manifest; source files are
unchanged after a run.

Enforcing design: runapi/redact.Redactor at every sink (INV-06).
"""

from __future__ import annotations

import pytest

from tradingagents.runapi.redact import Redactor

pytestmark = pytest.mark.unit

SECRETS = {
    "bearer": "Authorization: Bearer abcDEF1234567890xyz",
    "openai": "api_key=sk-ABCDEFGHIJKLMNOP12345",
    "github": "token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
    "google": "ya29.a0AfH6SMBabcdefghijklmnopqrstuvwxyz",
}


# TC-NFR003-a: each of the four planted secret types is scrubbed from text.
@pytest.mark.parametrize("name", list(SECRETS))
def test_tc_nfr003_a_each_secret_type_scrubbed(name):
    scrubbed = Redactor().scrub(SECRETS[name])
    assert "[REDACTED]" in scrubbed
    for token in ("abcDEF1234567890xyz", "sk-ABCDEFGHIJKLMNOP12345",
                  "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
                  "a0AfH6SMBabcdefghijklmnopqrstuvwxyz"):
        assert token not in scrubbed


# TC-NFR003-b: secret-keyed mapping values are redacted by key name.
def test_tc_nfr003_b_mapping_values_redacted():
    safe = Redactor().scrub({"api_key": "sensitive", "access_token": "t0ken!"})
    assert safe == {"api_key": "[REDACTED]", "access_token": "[REDACTED]"}


# TC-NFR003-c: a redacted diagnostic keeps the exception type but hides the secret.
def test_tc_nfr003_c_diagnostic_redacts():
    diag = Redactor().diagnostic(RuntimeError("failed with Bearer sk-abcdefghijklmnop1234"))
    assert "RuntimeError" in diag
    assert "sk-abcdefghijklmnop1234" not in diag


# TC-NFR003-d: a model error raised through the shared API must not leak planted
# secrets or an unrelated holding into result, report, manifest, events or the
# diagnostic; the source portfolio file is unchanged.
def test_tc_nfr003_d_model_error_paths_do_not_leak(tmp_path):
    import json

    from conftest import make_engine

    from tradingagents.portfolio import PortfolioContext
    from tradingagents.runapi.execution import run_analysis_api
    from tradingagents.runapi.input_service import freeze_explicit

    planted = [
        "Bearer abcDEF1234567890xyz",
        "api_key=sk-ABCDEFGHIJKLMNOP12345",
        "token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
        "ya29.a0AfH6SMBabcdefghijklmnopqrstuvwxyz",
    ]
    unrelated = "UNRELATED_HOLDING_MARKER"

    source = tmp_path / "book.json"
    source.write_text(json.dumps({
        "cash": 1000.0,
        "positions": [{"ticker": "AAPL", "quantity": 10}, {"ticker": unrelated, "quantity": 3}],
    }, indent=2), encoding="utf-8")
    before = source.read_bytes()

    portfolio = PortfolioContext.model_validate(json.loads(source.read_text()))
    ctx = freeze_explicit("AAPL", "2026-11-12", portfolio).confirm()

    secret_message = ("provider exhausted; " + "; ".join(planted))
    factory, runner = make_engine({}, raises=TimeoutError(secret_message))
    result = run_analysis_api(
        ctx, config={"results_dir": str(tmp_path), "selected_analysts": ["market"]},
        selected_analysts=["market"], graph_factory=factory, engine_runner=runner,
    )

    run_dir = tmp_path / "AAPL" / result.run_id
    report = (run_dir / "reports" / "complete_report.md").read_text()
    manifest_text = (run_dir / "manifest.json").read_text()
    events_text = (run_dir / "events.jsonl").read_text()
    surfaces = {
        "result": json.dumps(result.as_dict()),
        "report": report,
        "manifest": manifest_text,
        "events": events_text,
    }

    for name, text in surfaces.items():
        for token in ("abcDEF1234567890xyz", "sk-ABCDEFGHIJKLMNOP12345",
                      "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
                      "a0AfH6SMBabcdefghijklmnopqrstuvwxyz"):
            assert token not in text, f"secret leaked into {name}"
        assert unrelated not in text, f"unrelated holding leaked into {name}"

    # The run stopped as a typed model failure, not an escape.
    assert result.run_outcome == "INCOMPLETE"
    assert result.stop_reason == "MODEL_FAILURE"

    # Non-vacuous: the diagnostic text reached the report but was scrubbed.
    assert "Analysis stopped:" in report
    assert "TimeoutError" in report
    assert "[REDACTED]" in report

    # Source portfolio bytes are unchanged.
    assert source.read_bytes() == before


# TC-NFR003-e: a pre-run portfolio input error shown by the CLI must not echo the
# planted secret or an unrelated holding; the source file is unchanged.
def test_tc_nfr003_e_cli_input_error_does_not_leak(tmp_path):
    import json

    from typer.testing import CliRunner

    import cli.main as m

    planted_secret = "sk-ABCDEFGHIJKLMNOP12345"
    unrelated = "UNRELATED_HOLDING_MARKER"
    # Valid JSON that fails the shape contract (missing quantity) but embeds
    # markers that must never be echoed back to the user.
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({
        "api_key": planted_secret,
        "positions": [{"ticker": "AAPL"}, {"ticker": unrelated, "quantity": 1}],
    }), encoding="utf-8")
    before = bad.read_bytes()

    result = CliRunner().invoke(m.app, ["--portfolio", str(bad), "--portfolio-as-of", "2026-11-12"])

    assert result.exit_code == 1
    assert planted_secret not in result.output
    assert unrelated not in result.output
    assert bad.read_bytes() == before


# TC-NFR003-f: an unrecovered *vendor* (data) exception raised inside the graph
# after the run starts must not leak a planted credential into any output of the
# incomplete path; the vendor stub is confirmed reached; source file unchanged.
def test_tc_nfr003_f_vendor_error_path_does_not_leak(tmp_path):
    import json

    from conftest import make_engine

    from tradingagents.dataflows.errors import NoMarketDataError
    from tradingagents.portfolio import PortfolioContext
    from tradingagents.runapi.execution import run_analysis_api
    from tradingagents.runapi.input_service import freeze_explicit

    fake_credential = "sk-VENDORLEAK0123456789abcdef"
    unrelated = "UNRELATED_HOLDING_MARKER"

    source = tmp_path / "book.json"
    source.write_text(json.dumps({
        "cash": 1000.0,
        "positions": [{"ticker": "AAPL", "quantity": 10}, {"ticker": unrelated, "quantity": 3}],
    }, indent=2), encoding="utf-8")
    before = source.read_bytes()

    portfolio = PortfolioContext.model_validate(json.loads(source.read_text()))
    ctx = freeze_explicit("AAPL", "2026-11-12", portfolio).confirm()

    reached = []
    vendor_error = NoMarketDataError(
        "AAPL", detail=f"vendor rejected request with token {fake_credential}"
    )

    def runner(_graph, _context):
        reached.append(True)  # the vendor stub (inside the graph) was reached
        raise vendor_error

    factory, _unused = make_engine({})
    result = run_analysis_api(
        ctx, config={"results_dir": str(tmp_path), "selected_analysts": ["market"]},
        selected_analysts=["market"], graph_factory=factory, engine_runner=runner,
    )

    # The vendor stub ran after the run started.
    assert reached == [True]

    # Typed data failure, no finished rating, check not run.
    assert result.run_outcome == "INCOMPLETE"
    assert result.stop_reason == "DATA_FAILURE"
    assert result.output_check == "NOT_RUN"
    assert result.final_rating is None

    # Every output produced on this path exists and is leak-free.
    run_dir = tmp_path / "AAPL" / result.run_id
    report_path = run_dir / "reports" / "complete_report.md"
    html_path = run_dir / "reports" / "complete_report.html"
    manifest_path = run_dir / "manifest.json"
    events_path = run_dir / "events.jsonl"
    assert report_path.exists()
    assert html_path.exists()
    assert manifest_path.exists()
    assert events_path.exists()

    surfaces = {
        "result": json.dumps(result.as_dict()),
        "report": report_path.read_text(),
        "report_html": html_path.read_text(),
        "manifest": manifest_path.read_text(),
        "events": events_path.read_text(),
    }
    for name, text in surfaces.items():
        assert fake_credential not in text, f"credential leaked into {name}"
        assert unrelated not in text, f"unrelated holding leaked into {name}"

    # Non-vacuous: the redacted vendor diagnostic reached the report; the typed
    # stop reason is recorded in the manifest and the report envelope (events
    # carry the progress outcome, not the stop reason).
    assert "Analysis stopped:" in surfaces["report"]
    assert "NoMarketDataError" in surfaces["report"]
    assert "[REDACTED]" in surfaces["report"]
    assert json.loads(surfaces["manifest"])["stop_reason"] == "DATA_FAILURE"
    assert "- Stop reason: DATA_FAILURE" in surfaces["report"]

    # Source portfolio bytes are unchanged.
    assert source.read_bytes() == before


# TC-NFR003-g: a fake credential planted in a *successfully published* model
# narrative is redacted from both the Markdown and HTML reports, while the benign
# sentence beside it survives. The run completes normally.
def test_tc_nfr003_g_published_narrative_redacts_credential(tmp_path):
    from conftest import GOOD_STATE, confirmed_context, make_engine

    from tradingagents.runapi.execution import run_analysis_api

    fake_credential = "sk-NARRATIVELEAK0123456789ab"
    benign = "The thesis remains constructive on steady demand."
    state = {
        **GOOD_STATE,
        "final_trade_decision": f"Rating: Hold\n\n{benign} Also note {fake_credential} for later.",
    }

    factory, runner = make_engine(state)
    result = run_analysis_api(
        confirmed_context(), config={"results_dir": str(tmp_path), "selected_analysts": ["market"]},
        selected_analysts=["market"], graph_factory=factory, engine_runner=runner, html=True,
    )

    assert result.run_outcome == "COMPLETED"

    run_dir = tmp_path / "AAPL" / result.run_id
    markdown = (run_dir / "reports" / "complete_report.md").read_text()
    html = (run_dir / "reports" / "complete_report.html").read_text()

    for name, text in (("markdown", markdown), ("html", html)):
        assert benign in text, f"benign sentence missing from {name} report"
        assert fake_credential not in text, f"credential leaked into {name} report"
        assert "[REDACTED]" in text, f"no redaction marker in {name} report"
