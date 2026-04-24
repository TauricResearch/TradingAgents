import contextvars

from tradingagents.agents.utils.llm_guard import invoke_with_timeout

_TRACE_ID = contextvars.ContextVar("trace_id", default=None)


class _ContextAwareLLM:
    def invoke(self, _input, config=None, **kwargs):
        return {"trace_id": _TRACE_ID.get()}


def test_invoke_with_timeout_propagates_contextvars():
    token = _TRACE_ID.set("run-ctx-123")
    try:
        result, error = invoke_with_timeout(
            llm=_ContextAwareLLM(),
            prompt_or_messages="ignored",
            timeout_seconds=5,
        )
    finally:
        _TRACE_ID.reset(token)

    assert error is None
    assert result["trace_id"] == "run-ctx-123"
