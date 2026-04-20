"""Output parser that validates LLM responses against Pydantic schemas."""

import json
import logging
import re
from collections.abc import Callable
from typing import Any, TypeVar

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)

_RETRY_PROMPT = (
    "Your previous response could not be parsed. Error:\n{error}\n\n"
    "Please respond ONLY with valid JSON matching this schema:\n{instructions}\n\n"
    "Previous (invalid) response:\n{previous}"
)

MAX_RETRIES = 2


class StructuredOutputParser:
    """Validates LLM text output against a Pydantic model.

    Usage:
        parser = StructuredOutputParser(AnalystReport)
        instructions = parser.get_format_instructions()  # inject into prompt
        result = parser.parse(llm_response_text)          # returns AnalystReport or raises

    With retry:
        result = parser.parse_with_retry(llm_response_text, llm_caller)
    """

    def __init__(self, schema: type[T]) -> None:
        self.schema = schema
        self._langchain_parser = PydanticOutputParser(pydantic_object=schema)

    def get_format_instructions(self) -> str:
        """Return formatting instructions to embed in the LLM prompt."""
        return self._langchain_parser.get_format_instructions()

    def parse(self, text: str) -> T:
        """Parse LLM text into the Pydantic model.

        Tries JSON extraction first, then falls back to langchain parser.

        Raises:
            ValidationError: If the output doesn't match the schema.
        """
        # Try to extract JSON from markdown code fences or raw JSON
        json_str = self._extract_json(text)
        if json_str is not None:
            try:
                data = json.loads(json_str)
                return self.schema.model_validate(data)
            except (json.JSONDecodeError, ValidationError):
                pass

        # Fallback: let langchain parser try
        try:
            return self._langchain_parser.parse(text)
        except Exception as e:
            # Re-raise as ValidationError for consistent handling
            raise ValidationError.from_exception_data(
                title=self.schema.__name__,
                line_errors=[
                    {
                        "type": "value_error",
                        "loc": (),
                        "msg": f"Failed to parse LLM output: {e}",
                        "input": text[:500],
                        "ctx": {"error": str(e)},
                    }
                ],
            ) from e

    def parse_with_retry(
        self,
        text: str,
        llm_caller: Callable[[str], str],
        max_retries: int = MAX_RETRIES,
    ) -> T:
        """Parse with automatic retry on validation failure.

        On failure, sends the error and format instructions back to the LLM
        via *llm_caller* (a callable that accepts a prompt string and returns
        the LLM's text response).

        Args:
            text: Initial LLM response text to parse.
            llm_caller: ``fn(prompt) -> response_text`` used for retries.
            max_retries: Maximum number of retry attempts (default 2).

        Returns:
            Validated Pydantic model instance.

        Raises:
            ValidationError: If all retries are exhausted.
        """
        last_error: Exception | None = None
        current_text = text

        for attempt in range(1 + max_retries):
            try:
                return self.parse(current_text)
            except (ValidationError, Exception) as exc:
                last_error = exc
                if attempt < max_retries:
                    logger.warning(
                        "Validation failed for %s (attempt %d/%d): %s",
                        self.schema.__name__,
                        attempt + 1,
                        1 + max_retries,
                        exc,
                    )
                    retry_prompt = _RETRY_PROMPT.format(
                        error=str(exc),
                        instructions=self.get_format_instructions(),
                        previous=current_text[:1000],
                    )
                    current_text = llm_caller(retry_prompt)

        # All retries exhausted — raise the last error
        raise last_error  # type: ignore[misc]

    @staticmethod
    def _extract_json(text: str) -> str | None:
        """Extract JSON from markdown code fences or find raw JSON object."""
        # Match ```json ... ``` or ``` ... ```
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Try to find a raw JSON object (non-greedy to avoid spanning multiple blocks)
        match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text)
        if match:
            return match.group(0)

        return None


def validate_agent_output(
    text: str,
    schema: type[T],
    llm: Any | None = None,
) -> tuple[T | None, dict]:
    """Validate agent output against a schema, with optional LLM retry.

    Returns (model_instance, extracted_fields) on success,
    or (None, {}) on failure (graceful degradation).
    """
    from tradingagents.agents.schemas import extract_fields

    parser = StructuredOutputParser(schema)

    def _llm_caller(prompt: str) -> str:
        return llm.invoke(prompt).content

    try:
        if llm is not None:
            model = parser.parse_with_retry(text, _llm_caller)
        else:
            model = parser.parse(text)
        return model, extract_fields(model)
    except Exception:
        logger.warning("Schema validation failed for %s, passing raw text through", schema.__name__)
        return None, {}
