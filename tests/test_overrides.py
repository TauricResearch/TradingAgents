"""TRADER_HOME/settings.json (ADR 0007): the file, and how the settings and the research
config read it."""

import json
from datetime import UTC, datetime

import pytest

from trader import overrides
from trader.research import build_config
from trader.settings import Settings
from tradingagents.default_config import DEFAULT_CONFIG

AT = datetime(2026, 11, 7, 5, 0, tzinfo=UTC)
LLM = {
    "deep_think_llm": "claude-sonnet-5-5", "quick_think_llm": "claude-haiku-5-5",
    "deep_think_provider": "anthropic", "quick_think_provider": "anthropic",
}
# Models no price table knows, so a test reaches the environment and the None fallbacks.
FAKE_DEEP, FAKE_QUICK = "no-such-deep-model", "no-such-quick-model"


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Settings.from_env reads ``tmp_path``; the environment prices nothing and
    DEFAULT_CONFIG names models the official table lacks."""
    monkeypatch.setenv("TRADER_HOME", str(tmp_path))
    monkeypatch.setenv("TRADER_PRICE_DEEP", "")
    monkeypatch.setenv("TRADER_PRICE_QUICK", "")
    monkeypatch.setitem(DEFAULT_CONFIG, "deep_think_llm", FAKE_DEEP)
    monkeypatch.setitem(DEFAULT_CONFIG, "quick_think_llm", FAKE_QUICK)
    return tmp_path


# -- the file -----------------------------------------------------------------


def test_load_is_none_without_a_file(tmp_path):
    assert overrides.load(tmp_path) is None
    assert overrides.tier_models(None) == {}


@pytest.mark.parametrize("text", ["{not json", '{"version": 1}', '{"llm": "x"}', "[]"])
def test_load_refuses_a_file_that_is_no_settings(tmp_path, text):
    (tmp_path / "settings.json").write_text(text)
    with pytest.raises(ValueError, match="settings.json"):
        overrides.load(tmp_path)


def test_save_writes_the_file_whole_and_load_reads_it_back(tmp_path):
    data = overrides.save(tmp_path, LLM, {"claude-sonnet-5-5": (2.0, 10.0)}, "web", AT)
    assert data == {
        "version": 1,
        "llm": LLM,
        "prices": {"claude-sonnet-5-5": [2.0, 10.0]},
        "updated_at": "2026-11-07T05:00:00Z",
        "history": [{
            "at": "2026-11-07T05:00:00Z", "deep": "claude-sonnet-5-5",
            "quick": "claude-haiku-5-5", "note": "web",
        }],
    }
    assert overrides.load(tmp_path) == data
    assert json.loads((tmp_path / "settings.json").read_text()) == data
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]  # no temporary file left
    assert overrides.tier_models(data) == LLM


def test_save_merges_the_prices_and_prepends_the_history(tmp_path):
    overrides.save(tmp_path, LLM, {"claude-sonnet-5-5": (2.0, 10.0), "old": (1.0, 1.0)}, "web", AT)
    later = {**LLM, "deep_think_llm": "claude-opus-5-5", "extra": "kept in llm"}
    data = overrides.save(
        tmp_path, later, {"claude-opus-5-5": (4.0, 20.0), "old": (3.0, 3.0)}, "cli",
        datetime(2026, 11, 8, tzinfo=UTC),
    )
    assert data["llm"] == later
    assert data["prices"] == {
        "claude-sonnet-5-5": [2.0, 10.0], "old": [3.0, 3.0], "claude-opus-5-5": [4.0, 20.0],
    }
    assert data["updated_at"] == "2026-11-08T00:00:00Z"
    assert [(h["at"], h["deep"], h["note"]) for h in data["history"]] == [
        ("2026-11-08T00:00:00Z", "claude-opus-5-5", "cli"),
        ("2026-11-07T05:00:00Z", "claude-sonnet-5-5", "web"),
    ]
    assert overrides.tier_models(data) == {k: v for k, v in later.items() if k != "extra"}


def test_the_history_keeps_the_newest_fifty(tmp_path):
    for i in range(60):
        data = overrides.save(tmp_path, {**LLM, "deep_think_llm": f"m{i}"}, {}, "web", AT)
    assert len(data["history"]) == 50
    assert [h["deep"] for h in data["history"][:3]] == ["m59", "m58", "m57"]
    assert data["history"][-1]["deep"] == "m10"


# -- the settings -------------------------------------------------------------


def test_without_a_file_the_settings_are_the_environments(env, monkeypatch):
    settings = Settings.from_env()
    assert settings.home == env
    assert settings.llm is None
    assert (settings.price_deep, settings.price_quick) == (None, None)
    monkeypatch.setenv("TRADER_PRICE_DEEP", "15,75")
    monkeypatch.setenv("TRADER_PRICE_QUICK", "3,15")
    settings = Settings.from_env()
    assert (settings.price_deep, settings.price_quick) == ((15.0, 75.0), (3.0, 15.0))


def test_a_malformed_environment_price_still_fails(env, monkeypatch):
    monkeypatch.setitem(DEFAULT_CONFIG, "deep_think_llm", "claude-sonnet-5-5")  # priced
    monkeypatch.setenv("TRADER_PRICE_DEEP", "fifteen")
    with pytest.raises(ValueError, match="TRADER_PRICE_DEEP"):
        Settings.from_env()


def test_the_official_price_of_the_env_model_beats_the_environment(env, monkeypatch):
    monkeypatch.setitem(DEFAULT_CONFIG, "deep_think_llm", "claude-sonnet-5.5")  # as .env spells it
    monkeypatch.setenv("TRADER_PRICE_DEEP", "15,75")
    settings = Settings.from_env()
    assert settings.price_deep == (2.0, 10.0)
    assert settings.price_quick is None
    assert settings.llm is None


def test_the_file_names_the_models_and_its_prices_come_first(env, monkeypatch):
    monkeypatch.setenv("TRADER_PRICE_DEEP", "15,75")
    overrides.save(
        env, {**LLM, "deep_think_llm": FAKE_DEEP, "quick_think_llm": "claude-haiku-5-5"},
        {FAKE_DEEP: (7.0, 8.0), "claude-haiku-5-5": (9.0, 9.5)}, "web", AT,
    )
    settings = Settings.from_env()
    assert settings.llm == {**LLM, "deep_think_llm": FAKE_DEEP, "quick_think_llm": "claude-haiku-5-5"}
    assert settings.price_deep == (7.0, 8.0)   # the file's, over the environment's
    assert settings.price_quick == (9.0, 9.5)  # the file's, over the official 0.1 / 0.5


def test_a_file_model_without_a_saved_price_falls_through_the_table_to_the_environment(
    env, monkeypatch
):
    monkeypatch.setenv("TRADER_PRICE_QUICK", "3,15")
    overrides.save(env, {**LLM, "quick_think_llm": FAKE_QUICK}, {}, "web", AT)
    settings = Settings.from_env()
    assert settings.price_deep == (2.0, 10.0)   # claude-sonnet-5-5: the official table
    assert settings.price_quick == (3.0, 15.0)  # FAKE_QUICK: the environment
    monkeypatch.setenv("TRADER_PRICE_QUICK", "")
    assert Settings.from_env().price_quick is None


def test_a_broken_file_fails_the_settings(env):
    (env / "settings.json").write_text("{")
    with pytest.raises(ValueError, match="settings.json"):
        Settings.from_env()


def test_with_overrides_reads_the_given_home(env, tmp_path, monkeypatch):
    other = tmp_path / "other"
    overrides.save(other, LLM, {}, "web", AT)
    assert Settings.with_overrides(other).llm == LLM
    assert Settings.from_env().llm is None


# -- the research config ------------------------------------------------------


def test_build_config_applies_the_four_llm_keys_and_no_other(tmp_path):
    plain = build_config(Settings(home=tmp_path))
    config = build_config(Settings(home=tmp_path, llm={**LLM, "results_dir": "/elsewhere", "x": 1}))
    assert {k: config[k] for k in LLM} == LLM
    assert config["results_dir"] == plain["results_dir"] and "x" not in config
    assert {k: v for k, v in config.items() if k not in LLM} == {
        k: v for k, v in plain.items() if k not in LLM
    }


def test_build_config_without_overrides_is_unchanged(tmp_path):
    assert build_config(Settings(home=tmp_path, llm=None)) == build_config(Settings(home=tmp_path))
    assert build_config(Settings(home=tmp_path))["deep_think_llm"] == DEFAULT_CONFIG["deep_think_llm"]
