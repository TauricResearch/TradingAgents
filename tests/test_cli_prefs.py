"""The CLI remembers what you chose last time and offers it back.

Prefill only: every prompt still appears, so a run never starts on a choice the
user did not see. Environment variables keep skipping their step outright and
win over anything remembered. Remembered values are validated against the
current choices each time, since models and providers come and go between
versions and a stale one must not be offered.
"""

from __future__ import annotations

from unittest import mock

import pytest

import cli.selections as cli_selections
from cli.models import AnalystType
from cli.prefs import load_last_run, sanitize, save_last_run

SAVED = {
    "output_language": "English",
    "analysts": ["market", "fundamentals"],
    "research_depth": 3,
    "llm_provider": "openai",
    "quick_think_llm": "gpt-5.6-mini",
    "deep_think_llm": "gpt-5.6",
}


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setattr("cli.prefs._PREFS_PATH", tmp_path / "cli_prefs.json")
    return tmp_path


@pytest.mark.unit
def test_round_trip():
    save_last_run(SAVED)
    assert load_last_run() == SAVED


@pytest.mark.unit
def test_missing_file_is_not_an_error():
    assert load_last_run() == {}


@pytest.mark.unit
def test_a_corrupt_file_degrades_to_no_memory(_home):
    (_home / "cli_prefs.json").write_text("{not json")
    assert load_last_run() == {}


@pytest.mark.unit
def test_a_half_written_file_cannot_be_observed(_home):
    """Two runs finishing together must never leave a torn file behind."""
    save_last_run(SAVED)
    save_last_run({**SAVED, "research_depth": 5})
    assert load_last_run()["research_depth"] == 5
    assert list((_home).glob("*.tmp*")) == []


# --- validation against the current choices ---------------------------------

@pytest.mark.unit
def test_a_model_that_no_longer_exists_is_dropped():
    # gpt-5.4 is still accepted by config, but is no longer in the picker's list.
    kept = sanitize({**SAVED, "quick_think_llm": "gpt-5.4"}, "stock")
    assert "quick_think_llm" not in kept
    assert kept["deep_think_llm"] == "gpt-5.6"  # the valid sibling survives


@pytest.mark.unit
def test_an_unknown_provider_drops_itself_and_its_models():
    kept = sanitize({**SAVED, "llm_provider": "no-such-provider"}, "stock")
    assert "llm_provider" not in kept
    assert "quick_think_llm" not in kept and "deep_think_llm" not in kept


@pytest.mark.unit
def test_analysts_are_narrowed_to_the_asset_type():
    kept = sanitize(SAVED, "crypto")
    assert AnalystType.FUNDAMENTALS.value not in kept["analysts"]
    assert AnalystType.MARKET.value in kept["analysts"]


@pytest.mark.unit
def test_junk_values_are_dropped_rather_than_offered():
    kept = sanitize({"research_depth": 99, "analysts": ["astrology"], "output_language": 5}, "stock")
    assert kept == {}


@pytest.mark.unit
def test_a_region_specific_provider_survives():
    kept = sanitize({**SAVED, "llm_provider": "qwen-cn", "quick_think_llm": None}, "stock")
    assert kept["llm_provider"] == "qwen-cn"


# --- wiring ------------------------------------------------------------------

def _answer_every_prompt(monkeypatch):
    """Drive the real selection flow, answering each prompt with a fixed value."""
    import cli.main as m

    monkeypatch.setattr(cli_selections, "fetch_announcements", lambda: [])
    monkeypatch.setattr(cli_selections, "display_announcements", lambda *a: None)
    monkeypatch.setattr(cli_selections, "get_ticker", lambda: "NVDA")
    monkeypatch.setattr(cli_selections, "get_analysis_date", lambda: "2026-09-01")
    monkeypatch.setattr(cli_selections, "ask_output_language", lambda default=None: "English")
    monkeypatch.setattr(cli_selections, "select_analysts", lambda asset_type, default=None: [AnalystType.MARKET])
    monkeypatch.setattr(cli_selections, "select_research_depth", lambda default=None: 3)
    monkeypatch.setattr(cli_selections, "select_llm_provider", lambda default=None: ("openai", None))
    monkeypatch.setattr(cli_selections, "select_shallow_thinking_agent", lambda p, default=None: "gpt-5.6-mini")
    monkeypatch.setattr(cli_selections, "select_deep_thinking_agent", lambda p, default=None: "gpt-5.6")
    monkeypatch.setattr(cli_selections, "ask_openai_reasoning_effort", lambda: "medium")
    return m


@pytest.mark.unit
def test_selections_are_remembered_after_a_run(monkeypatch):
    """Drives the real flow: a stubbed selections dict would hide a key mismatch."""
    _answer_every_prompt(monkeypatch)

    cli_selections.get_user_selections()

    remembered = load_last_run()
    assert remembered["analysts"] == ["market"]
    assert remembered["quick_think_llm"] == "gpt-5.6-mini"
    assert remembered["deep_think_llm"] == "gpt-5.6"
    assert remembered["llm_provider"] == "openai"
    assert "ticker" not in remembered  # changes every run; never remembered
    assert "analysis_date" not in remembered  # a stale date must not be offered


@pytest.mark.unit
def test_a_custom_language_is_remembered_without_breaking_the_next_run():
    """A free-text answer is not one of the menu's choices, and questionary
    rejects a default it cannot find, so offering it back would crash startup."""
    from cli.prompts import ask_output_language

    save_last_run({"output_language": "Turkish"})
    with mock.patch("cli.prompts.questionary.select") as select:
        select.return_value.ask.return_value = "English"
        ask_output_language(load_last_run()["output_language"])
    assert select.call_args.kwargs["default"] is None


@pytest.mark.unit
def test_a_remembered_endpoint_is_offered_back(monkeypatch):
    """Users of a local or custom endpoint retyped the URL every run: it was
    remembered and validated, then never read."""

    save_last_run({"llm_provider": "openai_compatible", "backend_url": "http://localhost:1234/v1"})
    offered = {}
    monkeypatch.setattr(cli_selections, "select_llm_provider", lambda default=None: ("openai_compatible", None))
    monkeypatch.setattr(cli_selections, "prompt_openai_compatible_url",
                        lambda default=None: offered.setdefault("default", default) or "http://x/v1")
    monkeypatch.setattr(cli_selections, "fetch_announcements", lambda: [])
    monkeypatch.setattr(cli_selections, "display_announcements", lambda *a: None)
    monkeypatch.setattr(cli_selections, "get_ticker", lambda: "NVDA")
    monkeypatch.setattr(cli_selections, "get_analysis_date", lambda: "2026-09-01")
    monkeypatch.setattr(cli_selections, "ask_output_language", lambda default=None: "English")
    monkeypatch.setattr(cli_selections, "select_analysts", lambda asset_type, default=None: [AnalystType.MARKET])
    monkeypatch.setattr(cli_selections, "select_research_depth", lambda default=None: 1)
    monkeypatch.setattr(cli_selections, "select_shallow_thinking_agent", lambda p, default=None: "local-model")
    monkeypatch.setattr(cli_selections, "select_deep_thinking_agent", lambda p, default=None: "local-model")

    cli_selections.get_user_selections()

    assert offered["default"] == "http://localhost:1234/v1"
