from types import SimpleNamespace
from unittest.mock import patch

import openai
import pytest

from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI


def _make_client(retries: int = 2) -> NormalizedChatOpenAI:
    client = object.__new__(NormalizedChatOpenAI)
    client._manual_retry_attempts = retries
    client._manual_retry_base_delay_s = 0.0
    return client


def test_invoke_retries_transient_network_disconnect():
    client = _make_client(retries=2)
    response = SimpleNamespace(content="ok")

    class FlakyInvoke:
        def __init__(self):
            self.calls = 0

        def __call__(self, _self, input, config=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise openai.APIConnectionError(request=None)
            return response

    flaky = FlakyInvoke()
    with patch("tradingagents.llm_clients.openai_client.ChatOpenAI.invoke", new=flaky):
        result = client.invoke(["hello"])

    assert result is response
    assert flaky.calls == 2


def test_invoke_does_not_retry_non_transient_api_error():
    client = _make_client(retries=2)
    error = openai.APIError("bad request", request=None, body=None)

    with patch(
        "tradingagents.llm_clients.openai_client.ChatOpenAI.invoke",
        side_effect=error,
    ) as mock_invoke:
        with pytest.raises(openai.APIError):
            client.invoke(["hello"])

    assert mock_invoke.call_count == 1
