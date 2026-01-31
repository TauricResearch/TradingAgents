"""
Claude Max LLM Wrapper.

This module provides a LangChain-compatible LLM that uses the Claude CLI
with Max subscription authentication instead of API keys.
"""

import os
import subprocess
import json
from typing import Any, Dict, List, Optional, Iterator

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.callbacks import CallbackManagerForLLMRun


class ClaudeMaxLLM(BaseChatModel):
    """
    A LangChain-compatible chat model that uses Claude CLI with Max subscription.

    This bypasses API key requirements by using the Claude CLI which authenticates
    via OAuth tokens from your Claude Max subscription.
    """

    model: str = "sonnet"  # Use alias for Claude Max subscription
    max_tokens: int = 4096
    temperature: float = 0.7
    claude_cli_path: str = "claude"

    @property
    def _llm_type(self) -> str:
        return "claude-max"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

    def _format_messages_for_prompt(self, messages: List[BaseMessage]) -> str:
        """Convert LangChain messages to a single prompt string."""
        formatted_parts = []

        for msg in messages:
            if isinstance(msg, SystemMessage):
                formatted_parts.append(f"<system>\n{msg.content}\n</system>\n")
            elif isinstance(msg, HumanMessage):
                formatted_parts.append(f"Human: {msg.content}\n")
            elif isinstance(msg, AIMessage):
                formatted_parts.append(f"Assistant: {msg.content}\n")
            else:
                formatted_parts.append(f"{msg.content}\n")

        return "\n".join(formatted_parts)

    def _call_claude_cli(self, prompt: str) -> str:
        """Call the Claude CLI and return the response."""
        # Create environment without ANTHROPIC_API_KEY to force subscription auth
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)

        # Build the command
        cmd = [
            self.claude_cli_path,
            "--print",  # Non-interactive mode
            "--model", self.model,
            prompt
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode != 0:
                raise RuntimeError(f"Claude CLI error: {result.stderr}")

            return result.stdout.strip()

        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude CLI timed out after 5 minutes")
        except FileNotFoundError:
            raise RuntimeError(
                f"Claude CLI not found at '{self.claude_cli_path}'. "
                "Make sure Claude Code is installed and in your PATH."
            )

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate a response from the Claude CLI."""
        prompt = self._format_messages_for_prompt(messages)
        response_text = self._call_claude_cli(prompt)

        # Apply stop sequences if provided
        if stop:
            for stop_seq in stop:
                if stop_seq in response_text:
                    response_text = response_text.split(stop_seq)[0]

        message = AIMessage(content=response_text)
        generation = ChatGeneration(message=message)

        return ChatResult(generations=[generation])

    def invoke(self, input: Any, **kwargs) -> AIMessage:
        """Invoke the model with the given input."""
        if isinstance(input, str):
            messages = [HumanMessage(content=input)]
        elif isinstance(input, list):
            messages = input
        else:
            messages = [HumanMessage(content=str(input))]

        result = self._generate(messages, **kwargs)
        return result.generations[0].message


def get_claude_max_llm(model: str = "claude-sonnet-4-5-20250514", **kwargs) -> ClaudeMaxLLM:
    """
    Factory function to create a ClaudeMaxLLM instance.

    Args:
        model: The Claude model to use (default: claude-sonnet-4-5-20250514)
        **kwargs: Additional arguments passed to ClaudeMaxLLM

    Returns:
        A configured ClaudeMaxLLM instance
    """
    return ClaudeMaxLLM(model=model, **kwargs)


def test_claude_max():
    """Test the Claude Max LLM wrapper."""
    print("Testing Claude Max LLM wrapper...")

    llm = ClaudeMaxLLM(model="claude-sonnet-4-5-20250514")

    # Test with a simple prompt
    response = llm.invoke("Say 'Hello, I am using Claude Max subscription!' in exactly those words.")
    print(f"Response: {response.content}")

    return response


if __name__ == "__main__":
    test_claude_max()
