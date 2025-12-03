"""
Utilities for working with structured LLM outputs.

Provides helper functions to easily configure LLMs for structured output
across different providers (OpenAI, Anthropic, Google).
"""

from typing import Type, Any, Dict
from pydantic import BaseModel


def get_structured_llm(llm: Any, schema: Type[BaseModel]):
    """
    Configure an LLM to return structured output based on a Pydantic schema.
    
    Args:
        llm: The LangChain LLM instance
        schema: Pydantic BaseModel class defining the expected output structure
        
    Returns:
        Configured LLM that returns structured output
        
    Example:
        ```python
        from tradingagents.schemas import TradeDecision
        from tradingagents.utils.structured_output import get_structured_llm
        
        structured_llm = get_structured_llm(llm, TradeDecision)
        response = structured_llm.invoke("Should I buy AAPL?")
        # response is a dict matching TradeDecision schema
        ```
    """
    return llm.with_structured_output(
        schema=schema.model_json_schema(),
        method="json_schema"
    )


def extract_structured_response(response: Dict[str, Any], schema: Type[BaseModel]) -> BaseModel:
    """
    Validate and parse a structured response into a Pydantic model.
    
    Args:
        response: Dictionary response from structured LLM
        schema: Pydantic BaseModel class to validate against
        
    Returns:
        Validated Pydantic model instance
        
    Raises:
        ValidationError: If response doesn't match schema
    """
    return schema(**response)
