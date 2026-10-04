from __future__ import annotations

import json

import pytest
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from tradingagents.batch.adapters import AnthropicBatchAdapter, OpenAIBatchAdapter
from tradingagents.batch.runner import BatchRunner
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.base_client import normalize_content


class FakeOpenAIAdapter(OpenAIBatchAdapter):
    def __init__(self, config):
        super().__init__(config)
        self.submitted = 0

    def submit_batch(self, *, model, lines, input_path):
        self.submitted += 1
        assert input_path.is_file()
        return f"fake_batch_{self.submitted}"

    def refresh_batch(self, batch_id):
        return {"status": "completed"}

    def download_results(self, *, batch_id, output_path, error_path):
        assert output_path.parent.is_dir()
        assert error_path.parent.is_dir()
        output_path.write_text("", encoding="utf-8")
        error_path.write_text("", encoding="utf-8")
        return {}


def _config(tmp_path):
    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "data_cache_dir": str(tmp_path / "cache"),
            "results_dir": str(tmp_path / "logs"),
            "reports_dir": str(tmp_path / "reports"),
            "llm_provider": "openai",
            "deep_think_llm": "gpt-5.5",
            "quick_think_llm": "gpt-5.4-mini",
            "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1,
        }
    )
    return config


@pytest.mark.parametrize("provider, tier, other_provider", [
    ("openai", "quick", "anthropic"),
    ("openai", "deep", "google"),
    ("anthropic", "quick", "openai"),
    ("anthropic", "deep", "OPENAI"),
])
def test_batch_rejects_a_different_tier_provider_before_setup(
    tmp_path, monkeypatch, provider, tier, other_provider,
):
    import tradingagents.batch.runner as runner_mod

    config = _config(tmp_path)
    config[f"{tier}_think_provider"] = other_provider

    def unexpected_setup(*a, **kw):
        pytest.fail("mixed-provider batch reached memory, network, or run-state setup")

    for operation in ("TradingMemoryLog", "resolve_instrument_identity", "Propagator"):
        monkeypatch.setattr(runner_mod, operation, unexpected_setup)
    monkeypatch.setattr(runner_mod.BatchManifest, "new", unexpected_setup)

    with pytest.raises(ValueError, match=f"{tier} tier uses '{other_provider.lower()}'") as error:
        BatchRunner.create(
            provider=provider, tickers=["AAPL"], trade_date="2026-09-01",
            asset_types={"AAPL": "stock"}, selected_analysts=["market"],
            config=config, root=tmp_path / "batch",
        )

    assert "synchronous runs" in str(error.value)
    assert not any(tmp_path.iterdir())


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("endpoint_choice", ["unset", "empty", "native", "native-slash"])
def test_batch_allows_explicit_tiers_using_its_own_provider(tmp_path, monkeypatch, provider, endpoint_choice):
    import tradingagents.batch.runner as runner_mod

    monkeypatch.setattr(runner_mod, "resolve_instrument_identity", lambda ticker: {})
    config = _config(tmp_path)
    native_endpoint = "https://api.openai.com/v1" if provider == "openai" else "https://api.anthropic.com"
    endpoint = {"unset": None, "empty": "", "native": native_endpoint,
                "native-slash": native_endpoint + "/"}[endpoint_choice]
    config.update(quick_think_provider=provider.upper(), deep_think_provider=provider,
                  quick_think_backend_url=endpoint, deep_think_backend_url=endpoint,
                  memory_log_path=str(tmp_path / "memory.md"))

    runner = BatchRunner.create(
        provider=provider.upper(), tickers=["AAPL"], trade_date="2026-09-01",
        asset_types={"AAPL": "stock"}, selected_analysts=["market"],
        config=config, root=tmp_path / "batch",
    )

    assert runner.provider == provider
    assert runner.quick_llm.provider == runner.deep_llm.provider == provider


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("tier", ["quick", "deep"])
def test_batch_rejects_custom_tier_endpoints_before_setup_without_exposing_the_url(
    tmp_path, monkeypatch, provider, tier,
):
    import tradingagents.batch.runner as runner_mod

    endpoint = "https://fixture-user:fixture-password@proxy.example.invalid/v1?key=fixture-key"
    config = _config(tmp_path)
    config[f"{tier}_think_backend_url"] = endpoint

    def unexpected_setup(*a, **kw):
        pytest.fail("custom-endpoint batch reached memory, network, or run-state setup")

    for operation in ("TradingMemoryLog", "resolve_instrument_identity", "Propagator"):
        monkeypatch.setattr(runner_mod, operation, unexpected_setup)
    monkeypatch.setattr(runner_mod.BatchManifest, "new", unexpected_setup)

    with pytest.raises(ValueError, match=f"custom {tier} tier endpoint") as error:
        BatchRunner.create(
            provider=provider, tickers=["AAPL"], trade_date="2026-09-01",
            asset_types={"AAPL": "stock"}, selected_analysts=["market"],
            config=config, root=tmp_path / "batch",
        )

    message = str(error.value)
    assert "synchronous runs" in message
    assert "https://" not in message
    assert "fixture-" not in message
    assert not any(tmp_path.iterdir())


