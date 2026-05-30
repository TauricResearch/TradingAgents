"""Test dello shim che tollera response.completed senza 'output' (backend Codex)."""
import langchain_openai.chat_models.base as lc_base

from tradingagents.llm_clients import openai_client


def test_shim_coerces_none_output(monkeypatch):
    received = {}

    def spy(response, *args, **kwargs):
        received["output"] = response.output
        return "RESULT"

    monkeypatch.setattr(lc_base, "_construct_lc_result_from_responses_api", spy)
    openai_client._install_codex_responses_output_shim()

    class FakeResp:
        output = None

    out = lc_base._construct_lc_result_from_responses_api(FakeResp())
    assert out == "RESULT"
    assert received["output"] == []  # None coerciato a lista vuota


def test_shim_passes_through_normal_output(monkeypatch):
    received = {}

    def spy(response, *args, **kwargs):
        received["output"] = response.output
        return "RESULT"

    monkeypatch.setattr(lc_base, "_construct_lc_result_from_responses_api", spy)
    openai_client._install_codex_responses_output_shim()

    class FakeResp:
        output = ["item"]

    lc_base._construct_lc_result_from_responses_api(FakeResp())
    assert received["output"] == ["item"]  # invariato


def test_shim_is_idempotent(monkeypatch):
    def spy(response, *args, **kwargs):
        return "X"

    monkeypatch.setattr(lc_base, "_construct_lc_result_from_responses_api", spy)
    openai_client._install_codex_responses_output_shim()
    first = lc_base._construct_lc_result_from_responses_api
    openai_client._install_codex_responses_output_shim()
    second = lc_base._construct_lc_result_from_responses_api
    assert first is second  # non ri-wrappa
