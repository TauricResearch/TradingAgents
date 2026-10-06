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
        with pytest.raises(ValueError, match="market, sentiment, news, fundamentals"):
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


class _Browser:
    def __init__(self):
        self.opened = []

    def open(self, url):
        self.opened.append(url)
        return True


@pytest.mark.unit
def test_save_and_show_answer_the_questions_after_the_run(monkeypatch, tmp_path):
    def no_prompt(*a, **k):
        raise AssertionError("prompted although --save/--show answered")

    monkeypatch.setattr(run.typer, "prompt", no_prompt)
    monkeypatch.setattr(run, "_graphical_browser", lambda: _Browser())   # even at a desktop
    shown = []
    monkeypatch.setattr(run, "display_complete_report", lambda state: shown.append(state))
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = object.__new__(TradingAgentsGraph)
    graph.config = {"results_dir": str(tmp_path)}
    graph.run_settings = lambda: {}
    state = {"market_report": "M", "final_trade_decision": "**Rating**: Hold"}

    run._offer_reports(state, graph, "NVDA", save=True, show=False)

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
    assert seen["flags"] == {**FLAGS, "html": None}


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


@pytest.mark.unit
def test_rounds_from_the_environment_do_not_claim_a_depth_was_chosen(monkeypatch, capsys):
    """With both round counts set, the depth question never appeared."""
    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "1")
    monkeypatch.setenv("TRADINGAGENTS_MAX_RISK_ROUNDS", "1")
    selections = {"research_depth": 3, "quick_think_llm": "q", "deep_think_llm": "d", "backend_url": None,
                  "llm_provider": "openai", "google_thinking_level": None, "openai_reasoning_effort": None,
                  "anthropic_effort": None, "output_language": "English"}

    run._build_run_config(selections, None)

    assert "the research depth you chose" not in capsys.readouterr().out


@pytest.mark.unit
def test_an_unknown_analyst_error_names_the_analysts_as_users_know_them():
    with pytest.raises(ValueError) as caught:
        prompts.parse_analysts("macro", AssetType.STOCK)
    assert "sentiment" in str(caught.value) and "social" not in str(caught.value)


def _selections_with_env(monkeypatch, keys=None):
    for name, value in UNATTENDED_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(selections, "fetch_announcements", lambda: None)
    monkeypatch.setattr(selections, "display_announcements", lambda *a: None)
    checked = keys if keys is not None else []
    monkeypatch.setattr(selections, "ensure_api_key", lambda provider: checked.append(provider))
    return checked


@pytest.mark.unit
def test_a_tier_on_another_provider_needs_its_own_model(monkeypatch, capsys):
    """Otherwise the CLI would take the main provider's model for it (#1440)."""
    _selections_with_env(monkeypatch)
    monkeypatch.setitem(selections.DEFAULT_CONFIG, "deep_think_provider", "anthropic")
    monkeypatch.delenv("TRADINGAGENTS_DEEP_THINK_LLM", raising=False)

    with pytest.raises(typer.Exit):
        selections._prompt_selections({}, FLAGS)
    assert "TRADINGAGENTS_DEEP_THINK_LLM" in capsys.readouterr().out


@pytest.mark.unit
def test_each_tier_provider_s_key_is_checked_before_the_run(monkeypatch):
    checked = _selections_with_env(monkeypatch)
    monkeypatch.setitem(selections.DEFAULT_CONFIG, "deep_think_provider", "anthropic")
    monkeypatch.setenv("TRADINGAGENTS_DEEP_THINK_LLM", "claude-opus-5-5")

    selections._prompt_selections({}, FLAGS)

    assert checked == ["ollama", "anthropic"]


def _report_graph(tmp_path):
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = object.__new__(TradingAgentsGraph)
    graph.config = {"results_dir": str(tmp_path)}
    graph.run_settings = lambda: {}
    return graph


STATE = {"market_report": "M", "final_trade_decision": "**Rating**: Hold"}


@pytest.mark.unit
def test_a_saved_report_includes_the_html_page_unless_declined(monkeypatch, tmp_path):
    monkeypatch.setattr(run, "display_complete_report", lambda state: None)

    run._offer_reports(STATE, _report_graph(tmp_path / "a"), "NVDA", save=True, show=False)
    run._offer_reports(STATE, _report_graph(tmp_path / "b"), "NVDA", save=True, show=False, html=False)

    assert list((tmp_path / "a").glob("reports/NVDA_*/complete_report.html"))
    assert list((tmp_path / "b").glob("reports/NVDA_*/complete_report.md"))
    assert not list((tmp_path / "b").glob("reports/NVDA_*/complete_report.html"))


def _answer(monkeypatch, answers):
    asked = []

    def prompt(text, default=None, **k):
        asked.append(text)
        for question, answer in answers.items():
            if question in text:
                return default if answer is None else answer
        raise AssertionError(f"unexpected question: {text}")

    monkeypatch.setattr(run.typer, "prompt", prompt)
    monkeypatch.setattr(run, "display_complete_report", lambda state: None)
    return asked