def test_openai_adapter_builds_responses_batch_line(tmp_path):
    adapter = OpenAIBatchAdapter(_config(tmp_path))
    payload = adapter.build_payload(
        model="gpt-5.4-mini",
        messages=[SystemMessage("system"), HumanMessage("hello")],
        request_kwargs={},
    )
    line = adapter.line_for_request("request_1", payload)
    assert line["url"] == "/v1/responses"
    assert line["method"] == "POST"
    assert line["body"]["model"] == "gpt-5.4-mini"
    assert "input" in line["body"]
    assert "stream" not in line["body"]


def test_anthropic_adapter_preserves_cache_markers(tmp_path):
    config = _config(tmp_path)
    config["llm_provider"] = "anthropic"
    adapter = AnthropicBatchAdapter(config)
    payload = adapter.build_payload(
        model="claude-sonnet-4-6",
        messages=[SystemMessage("system"), HumanMessage("hello")],
        request_kwargs={},
    )
    line = adapter.line_for_request("request_1", payload)
    assert line["params"]["model"] == "claude-sonnet-4-6"
    assert line["params"]["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert line["params"]["messages"][-1]["content"][0]["cache_control"] == {
        "type": "ephemeral"
    }


def test_anthropic_batch_tool_followup_preserves_signed_thinking(tmp_path):
    config = _config(tmp_path)
    config["llm_provider"] = "anthropic"
    config["max_tokens"] = 1024
    adapter = AnthropicBatchAdapter(config)
    thinking = {"type": "thinking", "thinking": "native reasoning", "signature": "signed_fixture"}
    response = adapter.message_from_response({"content": [
        thinking, {"type": "tool_use", "id": "call1", "name": "lookup", "input": {}},
    ]})
    payload = adapter.build_payload(
        model="claude-sonnet-5-5",
        messages=[HumanMessage("Use verified evidence."), normalize_content(response),
                  ToolMessage(content="Verified evidence", tool_call_id="call1")],
        request_kwargs={},
    )
    assistant = payload["messages"][1]["content"]
    assert assistant[0] == thinking
    assert assistant[1]["type"] == "tool_use"
    assert assistant[1]["id"] == "call1"


def test_openai_adapter_extracts_structured_function_arguments(tmp_path):
    adapter = OpenAIBatchAdapter(_config(tmp_path))
    args = adapter.structured_args_from_response(
        {
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "Pick",
                    "arguments": '{"rating":"Buy"}',
                }
            ]
        }
    )
    assert args == {"rating": "Buy"}


def test_anthropic_adapter_extracts_structured_tool_use(tmp_path):
    adapter = AnthropicBatchAdapter(_config(tmp_path))
    args = adapter.structured_args_from_response(
        {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "Pick",
                    "input": {"rating": "Hold"},
                }
            ]
        }
    )
    assert args == {"rating": "Hold"}


def test_runner_submits_first_deferred_request(tmp_path, monkeypatch):
    import tradingagents.batch.runner as runner_mod

    monkeypatch.setattr(runner_mod, "resolve_instrument_identity", lambda ticker: {})
    config = _config(tmp_path)
    runner = BatchRunner.create(
        provider="openai",
        tickers=["AAPL"],
        trade_date="2026-06-19",
        asset_types={"AAPL": "stock"},
        selected_analysts=["market"],
        config=config,
        root=tmp_path / "batch",
    )
    adapter = FakeOpenAIAdapter(config)
    runner.adapter = adapter
    runner.context.adapter = adapter

    manifest_path = runner.submit()

    assert manifest_path.is_file()
    assert runner.manifest.runs["AAPL"].status == "waiting"
    assert len(runner.manifest.requests) == 1
    request = next(iter(runner.manifest.requests.values()))
    assert request.node == "Market Analyst"
    assert request.status == "submitted"
    assert request.provider_batch_id == "fake_batch_1"


