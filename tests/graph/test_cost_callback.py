import pytest
from langchain_core.outputs import LLMResult, Generation


@pytest.mark.unit
def test_callback_accumulates_tokens_per_model():
    from tradingagents.graph.cost_callback import RunCostCallback
    cb = RunCostCallback()
    result1 = LLMResult(
        generations=[[Generation(text="x")]],
        llm_output={"token_usage": {"prompt_tokens": 100, "completion_tokens": 50},
                    "model_name": "deepseek-v4-pro"},
    )
    result2 = LLMResult(
        generations=[[Generation(text="y")]],
        llm_output={"token_usage": {"prompt_tokens": 30, "completion_tokens": 20},
                    "model_name": "deepseek-v4-flash"},
    )
    cb.on_llm_end(result1)
    cb.on_llm_end(result2)
    cb.on_llm_end(result1)  # second call to deep model
    totals = cb.totals_by_model()
    assert totals["deepseek-v4-pro"] == {"in_tokens": 200, "out_tokens": 100}
    assert totals["deepseek-v4-flash"] == {"in_tokens": 30, "out_tokens": 20}


@pytest.mark.unit
def test_callback_handles_missing_token_usage():
    from tradingagents.graph.cost_callback import RunCostCallback
    cb = RunCostCallback()
    result = LLMResult(generations=[[Generation(text="x")]], llm_output={})
    cb.on_llm_end(result)  # must not raise
    assert cb.totals_by_model() == {}
