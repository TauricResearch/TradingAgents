import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage
import pytest

from tradingagents.llm_clients.openai_client import OpenAIClient
from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI


@pytest.mark.unit
class TestOpenAICompatibleProviderConfig(unittest.TestCase):
    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_explicit_base_url_overrides_provider_default(self, mock_chat):
        client = OpenAIClient(
            "qwen-plus",
            base_url="https://custom.example/v1",
            provider="qwen",
        )

        client.get_llm()

        call_kwargs = mock_chat.call_args[1]
        self.assertEqual(call_kwargs["base_url"], "https://custom.example/v1")
        self.assertEqual(call_kwargs["api_key"], "placeholder")

    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_qwen_default_base_url_matches_cli_provider_url(self, mock_chat):
        client = OpenAIClient("qwen-plus", provider="qwen")

        client.get_llm()

        call_kwargs = mock_chat.call_args[1]
        self.assertEqual(
            call_kwargs["base_url"],
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

    def test_missing_provider_api_key_fails_before_sdk_call(self):
        with patch.dict("os.environ", {"DASHSCOPE_API_KEY": ""}):
            client = OpenAIClient("qwen-plus", provider="qwen")

            with self.assertRaisesRegex(ValueError, "Missing DASHSCOPE_API_KEY"):
                client.get_llm()

    def test_reasoning_content_is_preserved_from_openai_compatible_responses(self):
        llm = NormalizedChatOpenAI(model="deepseek-reasoner", api_key="test")
        result = llm._create_chat_result(
            {
                "model": "deepseek-reasoner",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Need a tool.",
                            "reasoning_content": "Private reasoning that DeepSeek requires.",
                            "tool_calls": [],
                        },
                        "finish_reason": "stop",
                    }
                ],
            }
        )

        message = result.generations[0].message
        self.assertEqual(
            message.additional_kwargs["reasoning_content"],
            "Private reasoning that DeepSeek requires.",
        )

    def test_reasoning_content_is_passed_back_with_assistant_history(self):
        llm = NormalizedChatOpenAI(model="deepseek-reasoner", api_key="test")
        message = AIMessage(
            content="Need a tool.",
            additional_kwargs={
                "reasoning_content": "Private reasoning that DeepSeek requires."
            },
        )

        payload = llm._get_request_payload([message])

        self.assertEqual(
            payload["messages"][0]["reasoning_content"],
            "Private reasoning that DeepSeek requires.",
        )

    def test_deepseek_reasoner_skips_structured_output_tool_choice(self):
        llm = NormalizedChatOpenAI(model="deepseek-reasoner", api_key="test")

        with self.assertRaisesRegex(NotImplementedError, "deepseek-reasoner"):
            llm.with_structured_output(dict)


if __name__ == "__main__":
    unittest.main()
