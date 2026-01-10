"""
RAG Isolator - Strict Context Enforcement

Forces LLMs to answer ONLY from provided context, preventing use of pre-trained knowledge.
"""

from typing import Dict, List, Any, Optional
from langchain.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage


class RAGIsolator:
    """
    Enforce strict RAG (Retrieval-Augmented Generation) to prevent knowledge contamination.
    
    LLMs must answer ONLY from provided context, not from training data.
    """
    
    def __init__(self, strict_mode: bool = True):
        """
        Initialize RAG isolator.
        
        Args:
            strict_mode: If True, explicitly forbid use of pre-trained knowledge
        """
        self.strict_mode = strict_mode
    
    def create_isolated_prompt(
        self,
        query: str,
        context: Dict[str, Any],
        system_role: str = "financial analyst"
    ) -> ChatPromptTemplate:
        """
        Create a prompt that enforces strict RAG isolation.
        
        Args:
            query: The question to answer
            context: Structured context data (market data, news, fundamentals)
            system_role: Role description for the agent
        
        Returns:
            ChatPromptTemplate with strict RAG enforcement
        """
        # Build context string from structured data
        context_str = self._format_context(context)
        
        if self.strict_mode:
            system_message = f"""You are a {system_role}. You must answer questions using ONLY the information provided in the CONTEXT section below.

CRITICAL RULES:
1. DO NOT use any knowledge from your training data
2. DO NOT make assumptions about companies, products, or events
3. If the CONTEXT does not contain the information needed to answer, respond with "INSUFFICIENT DATA"
4. DO NOT identify companies by price levels, volatility patterns, or other indirect signals
5. Treat all data as anonymous - you are analyzing ASSET_XXX, not real companies

CONTEXT:
{context_str}

If you cannot answer from the CONTEXT alone, you MUST respond: "INSUFFICIENT DATA: [explain what information is missing]"
"""
        else:
            system_message = f"""You are a {system_role}. Use the following context to answer questions.

CONTEXT:
{context_str}
"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", "{query}")
        ])
        
        return prompt
    
    def _format_context(self, context: Dict[str, Any]) -> str:
        """
        Format structured context into readable text.
        
        Args:
            context: Dictionary with market data, news, fundamentals, etc.
        
        Returns:
            Formatted context string
        """
        sections = []
        
        # Market Data Section
        if "market_data" in context:
            market_data = context["market_data"]
            sections.append("=== MARKET DATA ===")
            sections.append(f"Current Price Index: {market_data.get('close', 'N/A')}")
            sections.append(f"Volume: {market_data.get('volume', 'N/A')}")
            
            if "indicators" in market_data:
                sections.append("\nTechnical Indicators:")
                for indicator, value in market_data["indicators"].items():
                    sections.append(f"  {indicator}: {value}")
        
        # News Section
        if "news" in context:
            sections.append("\n=== NEWS SUMMARY ===")
            for i, article in enumerate(context["news"][:5], 1):  # Limit to 5 articles
                sections.append(f"{i}. {article.get('summary', article.get('title', 'N/A'))}")
        
        # Fundamentals Section
        if "fundamentals" in context:
            fundamentals = context["fundamentals"]
            sections.append("\n=== FUNDAMENTAL DATA ===")
            sections.append(f"Revenue Growth: {fundamentals.get('revenue_growth', 'N/A')}")
            sections.append(f"Earnings: {fundamentals.get('earnings', 'N/A')}")
            sections.append(f"Debt/Equity: {fundamentals.get('debt_to_equity', 'N/A')}")
        
        # Historical Performance
        if "historical" in context:
            sections.append("\n=== HISTORICAL PERFORMANCE ===")
            hist = context["historical"]
            sections.append(f"1-Month Return: {hist.get('1m_return', 'N/A')}")
            sections.append(f"3-Month Return: {hist.get('3m_return', 'N/A')}")
            sections.append(f"6-Month Return: {hist.get('6m_return', 'N/A')}")
        
        return "\n".join(sections)
    
    def validate_response(self, response: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate that LLM response only uses information from context.
        
        Args:
            response: LLM's response
            context: The context that was provided
        
        Returns:
            {
                "valid": bool,
                "violations": List[str],
                "confidence": float
            }
        """
        violations = []
        
        # Check for company name leakage
        company_indicators = [
            "Apple", "Microsoft", "Google", "Amazon", "Meta", "Tesla",
            "Nvidia", "AMD", "Intel", "Oracle", "Salesforce"
        ]
        for company in company_indicators:
            if company.lower() in response.lower():
                violations.append(f"Mentioned real company name: {company}")
        
        # Check for product name leakage
        product_indicators = [
            "iPhone", "Windows", "Android", "Azure", "AWS",
            "GeForce", "RTX", "H100", "A100"
        ]
        for product in product_indicators:
            if product.lower() in response.lower():
                violations.append(f"Mentioned real product name: {product}")
        
        # CRITICAL: Check for currency symbols (immediate hallucination)
        # If context uses normalized values, ANY currency symbol is a leak
        import re
        currency_symbols = re.findall(r'[\$€£¥₹]', response)
        if currency_symbols:
            violations.append(f"HALLUCINATION: Used currency symbols {set(currency_symbols)} (context uses normalized index)")
        
        # Check for absolute dollar amounts (3+ digits with $)
        # This catches "$480" but not "$1.20" (which could be earnings per share)
        absolute_prices = re.findall(r'\$\d{3,}', response)
        if absolute_prices:
            violations.append(f"Mentioned absolute dollar prices: {absolute_prices}")
        
        # Check for "I know" or "based on my knowledge" phrases
        knowledge_phrases = [
            "i know", "as i know", "from my knowledge",
            "based on my training", "historically", "typically"
        ]
        for phrase in knowledge_phrases:
            if phrase in response.lower():
                violations.append(f"Used pre-trained knowledge phrase: '{phrase}'")
        
        valid = len(violations) == 0
        confidence = 1.0 - (len(violations) * 0.2)  # Reduce confidence per violation
        
        return {
            "valid": valid,
            "violations": violations,
            "confidence": max(0.0, confidence)
        }
    
    def create_fact_grounded_prompt(
        self,
        query: str,
        facts: List[str],
        allow_inference: bool = False
    ) -> str:
        """
        Create a prompt that grounds LLM in specific facts.
        
        Args:
            query: Question to answer
            facts: List of factual statements
            allow_inference: Whether to allow logical inference from facts
        
        Returns:
            Formatted prompt string
        """
        facts_str = "\n".join([f"{i+1}. {fact}" for i, fact in enumerate(facts)])
        
        if allow_inference:
            instruction = "You may make logical inferences from these facts, but clearly state when you are inferring."
        else:
            instruction = "Answer using ONLY these facts. Do not infer or extrapolate."
        
        prompt = f"""FACTS:
{facts_str}

QUESTION: {query}

INSTRUCTION: {instruction}

ANSWER:"""
        
        return prompt


