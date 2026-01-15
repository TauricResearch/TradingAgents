from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import json
from tradingagents.agents.utils.agent_utils import normalize_agent_output, smart_truncate
from tradingagents.utils.anonymizer import TickerAnonymizer
from tradingagents.utils.logger import app_logger as logger

def create_social_media_analyst(llm):
    # PARANOIA CHECK
    if hasattr(llm, "tools") and llm.tools:
        logger.critical("SECURITY VIOLATION: Social/Sentiment Analyst has access to tools!")

    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        real_ticker = state["company_of_interest"]
        
        # BLINDFIRE PROTOCOL: Anonymize Ticker
        anonymizer = TickerAnonymizer()
        ticker = anonymizer.anonymize_ticker(real_ticker)

        # 1. READ FROM LEDGER
        ledger = state.get("fact_ledger")
        if not ledger:
             raise RuntimeError("Social Analyst: FactLedger missing.")
             
        # We share NEWS data as source for social sentiment proxy (Simulating reddit scraping from news/blogs)
        raw_news_data = ledger.get("news_data")
        raw_insider_data = ledger.get("insider_data")
        
        # Format Context
        # Format Context
        data_context = "SOCIAL/NEWS SENTIMENT DATA:\n"
        data_context += smart_truncate(raw_news_data, max_length=15000)

        data_context += "\n\nINSIDER TRANSACTIONS (Internal Sentiment):\n"
        data_context += smart_truncate(raw_insider_data, max_length=5000, max_list_items=50)

        # ESCAPE BRACES for LangChain
        data_context = data_context.replace("{", "{{").replace("}", "}}")

        system_message = (
            f"""ROLE: Social Media & Sentiment Analyst.
CONTEXT: You are analyzing sentiment for ANONYMIZED ASSET (ASSET_XXX).
DATA SOURCE: TRUSTED FACT LEDGER ID {ledger.get('ledger_id', 'UNKNOWN')}.

AVAILABLE DATA:
{data_context}

TASK:
1. Analyze the "Vibe" of the news coverage (Positive/Negative/Fearful/Greedy).
2. Analyze Insider Confidence (Buying = Confidence, Selling = Caution).
3. Project how retail traders might react to these headlines.

STRICT COMPLIANCE:
1. CITATION RULE: Cite "FactLedger" for all claims.
2. NO HALLUCINATION: Do NOT invent tweets or reddit posts. Infer sentiment from the provided news/insider text.
3. If data is empty, report "Neutral Sentiment (Insufficient Data)."

Make sure to append a Markdown table at the end summarizing Sentiment Drivers."""
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
            logger.error(f"Social Analyst Failed: {e}")
            report = f"Sentiment Analysis Failed: {str(e)}"
            result = None

        return {
            "messages": [result] if result else [],
            "sentiment_report": normalize_agent_output(report),
        }

    return social_media_analyst_node
