"""
Example: Using Pydantic validation in analyst agents.

This demonstrates how to add validation at agent boundaries
to catch errors early and provide clear feedback.

Issue #434: https://github.com/TauricResearch/TradingAgents/issues/434
"""

from tradingagents.agents.utils.pydantic_validation import (
    AnalystReport,
    safe_validate_agent_output,
)


def create_market_analyst_with_validation(llm):
    """
    Enhanced market analyst with Pydantic validation.
    
    Wraps the standard market analyst to validate outputs
    and provide clear error messages when validation fails.
    """
    from tradingagents.agents.analysts.market_analyst import create_market_analyst
    
    # Get the original analyst
    original_analyst = create_market_analyst(llm)
    
    def validated_market_analyst_node(state):
        # Run the original analyst
        result = original_analyst(state)
        
        # Validate the output
        if isinstance(result, dict):
            validated = safe_validate_agent_output(result, AnalystReport)
            
            if validated.get('_validation_status') == 'invalid':
                # Log validation error but continue with original output
                print(f"⚠️ Validation warning: {validated.get('_validation_error')}")
            
            return validated
        
        return result
    
    return validated_market_analyst_node


# Usage example:
# from tradingagents.agents.utils.pydantic_validation import create_market_analyst_with_validation
# validated_analyst = create_market_analyst_with_validation(llm)