# Example usage
if __name__ == "__main__":
    isolator = RAGIsolator(strict_mode=True)
    
    # Create isolated context
    context = {
        "market_data": {
            "close": 102.5,
            "volume": 50000000,
            "indicators": {
                "RSI": 45.2,
                "MACD": 0.8,
                "50_SMA": 100.3
            }
        },
        "news": [
            {"summary": "Company ASSET_042 reported quarterly earnings"},
            {"summary": "Product A sales exceeded expectations"}
        ],
        "fundamentals": {
            "revenue_growth": 0.05,
            "earnings": 1.2,
            "debt_to_equity": 0.3
        }
    }
    
    # Create prompt
    query = "Should I buy this asset?"
    prompt = isolator.create_isolated_prompt(query, context)
    
    print("=== ISOLATED PROMPT ===")
    print(prompt.format(query=query))
    
    # Test response validation
    print("\n=== RESPONSE VALIDATION ===")
    
    # Good response (only uses context)
    good_response = "Based on the RSI of 45.2 and positive revenue growth of 5%, the asset shows moderate strength."
    result = isolator.validate_response(good_response, context)
    print(f"Good response valid: {result['valid']}")
    
    # Bad response (uses pre-trained knowledge)
    bad_response = "This is clearly Apple based on the price level. iPhone sales are strong."
    result = isolator.validate_response(bad_response, context)
    print(f"Bad response valid: {result['valid']}")
    print(f"Violations: {result['violations']}")
