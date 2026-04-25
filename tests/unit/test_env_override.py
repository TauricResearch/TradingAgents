"""Tests for deterministic config precedence in build_default_config()."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tradingagents.default_config import build_default_config, get_env_value

if TYPE_CHECKING:
    from pathlib import Path


def _build(
    *,
    environ: dict[str, str] | None = None,
    load_dotenv: bool = False,
    dotenv_path: Path | None = None,
) -> dict:
    return build_default_config(
        load_dotenv=load_dotenv,
        dotenv_path=dotenv_path,
        environ=environ or {},
    )


def test_no_env_set_uses_hardcoded_defaults():
    cfg = _build()
    assert cfg["llm_provider"] == "openai"
    assert cfg["deep_think_llm"] == "gpt-5.2"
    assert cfg["mid_think_llm"] is None
    assert cfg["quick_think_llm"] == "gpt-5-mini"
    assert cfg["backend_url"] == "https://api.openai.com/v1"
    assert cfg["llm_timeout"] == 300.0
    assert cfg["max_debate_rounds"] == 2
    assert cfg["data_vendors"]["scanner_data"] == "yfinance"


def test_process_env_overrides_defaults():
    cfg = _build(
        environ={
            "TRADINGAGENTS_LLM_PROVIDER": "openrouter",
            "TRADINGAGENTS_LLM_TIMEOUT_SEC": "45",
            "TRADINGAGENTS_MID_THINK_LLM_TIMEOUT_SEC": "12.5",
            "TRADINGAGENTS_SCANNER_SUMMARIZER_TIMEOUT_SEC": "210",
            "TRADINGAGENTS_TOOL_EXECUTION_TIMEOUT_SEC": "75",
            "TRADINGAGENTS_SCAN_TIMEOUT_SEC": "2400",
        }
    )
    assert cfg["llm_provider"] == "openrouter"
    assert cfg["llm_timeout"] == 45.0
    assert cfg["mid_think_llm_timeout"] == 12.5
    assert cfg["scanner_summarizer_timeout"] == 210.0
    assert cfg["tool_execution_timeout"] == 75.0
    assert cfg["scan_timeout_seconds"] == 2400.0


def test_dotenv_overrides_defaults(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "TRADINGAGENTS_LLM_PROVIDER=google",
                "TRADINGAGENTS_MAX_DEBATE_ROUNDS=3",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cfg = _build(load_dotenv=True, dotenv_path=env_file)
    assert cfg["llm_provider"] == "google"
    assert cfg["max_debate_rounds"] == 3


def test_process_env_overrides_dotenv(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TRADINGAGENTS_LLM_PROVIDER=google\nTRADINGAGENTS_BACKEND_URL=http://dotenv\n",
        encoding="utf-8",
    )

    cfg = _build(
        load_dotenv=True,
        dotenv_path=env_file,
        environ={
            "TRADINGAGENTS_LLM_PROVIDER": "openrouter",
            "TRADINGAGENTS_BACKEND_URL": "http://process",
        },
    )
    assert cfg["llm_provider"] == "openrouter"
    assert cfg["backend_url"] == "http://process"


def test_get_env_value_reads_plain_dotenv_key(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_API_KEY=dotenv-secret\n", encoding="utf-8")

    value = get_env_value(
        "OPENROUTER_API_KEY",
        load_dotenv=True,
        dotenv_path=env_file,
        environ={},
    )

    assert value == "dotenv-secret"


def test_get_env_value_process_env_overrides_dotenv(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_API_KEY=dotenv-secret\n", encoding="utf-8")

    value = get_env_value(
        "OPENROUTER_API_KEY",
        load_dotenv=True,
        dotenv_path=env_file,
        environ={"OPENROUTER_API_KEY": "process-secret"},
    )

    assert value == "process-secret"


def test_empty_env_var_keeps_default():
    cfg = _build(environ={"TRADINGAGENTS_LLM_PROVIDER": ""})
    assert cfg["llm_provider"] == "openai"


def test_empty_env_var_keeps_none_default():
    cfg = _build(environ={"TRADINGAGENTS_DEEP_THINK_LLM_PROVIDER": ""})
    assert cfg["deep_think_llm_provider"] is None


def test_tool_vendor_overrides_are_opt_in_by_default():
    cfg = _build()
    assert "get_gold_price" not in cfg["tool_vendors"]
    assert "get_oil_prices" not in cfg["tool_vendors"]
    assert "get_bitcoin_price" not in cfg["tool_vendors"]
    assert "get_gap_candidates" not in cfg["tool_vendors"]
    assert "get_insider_transactions" not in cfg["tool_vendors"]


def test_tool_vendor_override_only_when_explicitly_set():
    cfg = _build(
        environ={
            "TRADINGAGENTS_VENDOR_GAP_CANDIDATES": "finviz",
            "TRADINGAGENTS_VENDOR_INSIDER_TRANSACTIONS": "finnhub",
            "TRADINGAGENTS_VENDOR_GOLD_PRICE": "alpha_vantage",
        }
    )
    assert cfg["tool_vendors"]["get_gap_candidates"] == "finviz"
    assert cfg["tool_vendors"]["get_insider_transactions"] == "finnhub"
    assert cfg["tool_vendors"]["get_gold_price"] == "alpha_vantage"
