from langchain_core.prompts import ChatPromptTemplate
from tradingagents.agents.utils.agent_states import AgentState

def create_trade_strategist(llm):
    def trade_strategist_node(state: AgentState):
        """
        Agent that analyzes the final trade decision and outputs 5 distinct trade setups.
        """
        
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are an elite Trade Strategist at a premier quantitative hedge fund.
Your job is to take the final consensus decision from the Portfolio Manager and the Trader's investment plan, and synthesize them into exactly 5 specific, actionable trade setups.

For the given asset, you must provide exactly 5 trade possibilities with the following parameters explicitly defined for each:
- Trade Direction (Long/Short, Options, etc.)
- Entry Price / Condition (e.g., Buy at market, Limit buy at $X, Wait for breakout above $X)
- Stop Loss (SL) (Specific price level)
- Take Profit (TP) (Specific price level)
- Risk/Reward Ratio
- Estimated Win Percentage (Probability of success based on current technicals/fundamentals, e.g., 65%)
- Brief Rationale (1-2 sentences explaining why this setup makes sense)

Format your output as a clean, highly readable Markdown document.
Do not output anything besides the 5 trades and a brief introductory/concluding sentence.
Use bullet points and bold text for the parameters so they are easily scannable."""
                ),
                (
                    "human",
                    """Asset: {company}

Portfolio Manager's Final Decision:
{final_decision}

Trader's Investment Plan:
{trader_plan}

Please formulate the 5 Trade Possibilities based on the above data."""
                ),
            ]
        )

        chain = prompt | llm

        result = chain.invoke({
            "company": state.get("company_of_interest", ""),
            "final_decision": state.get("final_trade_decision", ""),
            "trader_plan": state.get("trader_investment_plan", "")
        })
        
        return {"trade_possibilities": result.content}
        
    return trade_strategist_node
