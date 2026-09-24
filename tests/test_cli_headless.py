"""Unattended CLI runs: flags answer the per-run questions, and a run with no
terminal stops up front, naming what to set, instead of waiting on a prompt."""

import datetime

import pytest
import typer

from cli import prompts, run, selections
from cli.models import AnalystType, AssetType

UNATTENDED_ENV = {
    "TRADINGAGENTS_OUTPUT_LANGUAGE": "English",
    "TRADINGAGENTS_MAX_DEBATE_ROUNDS": "1",
    "TRADINGAGENTS_MAX_RISK_ROUNDS": "1",
    "TRADINGAGENTS_LLM_PROVIDER": "openai",
    "TRADINGAGENTS_QUICK_THINK_LLM": "gpt-6-luna",
}
FLAGS = {"ticker": "NVDA", "date": "2026-09-23", "analysts": "market,news", "save": True, "show": False}


@pytest.mark.unit
class TestFlagValues:
    def test_a_ticker_is_normalised_and_an_empty_one_refused(self):
        assert prompts.parse_ticker("0700.hk") == "0700.HK"
        with pytest.raises(ValueError, match="ticker"):
            prompts.parse_ticker("  ")
        with pytest.raises(ValueError, match="ticker"):
            prompts.parse_ticker("NV DA")

    def test_a_date_must_be_a_past_or_present_day(self):
        assert prompts.parse_analysis_date("2026-09-23") == "2026-09-23"
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        with pytest.raises(ValueError, match="future"):
            prompts.parse_analysis_date(tomorrow)
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            prompts.parse_analysis_date("23/09/2026")

    def test_analysts_are_named_and_checked_against_the_asset(self):
        assert prompts.parse_analysts(" Market, news ", AssetType.STOCK) == [AnalystType.MARKET, AnalystType.NEWS]
        with pytest.raises(ValueError, match="market, social, news, fundamentals"):
            prompts.parse_analysts("market,macro", AssetType.STOCK)
        with pytest.raises(ValueError, match="crypto"):
            prompts.parse_analysts("fundamentals", AssetType.CRYPTO)
        with pytest.raises(ValueError, match="at least one"):
            prompts.parse_analysts(" , ", AssetType.STOCK)


@pytest.mark.unit
def test_flags_skip_exactly_their_own_steps(monkeypatch):
    for name, value in UNATTENDED_ENV.items():
        monkeypatch.setenv(name, value)

    def no_prompt(*a, **k):
        raise AssertionError("prompted although a flag answered the step")

    for step in ("get_ticker", "get_analysis_date", "select_analysts"):
        monkeypatch.setattr(selections, step, no_prompt)
    monkeypatch.setattr(selections, "fetch_announcements", lambda: None)
    monkeypatch.setattr(selections, "display_announcements", lambda *a: None)

    chosen = selections._prompt_selections({}, FLAGS)

    assert chosen["ticker"] == "NVDA" and chosen["analysis_date"] == "2026-09-23"
    assert chosen["analysts"] == [AnalystType.MARKET, AnalystType.NEWS]


@pytest.mark.unit
def test_without_a_terminal_every_unanswered_question_is_named_before_the_run(monkeypatch, capsys):
    for name in UNATTENDED_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(run.sys.stdin, "isatty", lambda: False)

    with pytest.raises(typer.Exit):
        run.run_analysis(flags={"ticker": "NVDA"})

    out = capsys.readouterr().out
    for needed in ("--date", "--analysts", "--save", "--show", "TRADINGAGENTS_LLM_PROVIDER"):
        assert needed in out
    assert "--ticker" not in out


@pytest.mark.unit
def test_nothing_is_missing_when_flags_and_environment_answer_every_step(monkeypatch):
    for name, value in UNATTENDED_ENV.items():
        monkeypatch.setenv(name, value)
    assert selections.unattended_gaps(FLAGS) == []


@pytest.mark.unit
def test_save_and_show_answer_the_questions_after_the_run(monkeypatch, tmp_path):
    def no_prompt(*a, **k):
        raise AssertionError("prompted although --save/--show answered")

    monkeypatch.setattr(run.typer, "prompt", no_prompt)
    shown = []
    monkeypatch.setattr(run, "display_complete_report", lambda state: shown.append(state))
    graph = type("G", (), {"run_settings": lambda self: {}})()
    state = {"market_report": "M", "final_trade_decision": "**Rating**: Hold"}

    run._offer_reports(state, graph, {"results_dir": str(tmp_path)}, "NVDA", save=True, show=False)

    assert list(tmp_path.glob("reports/NVDA_*/complete_report.md"))
    assert shown == []



@pytest.mark.unit
def test_an_announcement_does_not_wait_for_enter_without_a_terminal(monkeypatch):
    from cli import announcements
    from cli.display import console

    def no_wait(*a):
        raise AssertionError("waited for Enter with no terminal")

    monkeypatch.setattr(announcements.getpass, "getpass", no_wait)
    monkeypatch.setattr(announcements.sys.stdin, "isatty", lambda: False)
    announcements.display_announcements(console, {"content": "Maintenance tonight", "require_attention": True})


@pytest.mark.unit
def test_a_missing_key_without_a_terminal_names_the_variable(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(prompts.sys.stdin, "isatty", lambda: False)

    with pytest.raises(typer.Exit):
        prompts.ensure_api_key("openai")
    assert "OPENAI_API_KEY" in capsys.readouterr().out


@pytest.mark.unit
def test_the_command_passes_its_flags_to_the_run(monkeypatch):
    from typer.testing import CliRunner

    from cli import main as cli_main

    seen = {}
    monkeypatch.setattr(cli_main, "run_analysis", lambda **kw: seen.update(kw))

    result = CliRunner().invoke(cli_main.app, ["--ticker", "NVDA", "--date", "2026-09-23",
                                               "--analysts", "market,news", "--save", "--no-show"])

    assert result.exit_code == 0, result.output
    assert seen["flags"] == FLAGS


@pytest.mark.unit
def test_sentiment_names_the_sentiment_analyst():
    assert prompts.parse_analysts("sentiment,market", AssetType.STOCK) == [AnalystType.MARKET, AnalystType.SOCIAL]


@pytest.mark.unit
def test_an_empty_flag_is_checked_like_its_step_not_reported_missing(monkeypatch):
    assert "--ticker" not in selections.unattended_gaps(dict(FLAGS, ticker=""))


@pytest.mark.unit
def test_a_closed_stdin_counts_as_no_terminal(monkeypatch, capsys):
    monkeypatch.setattr(run.sys, "stdin", None)
    with pytest.raises(typer.Exit):
        run.run_analysis(flags={})
    assert "--ticker" in capsys.readouterr().out
