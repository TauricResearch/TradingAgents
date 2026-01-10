"""
JSON Retry Loop - Enforce Schema Compliance

If LLM outputs text instead of JSON, retry with error message.
Max 2 retries before hard failure.
"""

from typing import Type, TypeVar, Optional, Callable
from pydantic import BaseModel, ValidationError
import json
import time

T = TypeVar('T', bound=BaseModel)


class JSONRetryLoop:
    """
    Enforce JSON schema compliance with retry mechanism.
    
    If LLM outputs invalid JSON or violates schema, retry with error feedback.
    """
    
    def __init__(self, max_retries: int = 2):
        """
        Initialize retry loop.
        
        Args:
            max_retries: Maximum retry attempts (default 2)
        """
        self.max_retries = max_retries
        self.retry_stats = {
            "total_calls": 0,
            "successful_first_try": 0,
            "successful_after_retry": 0,
            "total_failures": 0
        }
    
    def invoke_with_retry(
        self,
        llm_callable: Callable,
        schema: Type[T],
        prompt: str,
        context: dict
    ) -> tuple[Optional[T], dict]:
        """
        Invoke LLM with automatic retry on schema violation.
        
        Args:
            llm_callable: Function that calls LLM (e.g., llm.invoke)
            schema: Pydantic schema class
            prompt: Initial prompt
            context: Context dict for prompt formatting
        
        Returns:
            (parsed_output, metadata) where metadata contains retry info
        """
        self.retry_stats["total_calls"] += 1
        
        metadata = {
            "attempts": 0,
            "errors": [],
            "latency": 0.0
        }
        
        start_time = time.time()
        
        for attempt in range(self.max_retries + 1):
            metadata["attempts"] = attempt + 1
            
            try:
                # Invoke LLM
                if attempt == 0:
                    # First attempt: use original prompt
                    response = llm_callable(prompt.format(**context))
                else:
                    # Retry: add error feedback
                    retry_prompt = self._build_retry_prompt(
                        prompt, context, metadata["errors"][-1]
                    )
                    response = llm_callable(retry_prompt)
                
                # Extract JSON from response
                json_str = self._extract_json(response.content)
                
                # Parse JSON
                json_data = json.loads(json_str)
                
                # Validate against schema
                parsed_output = schema(**json_data)
                
                # Success!
                metadata["latency"] = time.time() - start_time
                
                if attempt == 0:
                    self.retry_stats["successful_first_try"] += 1
                else:
                    self.retry_stats["successful_after_retry"] += 1
                
                return parsed_output, metadata
                
            except json.JSONDecodeError as e:
                error_msg = f"Invalid JSON: {str(e)}"
                metadata["errors"].append(error_msg)
                
            except ValidationError as e:
                error_msg = f"Schema validation failed: {str(e)}"
                metadata["errors"].append(error_msg)
            
            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                metadata["errors"].append(error_msg)
        
        # All retries exhausted
        self.retry_stats["total_failures"] += 1
        metadata["latency"] = time.time() - start_time
        
        return None, metadata
    
    def _extract_json(self, text: str) -> str:
        """
        Extract JSON from LLM response.
        
        Handles cases where LLM wraps JSON in markdown code blocks.
        """
        # Remove markdown code blocks
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            return text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            return text[start:end].strip()
        
        # Try to find JSON object
        if "{" in text and "}" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            return text[start:end]
        
        return text.strip()
    
    def _build_retry_prompt(
        self,
        original_prompt: str,
        context: dict,
        error_msg: str
    ) -> str:
        """
        Build retry prompt with error feedback.
        
        Args:
            original_prompt: Original prompt template
            context: Context dict
            error_msg: Error message from previous attempt
        
        Returns:
            Retry prompt with error feedback
        """
        retry_instruction = f"""
CRITICAL ERROR: Your previous response failed validation.

ERROR: {error_msg}

You MUST output valid JSON matching the required schema. Do NOT output:
- Markdown explanations
- Text before or after JSON
- Invalid JSON syntax
- Missing required fields

Try again. Output ONLY valid JSON.

---

{original_prompt}
"""
        return retry_instruction.format(**context)
    
    def get_stats(self) -> dict:
        """Get retry statistics."""
        total = self.retry_stats["total_calls"]
        if total == 0:
            return self.retry_stats
        
        return {
            **self.retry_stats,
            "first_try_success_rate": self.retry_stats["successful_first_try"] / total,
            "overall_success_rate": (
                self.retry_stats["successful_first_try"] + 
                self.retry_stats["successful_after_retry"]
            ) / total,
            "failure_rate": self.retry_stats["total_failures"] / total
        }


# Example usage
if __name__ == "__main__":
    from tradingagents.schemas.agent_schemas import AnalystOutput
    
    # Mock LLM callable
    class MockLLM:
        def __init__(self, responses):
            self.responses = responses
            self.call_count = 0
        
        def invoke(self, prompt):
            response = self.responses[self.call_count]
            self.call_count += 1
            
            class Response:
                def __init__(self, content):
                    self.content = content
            
            return Response(response)
    
    # Test: First attempt fails (invalid JSON), second succeeds
    responses = [
        "This is just text, not JSON",  # First attempt fails
        '''```json
        {
            "analyst_type": "market",
            "key_findings": ["Finding 1", "Finding 2", "Finding 3"],
            "signal": "BUY",
            "confidence": 0.8,
            "reasoning": "Strong technical indicators suggest bullish momentum with volume confirmation."
        }
        ```'''  # Second attempt succeeds
    ]
    
    mock_llm = MockLLM(responses)
    retry_loop = JSONRetryLoop(max_retries=2)
    
    prompt = "Analyze the market and output JSON"
    context = {}
    
    result, metadata = retry_loop.invoke_with_retry(
        mock_llm.invoke,
        AnalystOutput,
        prompt,
        context
    )
    
    print(f"Attempts: {metadata['attempts']}")
    print(f"Errors: {metadata['errors']}")
    print(f"Success: {result is not None}")
    
    if result:
        print(f"\nParsed output:")
        print(result.json(indent=2))
    
    print(f"\nRetry stats:")
    print(retry_loop.get_stats())
