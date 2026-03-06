from tradingagents.agents.utils.factor_rules import load_factor_rules, summarize_factor_rules
from tradingagents.dataflows.config import get_config


def create_factor_rule_analyst(llm):
    def factor_rule_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        config = get_config()
        rules, rule_path = load_factor_rules(config)
        summary = summarize_factor_rules(rules, ticker, current_date)

        system_prompt = f"""You are a Factor Rule Analyst for a trading research team.
Your job is to interpret manually curated factor rules for {ticker} on {current_date}.
The rules are loaded from: {rule_path or 'no file found'}.
You must:
1. Summarize the strongest bullish and bearish factor signals.
2. Explain which rules are higher conviction based on weight and rationale.
3. Point out any rule conflicts or missing information.
4. End with a practical conclusion describing how traders and downstream researchers should use these factor rules.
5. Include a short markdown table of the highest priority rules.
Do not invent quantitative backtest results. Only reason from the provided rule context.

Rule context:
{summary}
"""

        result = llm.invoke(system_prompt)

        return {
            "messages": [result],
            "factor_rules_report": result.content,
        }

    return factor_rule_analyst_node
