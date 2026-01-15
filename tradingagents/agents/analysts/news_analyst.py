from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import json
from tradingagents.agents.utils.agent_utils import normalize_agent_output
from tradingagents.utils.anonymizer import TickerAnonymizer
from tradingagents.utils.logger import app_logger as logger

def create_news_analyst(llm):
    # PARANOIA CHECK
    if hasattr(llm, "tools") and llm.tools:
        logger.critical("SECURITY VIOLATION: News Analyst has access to tools!")

    def news_analyst_node(state):
        current_date = state["trade_date"]
        real_ticker = state["company_of_interest"]
        
        # BLINDFIRE PROTOCOL: Anonymize Ticker
        anonymizer = TickerAnonymizer()
        ticker = anonymizer.anonymize_ticker(real_ticker)

        # 1. READ FROM LEDGER
        ledger = state.get("fact_ledger")
        if not ledger:
             raise RuntimeError("News Analyst: FactLedger missing.")
             
        raw_news_data = ledger.get("news_data")
        
        # Format Context
        data_context = "RAW NEWS DATA:\n"
        # Ideally this is a list of articles. If string, just dump it.
        if isinstance(raw_news_data, (list, dict)):
             data_context += json.dumps(raw_news_data, indent=2)
        else:
             data_context += str(raw_news_data)

        # ESCAPE BRACES for LangChain
        data_context = data_context.replace("{", "{{").replace("}", "}}")

        system_message = (
            f"""ROLE: Macroeconomic & News Analyst.
CONTEXT: You are analyzing global and specific news for ANONYMIZED ASSET (ASSET_XXX).
DATA SOURCE: TRUSTED FACT LEDGER ID {ledger.get('ledger_id', 'UNKNOWN')}.

AVAILABLE DATA:
{data_context}

TASK: Write a comprehensive news report.
1. Synthesize the provided news headers/summaries.
2. Identify Sentiment (Positive/Negative/Neutral).
3. flag any "Red Swan" events (Regulatory bans, Lawsuits).
4. Ignore any news older than 7 days unless critical context.

STRICT COMPLIANCE:
1. CITATION RULE: Cite "FactLedger" for all claims.
2. NO HALLUCINATION: Do NOT invent news stories.
3. If data is empty, report "No relevant news found."

Make sure to append a Markdown table at the end summarizing key events."""
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
            logger.error(f"News Analyst Failed: {e}")
            report = f"News Analysis Failed: {str(e)}"
            result = None

        return {
            "messages": [result] if result else [],
            "news_report": normalize_agent_output(report),
        }

    return news_analyst_node
