"""Regression test for the gateway-overload retry layer.

A saturated inference gateway (e.g. a local proxy at 127.0.0.1:15721) can
return HTTP 529 "Overloaded" for long enough to exhaust the OpenAI SDK's
built-in retries and surface "Service was busy" to the user. The
``NormalizedChat*`` subclasses wrap ``_generate``/``_agenerate`` with a
tenacity exponential backoff that rides out these transient errors so the
user never has to manually click "try again".

These tests pin that behavior: a 529 is retried until it succeeds, a 400
fails immediately without wasting a backoff, and the retry covers the
``bind_tools`` call path too (not just bare ``invoke``).
"""

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI


def _overloaded_529():
    req = httpx.Request("POST", "http://127.0.0.1:15721/v1/chat/completions")
    from openai import InternalServerError

    return InternalServerError("Overloaded", response=httpx.Response(529, request=req), body=None)


def _ok_result(text="ok"):
    return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


@pytest.fixture()
def _fast_retry(monkeypatch):
    """Keep the retry fast: 3 attempts, 1s cap, so the test is sub-second."""
    monkeypatch.setenv("TRADINGAGENTS_LLM_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("TRADINGAGENTS_LLM_RETRY_MAX_WAIT", "1.0")
    yield


@pytest.fixture()
def _patched_generate(monkeypatch):
    """Replace ChatOpenAI._generate with a scriptable stub.

    Returns a dict whose ``script`` list is consumed left-to-right: exceptions
    are raised, anything else is returned as a ChatResult. Lets each test
    declare the exact failure sequence the gateway would produce.
    """
    state = {"script": [], "calls": 0}

    def fake_generate(self, messages, stop=None, run_manager=None, **kwargs):
        state["calls"] += 1
        if state["script"]:
            item = state["script"].pop(0)
            if isinstance(item, BaseException):
                raise item
            return item
        return _ok_result()

    monkeypatch.setattr(ChatOpenAI, "_generate", fake_generate)
    return state


@pytest.mark.unit
def test_529_is_retried_until_success(_fast_retry, _patched_generate):
    _patched_generate["script"] = [_overloaded_529(), _overloaded_529(), _ok_result("recovered")]

    llm = NormalizedChatOpenAI(model="gpt-4o-mini", api_key="dummy")
    result = llm.invoke([HumanMessage(content="hi")])

    assert result.content == "recovered"
    assert _patched_generate["calls"] == 3  # two failures + one success


@pytest.mark.unit
def test_persistent_529_reraises_after_max_attempts(_fast_retry, _patched_generate):
    # Every call overloads — the retry layer must give up after the cap and
    # re-raise so the error is visible, not silently swallowed.
    _patched_generate["script"] = [_overloaded_529() for _ in range(10)]

    from openai import InternalServerError

    llm = NormalizedChatOpenAI(model="gpt-4o-mini", api_key="dummy")
    with pytest.raises(InternalServerError):
        llm.invoke([HumanMessage(content="hi")])
    assert _patched_generate["calls"] == 3  # TRADINGAGENTS_LLM_MAX_ATTEMPTS


@pytest.mark.unit
def test_non_transient_400_fails_immediately(_fast_retry, _patched_generate):
    from openai import BadRequestError

    req = httpx.Request("POST", "http://127.0.0.1:15721/v1/chat/completions")
    _patched_generate["script"] = [
        BadRequestError("bad request", response=httpx.Response(400, request=req), body=None),
        _ok_result("should-not-reach"),
    ]

    llm = NormalizedChatOpenAI(model="gpt-4o-mini", api_key="dummy")
    with pytest.raises(BadRequestError):
        llm.invoke([HumanMessage(content="hi")])
    assert _patched_generate["calls"] == 1  # no retry on a 400


@pytest.mark.unit
def test_bind_tools_path_also_retries(_fast_retry, _patched_generate):
    # The analysts build `prompt | llm.bind_tools(tools)` pipelines. That path
    # must also be covered by the retry layer, not just bare invoke.
    _patched_generate["script"] = [_overloaded_529(), _ok_result("ok")]

    llm = NormalizedChatOpenAI(model="gpt-4o-mini", api_key="dummy")
    bound = llm.bind_tools([])
    result = bound.invoke([HumanMessage(content="hi")])

    assert result.content == "ok"
    assert _patched_generate["calls"] == 2
