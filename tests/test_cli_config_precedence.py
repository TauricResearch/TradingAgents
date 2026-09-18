"""CLI config precedence (#976, #977).

An explicit environment override for the debate/risk round counts, or the
checkpoint flag, must win over the interactive research-depth selection — the CLI
must not clobber an env-configured value back to a prompt/flag default.
"""

from unittest import mock

import pytest

import cli.main as m

# Minimal selections dict shaped like get_user_selections()'s return value.
SELECTIONS = {
    "research_depth": 5,
    "quick_think_llm": "gpt-5.4-mini",
    "deep_think_llm": "gpt-5.5",
    "backend_url": None,
    "llm_provider": "openai",
    "google_thinking_level": None,
    "openai_reasoning_effort": None,
    "anthropic_effort": None,
    "output_language": "English",
}


def test_research_depth_sets_both_rounds_without_env(monkeypatch):
    for var in ("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "TRADINGAGENTS_MAX_RISK_ROUNDS"):
        monkeypatch.delenv(var, raising=False)
    cfg = m._build_run_config(SELECTIONS, checkpoint=None)
    assert cfg["max_debate_rounds"] == 5
    assert cfg["max_risk_discuss_rounds"] == 5


def test_env_round_counts_win_over_selection(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "2")
    monkeypatch.setenv("TRADINGAGENTS_MAX_RISK_ROUNDS", "4")
    # DEFAULT_CONFIG already reflects the env (applied at import); emulate that.
    patched = dict(m.DEFAULT_CONFIG, max_debate_rounds=2, max_risk_discuss_rounds=4)
    with mock.patch.object(m, "DEFAULT_CONFIG", patched):
        cfg = m._build_run_config(SELECTIONS, checkpoint=None)
    assert cfg["max_debate_rounds"] == 2  # env value, not research_depth=5
    assert cfg["max_risk_discuss_rounds"] == 4


def test_partial_env_only_overrides_that_count(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "2")
    monkeypatch.delenv("TRADINGAGENTS_MAX_RISK_ROUNDS", raising=False)
    patched = dict(m.DEFAULT_CONFIG, max_debate_rounds=2)
    with mock.patch.object(m, "DEFAULT_CONFIG", patched):
        cfg = m._build_run_config(SELECTIONS, checkpoint=None)
    assert cfg["max_debate_rounds"] == 2  # env wins
    assert cfg["max_risk_discuss_rounds"] == 5  # falls through to research_depth


def test_checkpoint_none_preserves_env_default():
    patched = dict(m.DEFAULT_CONFIG, checkpoint_enabled=True)  # e.g. env-enabled
    with mock.patch.object(m, "DEFAULT_CONFIG", patched):
        cfg = m._build_run_config(SELECTIONS, checkpoint=None)
    assert cfg["checkpoint_enabled"] is True  # not clobbered back to False


@pytest.mark.parametrize("flag", [True, False])
def test_checkpoint_flag_overrides_env(flag):
    patched = dict(m.DEFAULT_CONFIG, checkpoint_enabled=not flag)
    with mock.patch.object(m, "DEFAULT_CONFIG", patched):
        cfg = m._build_run_config(SELECTIONS, checkpoint=flag)
    assert cfg["checkpoint_enabled"] is flag


@pytest.mark.unit
def test_glm_resolves_to_the_endpoint_its_key_belongs_to():
    """The provider table, the client registry and the key mapping must name the
    same platform: glm is Z.AI international (ZHIPU_API_KEY) and glm-cn is
    BigModel China. A mismatch sends the key to the other platform and every
    call fails auth."""
    from cli.utils import resolve_backend_url
    from tradingagents.llm_clients.api_key_env import get_api_key_env
    from tradingagents.llm_clients.openai_client import OPENAI_COMPATIBLE_PROVIDERS

    assert resolve_backend_url("glm", None, None) == OPENAI_COMPATIBLE_PROVIDERS["glm"].base_url
    assert get_api_key_env("glm") == "ZHIPU_API_KEY"
    assert "z.ai" in OPENAI_COMPATIBLE_PROVIDERS["glm"].base_url
    assert "bigmodel.cn" in OPENAI_COMPATIBLE_PROVIDERS["glm-cn"].base_url


@pytest.mark.unit
def test_a_half_set_round_count_says_which_value_won(capsys, monkeypatch):
    """With only one of the two round-count variables set, the depth prompt is
    still shown but half the answer is discarded; the user was never told."""
    import cli.main as m

    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "1")
    monkeypatch.delenv("TRADINGAGENTS_MAX_RISK_ROUNDS", raising=False)
    printed = []
    monkeypatch.setattr(m.console, "print", lambda *a, **k: printed.append(str(a[0]) if a else ""))

    config = m._build_run_config({
        "ticker": "NVDA", "analysis_date": "2026-09-01", "asset_type": "stock",
        "analysts": [], "research_depth": 5, "llm_provider": "openai",
        "quick_think_llm": "gpt-5.6-luna", "deep_think_llm": "gpt-5.6",
        "backend_url": None, "output_language": "English",
    }, None)

    assert config["max_risk_discuss_rounds"] == 5
    assert any("TRADINGAGENTS_MAX_DEBATE_ROUNDS" in line for line in printed), printed
