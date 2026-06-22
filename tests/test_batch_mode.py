from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from tradingagents.batch.adapters import AnthropicBatchAdapter, OpenAIBatchAdapter
from tradingagents.batch.runner import BatchRunner
from tradingagents.default_config import DEFAULT_CONFIG


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


def test_anthropic_adapter_preserves_cache_markers(tmp_path, monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_ANTHROPIC_CACHE", raising=False)
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


def test_runner_replays_result_and_advances_to_next_node(tmp_path, monkeypatch):
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
                "content": [{"type": "output_text", "text": "Market report."}],
            }
        ],
        "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
    }
    runner.collect()

    run = runner.manifest.runs["AAPL"]
    assert run.progress["phase"] == "debate"
    assert run.progress["active_node"] == "Bull Researcher"
    assert run.decoded_state()["market_report"] == "Market report."
    nodes = [request.node for request in runner.manifest.requests.values()]
    assert nodes == ["Market Analyst", "Bull Researcher"]