@pytest.mark.parametrize("market_text", ["Market report.", ""])
def test_runner_replays_result_and_advances_to_next_node(tmp_path, monkeypatch, market_text):
    import tradingagents.batch.runner as runner_mod

    monkeypatch.setattr(runner_mod, "resolve_instrument_identity", lambda ticker: {})
    config = _config(tmp_path)
    runner = BatchRunner.create(
        provider="openai",
        tickers=["AAPL"],
        trade_date="2026-06-19",
        asset_types={"AAPL": "stock"},
        selected_analysts=["market"],
        config=config,
        root=tmp_path / "batch",
    )
    adapter = FakeOpenAIAdapter(config)
    runner.adapter = adapter
    runner.context.adapter = adapter
    runner.submit()

    request = next(iter(runner.manifest.requests.values()))
    request.status = "succeeded"
    request.response = {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": market_text}],
            }
        ],
        "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
    }
    runner.collect()

    run = runner.manifest.runs["AAPL"]
    if not market_text:
        assert run.status == "failed"
        assert "empty response" in run.error
        assert not run.decoded_state()["market_report"]
        assert len(runner.manifest.requests) == 1
        assert not runner.memory_log.load_entries()
        return
    assert run.progress["phase"] == "debate"
    assert run.progress["active_node"] == "Bull Researcher"
    assert run.decoded_state()["market_report"] == "Market report."
    nodes = [request.node for request in runner.manifest.requests.values()]
    assert nodes == ["Market Analyst", "Bull Researcher"]


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("corrected", [True, False])
def test_pm_target_correction_survives_batch_replay(tmp_path, monkeypatch, provider, corrected):
    import tradingagents.batch.runner as runner_mod

    monkeypatch.setattr(runner_mod, "resolve_instrument_identity", lambda ticker: {})
    config = _config(tmp_path)
    config.update(llm_provider=provider, memory_log_path=str(tmp_path / "memory.md"))
    runner = BatchRunner.create(
        provider=provider, tickers=["AAPL"], trade_date="2026-10-01",
        asset_types={"AAPL": "stock"}, selected_analysts=["market"],
        config=config, root=tmp_path / "batch",
    )
    run = runner.manifest.runs["AAPL"]
    state = run.decoded_state()
    state.update(market_report="Verified resistance objective: 120.",
                 fundamentals_report="Valuation: 6 EPS times 20 multiple supports 120.",
                 investment_plan="Hold.", trader_investment_plan="Action: Hold")
    run.set_state(state)
    run.progress["phase"] = "portfolio_manager"
    runner.advance_all()
    first = next(iter(runner.manifest.requests.values()))
    assert first.kind == "structured"
    missing = {"rating": "Hold", "executive_summary": "Retain current position.",
               "investment_thesis": "Balanced evidence.", "price_target": None}
    first.status = "succeeded"
    first.response = (
        {"output": [{"type": "function_call", "call_id": "pm", "name": "PortfolioDecision",
                     "arguments": json.dumps(missing)}]} if provider == "openai" else
        {"content": [{"type": "tool_use", "id": "pm", "name": "PortfolioDecision", "input": missing}]}
    )
    runner.advance_all()
    assert run.status == "waiting"
    assert len(runner.manifest.requests) == 2
    # Resume while the correction is still pending: do not enqueue a third call.
    runner.advance_all()
    assert len(runner.manifest.requests) == 2
    second = list(runner.manifest.requests.values())[1]
    assert second.kind == "message"
    text = "Rating: Hold\nInvestment Thesis: EPS 6 times multiple 20 supports 120.\nPrice Target: "
    text += "120" if corrected else "not provided"
    second.status = "succeeded"
    second.response = (
        {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}
        if provider == "openai" else {"content": [{"type": "text", "text": text}]}
    )
    runner.advance_all()
    assert run.status == ("completed" if corrected else "failed")
    assert len(runner.manifest.requests) == 2
    if not corrected:
        assert "numeric Price Target" in run.error
        assert not runner.memory_log.load_entries()
