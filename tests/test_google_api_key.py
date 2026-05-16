import unittest
from unittest.mock import patch

import pytest

from tradingagents.llm_clients.google_client import (
    GoogleClient,
    _extract_retry_delay_seconds,
    _invoke_with_quota_retry,
    _is_resource_exhausted_error,
)


@pytest.mark.unit
class TestGoogleApiKeyStandardization(unittest.TestCase):
    """Verify GoogleClient accepts unified api_key parameter."""

    @patch("tradingagents.llm_clients.google_client.NormalizedChatGoogleGenerativeAI")
    def test_api_key_handling(self, mock_chat):
        test_cases = [
            ("unified api_key is mapped", {"api_key": "test-key-123"}, "test-key-123"),
            ("legacy google_api_key still works", {"google_api_key": "legacy-key-456"}, "legacy-key-456"),
            ("unified api_key takes precedence", {"api_key": "unified", "google_api_key": "legacy"}, "unified"),
        ]

        for msg, kwargs, expected_key in test_cases:
            with self.subTest(msg=msg):
                mock_chat.reset_mock()
                client = GoogleClient("gemini-2.5-flash", **kwargs)
                client.get_llm()
                call_kwargs = mock_chat.call_args[1]
                self.assertEqual(call_kwargs.get("google_api_key"), expected_key)


@pytest.mark.unit
def test_google_quota_retry_honors_retry_delay(monkeypatch):
    error = Exception(
        "429 RESOURCE_EXHAUSTED. {'error': {'status': 'RESOURCE_EXHAUSTED', "
        "'details': [{'@type': 'type.googleapis.com/google.rpc.RetryInfo', "
        "'retryDelay': '4s'}]}}"
    )
    attempts = {"count": 0}
    sleeps = []

    monkeypatch.setenv("TRADINGAGENTS_GOOGLE_QUOTA_MAX_RETRIES", "1")
    monkeypatch.setattr("tradingagents.llm_clients.google_client.random.uniform", lambda *_: 0)
    monkeypatch.setattr("tradingagents.llm_clients.google_client.time.sleep", sleeps.append)

    def operation():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise error
        return "ok"

    assert _is_resource_exhausted_error(error)
    assert _extract_retry_delay_seconds(error) == 4
    assert _invoke_with_quota_retry(operation) == "ok"
    assert sleeps == [4]
    assert attempts["count"] == 2


if __name__ == "__main__":
    unittest.main()
