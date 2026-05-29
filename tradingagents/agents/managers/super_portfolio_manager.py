from langchain_core.prompts import ChatPromptTemplate
from tradingagents.agents.utils.agent_utils import get_language_instruction

def create_super_portfolio_manager(llm):
    """Creates a node that takes reports from multiple tickers and optimizes the portfolio."""
    
    def super_portfolio_manager_node(state: dict):
        # State will contain a dict of ticker -> trader decisions
        ticker_reports = state.get("ticker_reports", {})
        
        # Prepare the context
        context_str = ""
        for ticker, report in ticker_reports.items():
            context_str += f"\n--- Ticker: {ticker} ---\n"
            context_str += f"Trader Plan: {report.get('trader_plan', 'No plan')}\n"
            context_str += f"Portfolio Manager Decision: {report.get('portfolio_decision', 'No decision')}\n"
        
        from tradingagents.default_config import DEFAULT_CONFIG
        system_message = (
            DEFAULT_CONFIG.get(
                "super_portfolio_manager_prompt",
                "You are a Super Portfolio Manager for a hedge fund. Allocate the portfolio across these assets based on their reports."
            )
            + get_language_instruction()
        )
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("user", f"Here are the final decisions from the trading team for the selected assets:\n\n{context_str}\n\nPlease provide the final portfolio allocation and strategy.")
        ])
        
        chain = prompt | llm
        result = chain.invoke({})
        
        return {
            "super_portfolio_report": result.content
        }
        
    return super_portfolio_manager_node
