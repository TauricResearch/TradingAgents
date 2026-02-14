"""
Claude Max LLM Wrapper.

This module provides a LangChain-compatible LLM that uses the Claude CLI
with Max subscription authentication instead of API keys.
"""

import os
import subprocess
import json
import re
import copy
from typing import Any, Dict, List, Optional, Iterator, Sequence, Union

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.tools import BaseTool
from langchain_core.runnables import Runnable


class ClaudeMaxLLM(BaseChatModel):
    """
    A LangChain-compatible chat model that uses Claude CLI with Max subscription.

    This bypasses API key requirements by using the Claude CLI which authenticates
    via OAuth tokens from your Claude Max subscription.
    """

    model: str = "sonnet"  # Use alias for Claude Max subscription
    max_tokens: int = 4096
    temperature: float = 0.2
    claude_cli_path: str = "claude"
    tools: List[Any] = []  # Bound tools

    class Config:
        arbitrary_types_allowed = True

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

    def bind_tools(
        self,
        tools: Sequence[Union[Dict[str, Any], BaseTool, Any]],
        **kwargs: Any,
    ) -> "ClaudeMaxLLM":
        """Bind tools to the model for function calling.

        Args:
            tools: A list of tools to bind to the model.
            **kwargs: Additional arguments (ignored for compatibility).

        Returns:
            A new ClaudeMaxLLM instance with tools bound.
        """
        # Create a copy with tools bound
        new_instance = ClaudeMaxLLM(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            claude_cli_path=self.claude_cli_path,
            tools=list(tools),
        )
        return new_instance

    def _format_tools_for_prompt(self) -> str:
        """Format bound tools as a string for the prompt."""
        if not self.tools:
            return ""

        tool_descriptions = []
        for tool in self.tools:
            if hasattr(tool, 'name') and hasattr(tool, 'description'):
                # LangChain BaseTool
                name = tool.name
                desc = tool.description
                args = ""
                if hasattr(tool, 'args_schema') and tool.args_schema:
                    schema = tool.args_schema.schema() if hasattr(tool.args_schema, 'schema') else {}
                    if 'properties' in schema:
                        args = ", ".join(f"{k}: {v.get('type', 'any')}" for k, v in schema['properties'].items())
                tool_descriptions.append(f"- {name}({args}): {desc}")
            elif isinstance(tool, dict):
                # Dict format
                name = tool.get('name', 'unknown')
                desc = tool.get('description', '')
                tool_descriptions.append(f"- {name}: {desc}")
            else:
                # Try to get function info
                name = getattr(tool, '__name__', str(tool))
                desc = getattr(tool, '__doc__', '') or ''
                tool_descriptions.append(f"- {name}: {desc[:100]}")

        return "\n\nAvailable tools:\n" + "\n".join(tool_descriptions) + "\n\nTo use a tool, respond with: TOOL_CALL: tool_name(arguments)\n"

    def _format_messages_for_prompt(self, messages: List[BaseMessage]) -> tuple:
        """Convert LangChain messages to a system prompt and user prompt.

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        system_parts = []
        user_parts = []

        # Add tools description if tools are bound
        tools_prompt = self._format_tools_for_prompt()
        if tools_prompt:
            system_parts.append(tools_prompt)

        for msg in messages:
            # Handle dict messages (LangChain sometimes passes these)
            if isinstance(msg, dict):
                role = msg.get("role", msg.get("type", "human"))
                content = msg.get("content", str(msg))
                if role in ("system",):
                    system_parts.append(content)
                elif role in ("human", "user"):
                    user_parts.append(content)
                elif role in ("ai", "assistant"):
                    user_parts.append(f"Previous response: {content}")
                else:
                    user_parts.append(content)
            elif isinstance(msg, SystemMessage):
                system_parts.append(msg.content)
            elif isinstance(msg, HumanMessage):
                user_parts.append(msg.content)
            elif isinstance(msg, AIMessage):
                user_parts.append(f"Previous response: {msg.content}")
            elif isinstance(msg, ToolMessage):
                user_parts.append(f"Tool Result ({msg.name}): {msg.content}")
            elif hasattr(msg, 'content'):
                user_parts.append(msg.content)
            else:
                user_parts.append(str(msg))

        system_prompt = "\n\n".join(system_parts) if system_parts else ""
        user_prompt = "\n\n".join(user_parts) if user_parts else ""

        return system_prompt, user_prompt

    def _call_claude_cli(self, system_prompt: str, user_prompt: str) -> str:
        """Call the Claude CLI and return the response.

        Args:
            system_prompt: The system prompt to use (overrides Claude Code defaults)
            user_prompt: The user prompt/query
        """
        # Create environment without ANTHROPIC_API_KEY to force subscription auth
        # Also remove CLAUDECODE to allow nested CLI calls from within Claude Code sessions
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("CLAUDECODE", None)

        # Build the command with --system-prompt to override Claude Code's default behavior
        cmd = [
            self.claude_cli_path,
            "--print",  # Non-interactive mode
            "--model", self.model,
            "--tools", "",  # Disable all Claude Code tools - we're just doing analysis
        ]

        # Add system prompt if provided (this overrides Claude Code's default system prompt)
        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])

        # Add the user prompt
        cmd.extend(["-p", user_prompt])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode != 0:
                # Include both stdout and stderr for better debugging
                error_info = result.stderr or result.stdout or "No output"
                raise RuntimeError(f"Claude CLI error (code {result.returncode}): {error_info}")

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
        system_prompt, user_prompt = self._format_messages_for_prompt(messages)
        response_text = self._call_claude_cli(system_prompt, user_prompt)

        # Apply stop sequences if provided
        if stop:
            for stop_seq in stop:
                if stop_seq in response_text:
                    response_text = response_text.split(stop_seq)[0]

        message = AIMessage(content=response_text)
        generation = ChatGeneration(message=message)

        return ChatResult(generations=[generation])

    def invoke(
        self,
        input: Any,
        config: Optional[Dict[str, Any]] = None,
        *,
        stop: Optional[List[str]] = None,
        **kwargs: Any
    ) -> AIMessage:
        """Invoke the model with the given input."""
        if isinstance(input, str):
            messages = [HumanMessage(content=input)]
        elif isinstance(input, list):
            messages = input
        else:
            messages = [HumanMessage(content=str(input))]

        result = self._generate(messages, stop=stop, **kwargs)
        return result.generations[0].message


def get_claude_max_llm(model: str = "sonnet", **kwargs) -> ClaudeMaxLLM:
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

    llm = ClaudeMaxLLM(model="sonnet")

    # Test with a simple prompt
    response = llm.invoke("Say 'Hello, I am using Claude Max subscription!' in exactly those words.")
    print(f"Response: {response.content}")

    return response


if __name__ == "__main__":
    test_claude_max()
