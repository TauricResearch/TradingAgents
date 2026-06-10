import json
import tomllib
from pathlib import Path

import pytest
import typer

from cli import main as cli_main
from cli.main import (
    INDIA_COMPLIANCE_DISCLAIMER,
    build_first_analysis_command,
    generate_sample_report,
    get_first_workflow_status,
    get_provider_setup_status,
    get_report_status,
    get_use_case_guidance,
    initialize_env_file,
    run_doctor_checks,
    run_first_run_checks,
    save_report_to_disk,
)
from tradingagents.dataflows.india.symbols import IndiaSymbolError


@pytest.mark.unit
def test_doctor_validates_india_ticker(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for env_var in (
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "OLLAMA_BASE_URL",
    ):
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setattr(cli_main.shutil, "which", lambda command: None)

    checks = run_doctor_checks("RELIANCE")

    assert checks["ticker_validation"] == "RELIANCE.NS"
    assert checks["package_import"] is True
    assert checks["provider_ready"] is False
    assert checks["preferred_provider"] == "none"
    assert checks["saved_report_bundle_ready"] is False
    assert checks["first_workflow_ready"] is False
    assert (
        "sample-report --ticker RELIANCE.NS --date 2026-06-05"
        in checks["first_workflow_next_step"]
    )


@pytest.mark.unit
def test_doctor_surfaces_ready_workflow_next_step(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr(cli_main.shutil, "which", lambda command: None)
    report_dir = tmp_path / "reports" / "RELIANCE.NS" / "2026-06-05"
    generate_sample_report(
        ticker="RELIANCE",
        analysis_date="2026-06-05",
        save_path=report_dir,
    )

    checks = run_doctor_checks("RELIANCE")

    assert checks["provider_ready"] is True
    assert checks["preferred_provider"] == "ollama"
    assert checks["saved_report_bundle_ready"] is True
    assert checks["first_workflow_ready"] is True
    assert checks["first_workflow_next_step"] == (
        "indiamarketagents analyze --ticker RELIANCE.NS --date 2026-06-05 "
        "--provider ollama --research-depth 1 --no-display --no-save-prompt"
    )


@pytest.mark.unit
def test_first_run_check_reports_missing_llm_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = run_first_run_checks(
        ticker="RELIANCE",
        analysis_date="2026-06-05",
        provider="openai",
        analysts="india_market",
    )

    assert result["ready"] is False
    assert result["ticker"] == "RELIANCE.NS"
    failures = {
        check["name"]: check
        for check in result["checks"]
        if check["status"] == "fail"
    }
    assert "LLM credentials" in failures
    assert "OPENAI_API_KEY is not set" in failures["LLM credentials"]["detail"]


@pytest.mark.unit
def test_first_run_check_reports_missing_provider_readiness(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for env_var in (
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "OLLAMA_BASE_URL",
    ):
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setattr(cli_main.shutil, "which", lambda command: None)

    result = run_first_run_checks(
        ticker="RELIANCE",
        analysis_date="2026-06-05",
        analysts="india_market",
    )

    assert result["ready"] is False
    failures = {
        check["name"]: check
        for check in result["checks"]
        if check["status"] == "fail"
    }
    checks = {check["name"]: check for check in result["checks"]}
    assert checks["Provider selection"]["detail"] == (
        "none (no ready provider; configured default is openai)"
    )
    assert failures["Provider readiness"]["detail"] == "No LLM provider path is ready"
    assert "LLM credentials" not in failures
    assert (
        "OLLAMA_BASE_URL=http://localhost:11434/v1"
        in failures["Provider readiness"]["next_step"]
    )


@pytest.mark.unit
def test_first_run_check_passes_with_llm_key(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.chdir(tmp_path)

    result = run_first_run_checks(
        ticker="RELIANCE",
        analysis_date="2026-06-05",
        provider="openai",
        analysts="india_market",
    )

    assert result["ready"] is True
    report_path = next(check for check in result["checks"] if check["name"] == "Report path")
    assert report_path["detail"] == str(
        tmp_path / "reports" / "RELIANCE.NS" / "2026-06-05"
    )
    assert result["report_path"] == str(
        tmp_path / "reports" / "RELIANCE.NS" / "2026-06-05"
    )
    assert result["next_command"] == (
        "indiamarketagents analyze --ticker RELIANCE.NS --date 2026-06-05 "
        "--provider openai --research-depth 1 --no-display --no-save-prompt "
        "--analysts india_market"
    )


@pytest.mark.unit
def test_build_first_analysis_command_quotes_arguments():
    command = build_first_analysis_command(
        ticker="RELIANCE.NS",
        analysis_date="2026-06-05",
        provider="openai",
        analysts=["india_market", "india_fundamentals"],
    )

    assert command == (
        "indiamarketagents analyze --ticker RELIANCE.NS --date 2026-06-05 "
        "--provider openai --research-depth 1 --no-display --no-save-prompt "
        "--analysts india_market,india_fundamentals"
    )


@pytest.mark.unit
def test_first_run_checklist_keeps_provider_aware_analyze_example():
    checklist = Path("docs/FIRST_RUN_CHECKLIST.md").read_text(encoding="utf-8")

    assert "indiamarketagents analyze" in checklist
    assert "Provider readiness" in checklist
    assert "--provider openai" in checklist
    assert "--research-depth 1" in checklist
    assert "--no-display" in checklist
    assert "--no-save-prompt" in checklist


@pytest.mark.unit
def test_usage_playbook_distinguishes_rehearsal_from_research_readiness():
    playbook = Path("docs/USAGE_PLAYBOOK.md").read_text(encoding="utf-8")

    assert "For no-key workflow rehearsal, confirm:" in playbook
    assert "For the first LLM-backed research run, confirm:" in playbook
    assert "indiamarketagents sample-report --ticker RELIANCE.NS --date 2026-06-05" in playbook
    assert "indiamarketagents provider-status" in playbook
    assert (
        "Treat the repo as ready for the first research run only when "
        "`provider-status` shows at least one ready provider path"
        in playbook
    )
    assert "first_workflow_ready=False" in playbook


@pytest.mark.unit
def test_beginner_setup_uses_safe_generated_analysis_flow():
    setup = Path("docs/BEGINNER_SETUP.md").read_text(encoding="utf-8")

    assert "indiamarketagents init-env" in setup
    assert (
        "indiamarketagents report-status --ticker RELIANCE.NS --date 2026-06-05"
        in setup
    )
    assert "indiamarketagents provider-status" in setup
    assert (
        "indiamarketagents workflow-status --ticker RELIANCE.NS --date 2026-06-05"
        in setup
    )
    assert (
        "indiamarketagents first-run-check --ticker RELIANCE.NS --date 2026-06-05"
        in setup
    )
    assert "command that it prints" in setup
    assert "cp .env.example.india .env" not in setup
    assert (
        "first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider openai"
        not in setup
    )
    assert (
        "analyze --ticker RELIANCE.NS --date 2026-06-05 --research-depth 1"
        not in setup
    )


@pytest.mark.unit
def test_initialize_env_file_creates_from_india_template(tmp_path):
    template = tmp_path / ".env.example.india"
    template.write_text("OPENAI_API_KEY=\nOLLAMA_BASE_URL=\n", encoding="utf-8")
    env_file = tmp_path / ".env"

    result = initialize_env_file(env_path=env_file, template_path=template)

    assert result["created"] is True
    assert result["status"] == "created"
    assert env_file.read_text(encoding="utf-8") == template.read_text(encoding="utf-8")
    assert result["next_step"] == "Edit the local .env, then run indiamarketagents provider-status."


@pytest.mark.unit
def test_initialize_env_file_never_overwrites_existing_env(tmp_path):
    template = tmp_path / ".env.example.india"
    template.write_text("OPENAI_API_KEY=\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=keep-me\n", encoding="utf-8")

    result = initialize_env_file(env_path=env_file, template_path=template)

    assert result["created"] is False
    assert result["status"] == "exists"
    assert env_file.read_text(encoding="utf-8") == "OPENAI_API_KEY=keep-me\n"
    assert "leaving it unchanged" in result["message"]


@pytest.mark.unit
def test_provider_status_reports_no_ready_provider(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for env_var in (
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "OLLAMA_BASE_URL",
        "TRADINGAGENTS_LLM_PROVIDER",
    ):
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setattr(cli_main.shutil, "which", lambda command: None)

    result = get_provider_setup_status()

    assert result["ready"] is False
    assert result["ready_providers"] == []
    assert result["env_file"] == {
        "path": str(tmp_path / ".env"),
        "exists": False,
        "next_step": "Run indiamarketagents init-env, then add one provider setting.",
    }
    assert result["configured_provider"]["provider"] == "openai"
    assert result["configured_provider"]["source"] == "default config"
    assert result["configured_provider"]["status"] == "missing"
    assert result["configured_provider"]["detail"] == "OPENAI_API_KEY is not set"
    providers = {item["provider"]: item for item in result["providers"]}
    assert providers["openai"]["status"] == "missing"
    assert str(tmp_path / ".env") in providers["openai"]["next_step"]
    assert providers["ollama"]["status"] == "missing"
    assert "OLLAMA_BASE_URL=http://localhost:11434/v1" in result["recommended_next_step"]


@pytest.mark.unit
def test_provider_status_surfaces_configured_provider_from_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for env_var in (
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "OLLAMA_BASE_URL",
    ):
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "google")
    monkeypatch.setattr(cli_main.shutil, "which", lambda command: None)

    result = get_provider_setup_status()

    assert result["ready"] is False
    assert result["configured_provider"] == {
        "provider": "google",
        "source": "TRADINGAGENTS_LLM_PROVIDER",
        "status": "missing",
        "detail": "GOOGLE_API_KEY is not set",
        "next_step": f"Add GOOGLE_API_KEY=<your key> to {tmp_path / '.env'} or export it.",
    }


@pytest.mark.unit
def test_provider_status_prefers_ready_ollama_for_low_cost(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("OLLAMA_BASE_URL=http://localhost:11434/v1\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr(cli_main.shutil, "which", lambda command: None)

    result = get_provider_setup_status()

    assert result["ready"] is True
    assert "openai" in result["ready_providers"]
    assert "ollama" in result["ready_providers"]
    assert result["preferred_provider"] == "ollama"
    assert result["recommended_next_step"] == (
        "Run indiamarketagents first-run-check --ticker RELIANCE.NS "
        "--date 2026-06-05"
    )
    assert result["env_file"]["exists"] is True
    providers = {item["provider"]: item for item in result["providers"]}
    assert providers["ollama"]["detail"] == "OLLAMA_BASE_URL is set"
    assert "--provider ollama" in providers["ollama"]["next_step"]
    assert "http://localhost:11434/v1" not in providers["ollama"]["detail"]


@pytest.mark.unit
def test_first_workflow_status_reports_next_sample_report_step(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for env_var in (
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "OLLAMA_BASE_URL",
    ):
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setattr(cli_main.shutil, "which", lambda command: None)

    result = get_first_workflow_status()

    assert result["ready_for_analysis"] is False
    assert "sample-report --ticker RELIANCE.NS --date 2026-06-05" in result["next_step"]
    checks = {item["name"]: item for item in result["checks"]}
    assert checks["Ticker/date"]["status"] == "pass"
    assert checks["Saved report bundle"]["status"] == "pending"
    assert "complete_report.md" in checks["Saved report bundle"]["detail"]
    assert checks["Provider"]["status"] == "fail"
    assert checks["First-run preflight"]["status"] == "pending"


@pytest.mark.unit
def test_first_workflow_status_requires_complete_saved_report_bundle(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for env_var in (
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "OLLAMA_BASE_URL",
    ):
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setattr(cli_main.shutil, "which", lambda command: None)
    report_dir = tmp_path / "reports" / "RELIANCE.NS" / "2026-06-05"
    report_dir.mkdir(parents=True)
    (report_dir / "complete_report.md").write_text("sample", encoding="utf-8")

    result = get_first_workflow_status()

    assert result["ready_for_analysis"] is False
    assert result["report_status"]["ready"] is False
    assert "data_quality.json" in result["report_status"]["missing_required"]
    checks = {item["name"]: item for item in result["checks"]}
    assert checks["Saved report bundle"]["status"] == "pending"
    assert "missing:" in checks["Saved report bundle"]["detail"]
    assert "1_market_technical.md" in checks["Saved report bundle"]["detail"]


@pytest.mark.unit
def test_first_workflow_status_returns_analysis_command_when_ready(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr(cli_main.shutil, "which", lambda command: None)
    report_dir = tmp_path / "reports" / "RELIANCE.NS" / "2026-06-05"
    generate_sample_report(
        ticker="RELIANCE",
        analysis_date="2026-06-05",
        save_path=report_dir,
    )

    result = get_first_workflow_status()

    assert result["ready_for_analysis"] is True
    assert result["next_step"] == (
        "indiamarketagents analyze --ticker RELIANCE.NS --date 2026-06-05 "
        "--provider ollama --research-depth 1 --no-display --no-save-prompt"
    )
    checks = {item["name"]: item for item in result["checks"]}
    assert checks["Saved report bundle"]["status"] == "pass"
    assert checks["Provider"]["status"] == "pass"
    assert checks["First-run preflight"]["status"] == "pass"


@pytest.mark.unit
def test_report_status_reports_missing_saved_bundle(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = get_report_status(ticker="RELIANCE", analysis_date="2026-06-05")

    assert result["ready"] is False
    assert result["ticker"] == "RELIANCE.NS"
    assert result["report_path"] == str(
        tmp_path / "reports" / "RELIANCE.NS" / "2026-06-05"
    )
    assert "complete_report.md" in result["missing_required"]
    assert "sample-report --ticker RELIANCE.NS --date 2026-06-05" in result["next_step"]
    assert result["data_quality"]["available"] is False
    assert {artifact["status"] for artifact in result["artifacts"]} == {"missing"}


@pytest.mark.unit
def test_report_status_accepts_complete_sample_bundle(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    report_dir = tmp_path / "reports" / "RELIANCE.NS" / "2026-06-05"
    generate_sample_report(
        ticker="RELIANCE",
        analysis_date="2026-06-05",
        save_path=report_dir,
    )

    result = get_report_status(ticker="RELIANCE", analysis_date="2026-06-05")

    assert result["ready"] is True
    assert result["missing_required"] == []
    assert all(artifact["status"] == "present" for artifact in result["artifacts"])
    assert "Read disclaimer.md" in result["next_step"]
    assert result["data_quality"]["available"] is True
    assert result["data_quality"]["symbol"] == "RELIANCE.NS"
    assert result["data_quality"]["section_count"] >= 1
    assert "India Market Technical" in result["data_quality"]["unavailable_sections"]


@pytest.mark.unit
def test_first_run_check_requires_ollama_runtime(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setattr(cli_main.shutil, "which", lambda command: None)

    result = run_first_run_checks(
        ticker="RELIANCE",
        analysis_date="2026-06-05",
        provider="ollama",
        analysts="india_market",
    )

    assert result["ready"] is False
    failures = {
        check["name"]: check
        for check in result["checks"]
        if check["status"] == "fail"
    }
    assert "Ollama runtime" in failures
    assert "OLLAMA_BASE_URL is not set" in failures["Ollama runtime"]["detail"]


@pytest.mark.unit
def test_first_run_check_passes_with_ollama_base_url(monkeypatch, tmp_path):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr(cli_main.shutil, "which", lambda command: None)
    monkeypatch.chdir(tmp_path)

    result = run_first_run_checks(
        ticker="RELIANCE",
        analysis_date="2026-06-05",
        provider="ollama",
        analysts="india_market",
    )

    assert result["ready"] is True
    runtime_check = next(check for check in result["checks"] if check["name"] == "Ollama runtime")
    assert runtime_check["status"] == "pass"
    assert runtime_check["detail"] == "OLLAMA_BASE_URL is set"
    assert "http://localhost:11434/v1" not in runtime_check["detail"]


@pytest.mark.unit
def test_first_run_check_auto_selects_ready_ollama(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr(cli_main.shutil, "which", lambda command: None)
    monkeypatch.chdir(tmp_path)

    result = run_first_run_checks(
        ticker="RELIANCE",
        analysis_date="2026-06-05",
        analysts="india_market",
    )

    assert result["ready"] is True
    assert result["provider"] == "ollama"
    assert result["provider_source"] == "auto-selected ready provider"
    assert result["next_command"] == (
        "indiamarketagents analyze --ticker RELIANCE.NS --date 2026-06-05 "
        "--provider ollama --research-depth 1 --no-display --no-save-prompt "
        "--analysts india_market"
    )
    checks = {check["name"]: check for check in result["checks"]}
    assert checks["Provider selection"]["detail"] == "ollama (auto-selected ready provider)"


@pytest.mark.unit
def test_use_case_guidance_names_best_workflow_and_commands():
    guidance = get_use_case_guidance()

    assert "First-pass India equity research pack" in guidance["best_use_case"]
    assert "RELIANCE.NS" in guidance["best_use_case"]
    assert any("sample-report" in command for command in guidance["commands"])
    assert any("report-status" in command for command in guidance["commands"])
    assert any("init-env" in command for command in guidance["commands"])
    assert any("provider-status" in command for command in guidance["commands"])
    assert any("workflow-status" in command for command in guidance["commands"])
    assert any("first-run-check" in command for command in guidance["commands"])
    assert any("analyze command printed by first-run-check" in command for command in guidance["commands"])
    assert not any("analyze --ticker RELIANCE.NS" in command for command in guidance["commands"])
    assert any("Live trading" in poor_fit for poor_fit in guidance["poor_fit"])
    assert any("only when .env is missing" in note for note in guidance["notes"])
    assert any("report-status" in note for note in guidance["notes"])
    assert any("provider-status" in note for note in guidance["notes"])
    assert any("workflow-status" in note for note in guidance["notes"])
    assert any("printed by first-run-check" in note for note in guidance["notes"])
    assert "docs/USAGE_PLAYBOOK.md" in guidance["docs"]


@pytest.mark.unit
def test_sample_report_generates_explicit_no_data_bundle(tmp_path):
    report_file = generate_sample_report(
        ticker="RELIANCE",
        analysis_date="2026-06-05",
        save_path=tmp_path,
    )

    assert report_file == tmp_path / "complete_report.md"
    complete_report = report_file.read_text(encoding="utf-8")
    assert "SAMPLE ONLY - UNAVAILABLE" in complete_report
    assert "It did not use live market data" in complete_report
    assert INDIA_COMPLIANCE_DISCLAIMER in complete_report

    trader_view = (tmp_path / "trader_research_view.md").read_text(encoding="utf-8")
    assert "SAMPLE MODEL VIEW - UNAVAILABLE" in trader_view
    assert "not a trade instruction" in trader_view

    data_quality = json.loads((tmp_path / "data_quality.json").read_text(encoding="utf-8"))
    market = data_quality["sections"]["India Market Technical"]
    assert data_quality["symbol"] == "RELIANCE.NS"
    assert market["contains_unavailable_marker"] is True
    assert market["data_quality_detected"] is True
    assert market["confidence_detected"] is True


@pytest.mark.unit
def test_report_writer_creates_disclaimer_and_summary(tmp_path):
    final_state = {
        "trade_date": "2026-06-05",
        "india_market_report": "Market section\n\nSource: NSE\nData Quality: medium\nConfidence: medium",
        "india_fundamentals_report": "Fundamentals section\n\nSource: local filing\nData Quality: high\nConfidence: medium",
        "india_news_filings_report": "News section\n\nSources: BSE announcements\nData Quality: medium\nConfidence: medium",
        "india_macro_policy_report": "Macro section\n\nUNAVAILABLE: official macro datapoint missing.",
        "india_flows_report": "Flows section\n\nUNAVAILABLE: FII/DII data missing.",
        "india_compliance_report": "Compliance section",
        "trader_investment_plan": "Trader model view: Hold",
        "final_trade_decision": "Model view: Hold",
        "investment_debate_state": {"bull_history": "Bull", "bear_history": "Bear", "judge_decision": "Manager"},
        "risk_debate_state": {"aggressive_history": "Aggressive", "conservative_history": "Conservative", "neutral_history": "Neutral"},
    }
    report = save_report_to_disk(final_state, "RELIANCE.NS", tmp_path)
    assert report.exists()
    complete_report = report.read_text(encoding="utf-8")
    assert INDIA_COMPLIANCE_DISCLAIMER in complete_report
    assert "## Data Quality And Source Coverage" in complete_report
    assert "Trader Research View" in complete_report
    assert (tmp_path / "disclaimer.md").exists()
    assert (tmp_path / "trader_research_view.md").exists()
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["symbol"] == "RELIANCE.NS"
    assert summary["section_files"]["Trader Research View"] == "trader_research_view.md"


@pytest.mark.unit
def test_report_writer_adds_disclaimer_and_artifact_notes_to_section_files(tmp_path):
    final_state = {
        "trade_date": "2026-06-05",
        "india_market_report": "Source: NSE\nData Quality: medium\nConfidence: medium\nMarket section",
        "final_trade_decision": "Model view: Hold",
    }
    save_report_to_disk(final_state, "RELIANCE.NS", tmp_path)

    section = (tmp_path / "1_market_technical.md").read_text(encoding="utf-8")
    assert "## Compliance Disclaimer" in section
    assert INDIA_COMPLIANCE_DISCLAIMER in section
    assert "## Report Artifact Notes" in section
    assert "Source coverage detected in section text: Yes" in section
    assert "Data-quality coverage detected in section text: Yes" in section
    assert "Confidence coverage detected in section text: Yes" in section
    assert "writer-level coverage checks only" in section


@pytest.mark.unit
def test_report_writer_indexes_sources_and_data_quality_coverage(tmp_path):
    final_state = {
        "trade_date": "2026-06-05",
        "india_market_report": "Source: NSE\nData Quality: medium\nConfidence: medium\nMarket section",
        "india_macro_policy_report": "UNAVAILABLE: official macro datapoint missing.",
        "final_trade_decision": "Model view: Hold",
    }
    save_report_to_disk(final_state, "RELIANCE.NS", tmp_path)

    data_quality = json.loads((tmp_path / "data_quality.json").read_text(encoding="utf-8"))
    market = data_quality["sections"]["India Market Technical"]
    macro = data_quality["sections"]["India Macro & Policy"]
    flows = data_quality["sections"]["India Flows & Positioning"]

    assert data_quality["coverage_method"] == "writer_marker_detection_only"
    assert market["source_coverage_detected"] is True
    assert market["data_quality_detected"] is True
    assert market["confidence_detected"] is True
    assert macro["contains_unavailable_marker"] is True
    assert flows["status"] == "unavailable"
    assert "Section was not produced in the current run." in flows["warnings"]

    sources = (tmp_path / "sources.md").read_text(encoding="utf-8")
    assert "# Sources And Data Quality Coverage" in sources
    assert "| India Market Technical | 1_market_technical.md | available | Yes | Yes | Yes | No |" in sources
    assert "Section text does not include explicit source coverage." in sources


@pytest.mark.unit
def test_report_writer_rejects_unsafe_ticker_component(tmp_path):
    with pytest.raises(IndiaSymbolError):
        save_report_to_disk({"trade_date": "2026-06-05"}, "../RELIANCE", tmp_path)


@pytest.mark.unit
def test_default_report_path_uses_safe_india_ticker(monkeypatch, tmp_path):
    captured = {}

    def fake_graph_factory(selected_analysts, config, debug):
        class FakeGraph:
            def propagate(self, ticker, trade_date):
                captured["ticker"] = ticker
                captured["trade_date"] = trade_date
                return (
                    {
                        "trade_date": trade_date,
                        "india_market_report": "Market section",
                        "final_trade_decision": "Model view: Hold",
                    },
                    "Hold",
                )

        return FakeGraph()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli_main, "TradingAgentsGraph", fake_graph_factory)
    monkeypatch.setattr(cli_main, "get_api_key_env", lambda provider: None)

    decision = cli_main.run_noninteractive_analysis(
        ticker="RELIANCE",
        analysis_date="2026-06-05",
        analysts="india_market",
        provider="openai",
        quick_model=None,
        deep_model=None,
        research_depth=1,
        checkpoint=False,
        save_path=None,
        no_display=True,
        no_save_prompt=True,
    )

    assert decision == "Hold"
    assert captured == {"ticker": "RELIANCE.NS", "trade_date": "2026-06-05"}
    assert (tmp_path / "reports" / "RELIANCE.NS" / "2026-06-05" / "complete_report.md").exists()


@pytest.mark.unit
def test_cli_metadata_is_rebranded_and_keeps_legacy_entrypoint():
    repo_root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert "IndiaMarketAgents" in project["description"]
    assert project["scripts"]["indiamarketagents"] == "cli.main:app"
    assert project["scripts"]["tradingagents"] == "cli.main:app"
    assert isinstance(cli_main.app, typer.Typer)