@pytest.mark.unit
def test_an_interactive_run_asks_for_the_html_page_and_opens_it(monkeypatch, tmp_path):
    asked = _answer(monkeypatch, {"Save report": "Y", "Save path": "rel/out", "HTML": "Y",
                                  "browser": "Y", "Display full report": "N"})
    browser = _Browser()
    monkeypatch.setattr(run, "_graphical_browser", lambda: browser)
    monkeypatch.chdir(tmp_path)

    run._offer_reports(STATE, _report_graph(tmp_path), "NVDA")

    page = tmp_path / "rel" / "out" / "complete_report.html"
    assert page.exists() and browser.opened == [page.resolve().as_uri()]
    assert [q for q in asked if "HTML" in q] and [q for q in asked if "browser" in q]


@pytest.mark.unit
def test_without_a_browser_window_the_page_is_not_offered_for_opening(monkeypatch, tmp_path):
    asked = _answer(monkeypatch, {"Save report": "Y", "Save path": None, "HTML": "Y",
                                  "Display full report": "N"})
    monkeypatch.setattr(run, "_graphical_browser", lambda: None)

    run._offer_reports(STATE, _report_graph(tmp_path), "NVDA")

    assert not [q for q in asked if "browser" in q]
    assert list(tmp_path.glob("reports/NVDA_*/complete_report.html"))


@pytest.mark.unit
def test_declining_the_html_page_saves_only_the_markdown(monkeypatch, tmp_path):
    asked = _answer(monkeypatch, {"Save report": "Y", "Save path": None, "HTML": "N",
                                  "Display full report": "N"})
    monkeypatch.setattr(run, "_graphical_browser", lambda: _Browser())

    run._offer_reports(STATE, _report_graph(tmp_path), "NVDA")

    assert not list(tmp_path.glob("reports/NVDA_*/complete_report.html"))
    assert not [q for q in asked if "browser" in q]


@pytest.mark.unit
@pytest.mark.parametrize("env, browser, offered", [
    ({}, "background", True),
    ({"SSH_CONNECTION": "10.0.0.1 22 10.0.0.2 22"}, "background", False),   # the page is on the remote
    ({"SSH_TTY": "/dev/pts/0"}, "background", False),
    ({}, "terminal", False),       # a text browser would take over the terminal
    ({}, "elinks", False),
    ({}, None, False),             # no browser at all
])
def test_a_page_is_opened_only_in_a_browser_window_on_this_machine(monkeypatch, env, browser, offered):
    import webbrowser

    for name in ("SSH_CONNECTION", "SSH_TTY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    def get():
        if browser is None:
            raise webbrowser.Error("no runnable browser")
        return {"background": lambda: webbrowser.BackgroundBrowser("firefox"),
                "terminal": lambda: webbrowser.GenericBrowser("lynx"),
                "elinks": lambda: webbrowser.Elinks("elinks")}[browser]()

    monkeypatch.setattr(run.webbrowser, "get", get)
    assert (run._graphical_browser() is not None) is offered


@pytest.mark.unit
@pytest.mark.parametrize("args, expected", [([], None), (["--no-html"], False), (["--html"], True)])
def test_the_html_flag_reaches_the_run(monkeypatch, args, expected):
    from typer.testing import CliRunner

    from cli import main as cli_main

    seen = {}
    monkeypatch.setattr(cli_main, "run_analysis", lambda **kw: seen.update(kw))
    result = CliRunner().invoke(cli_main.app, ["--ticker", "NVDA", "--save", "--no-show", *args])

    assert result.exit_code == 0 and seen["flags"]["html"] is expected


@pytest.mark.unit
def test_only_the_providers_the_tiers_use_need_a_key(monkeypatch):
    """Both tiers on a local Ollama: the main provider's key is not needed."""
    checked = _selections_with_env(monkeypatch)
    for tier in ("quick", "deep"):
        monkeypatch.setitem(selections.DEFAULT_CONFIG, f"{tier}_think_provider", "ollama")
        monkeypatch.setenv(f"TRADINGAGENTS_{tier.upper()}_THINK_LLM", "llama3.1")

    selections._prompt_selections({}, FLAGS)

    assert checked == ["ollama"]


@pytest.mark.unit
def test_a_page_the_browser_cannot_open_is_pointed_to(monkeypatch, tmp_path, capsys):
    class Failing(_Browser):
        def open(self, url):
            return False

    _answer(monkeypatch, {"Save report": "Y", "Save path": None, "HTML": "Y", "browser": "Y",
                          "Display full report": "N"})
    monkeypatch.setattr(run, "_graphical_browser", lambda: Failing())
    monkeypatch.setattr(run.console, "print", lambda *a, **k: print(*a))

    run._offer_reports(STATE, _report_graph(tmp_path), "NVDA")

    assert "complete_report.html" in capsys.readouterr().out.split("the page is at:")[-1]
