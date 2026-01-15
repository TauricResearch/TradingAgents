from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import json
from tradingagents.agents.utils.agent_utils import normalize_agent_output, smart_truncate


from tradingagents.utils.anonymizer import TickerAnonymizer
from tradingagents.utils.logger import app_logger as logger

def create_fundamentals_analyst(llm):
    # PARANOIA CHECK
    if hasattr(llm, "tools") and llm.tools:
        logger.critical("SECURITY VIOLATION: Fundamentals Analyst has access to tools!")

    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        
        # 1. READ FROM LEDGER
        ledger = state.get("fact_ledger")
        if not ledger:
             raise RuntimeError("Fundamentals Analyst: FactLedger missing.")
             
        raw_fund_data = ledger.get("fundamental_data")
        raw_insider_data = ledger.get("insider_data")
        
        # Anonymize
        anonymizer = TickerAnonymizer()
        real_ticker = state["company_of_interest"]
        ticker = anonymizer.anonymize_ticker(real_ticker)

        # Context Construction
        data_context = "FUNDAMENTAL DATA:\n" 
        
        data_context += smart_truncate(raw_fund_data, max_length=15000)
            
        data_context += "\n\nINSIDER TRANSACTIONS (Supplementary):\n"
        data_context += smart_truncate(raw_insider_data, max_length=5000, max_list_items=50)

        # ESCAPE BRACES for LangChain
        data_context = data_context.replace("{", "{{").replace("}", "}}")

        system_message = (
            f"""ROLE: Quantitative Fundamental Analyst.
CONTEXT: You are analyzing an ANONYMIZED ASSET (ASSET_XXX).
DATA SOURCE: TRUSTED FACT LEDGER ID {ledger.get('ledger_id', 'UNKNOWN')}.

AVAILABLE DATA:
{data_context}

TASK: Write a comprehensive fundamental analysis report.
Focus on:
1. Financial Stability (Balance Sheet).
2. Profitability Trends (Income Statement).
3. Cash Flow Quality.
4. Insider Sentiment (if available).

STRICT COMPLIANCE:
1. CITATION RULE: Cite "FactLedger" for all numbers.
2. NO HALLUCINATION: If data (e.g., P/E ratio) is not in the text above, DO NOT invent it.
3. UNIT NORMALIZATION: Assume all currency is USD unless stated otherwise.

Make sure to append a Markdown table at the end of the report summarizing key Financial Ratios."""
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_message),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        
        try:
            # NO BIND TOOLS
            chain = prompt | llm 
            # Fix: Must pass dict to Chain when using MessagesPlaceholder
            result = chain.invoke({"messages": state["messages"]})
            report = result.content
        except Exception as e:
            logger.error(f"Fundamentals Analyst Failed: {e}")
            report = f"Analysis Failed: {str(e)}"
            result = None

        return {
            "messages": [result] if result else [],
            "fundamentals_report": normalize_agent_output(report),
        }

    return fundamentals_analyst_node
