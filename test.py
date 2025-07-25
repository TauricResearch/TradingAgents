from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()



def json_to_markdown(json_file_path: str) -> str:
    """
    Convert trading analysis JSON file to formatted markdown string.
    
    Args:
        json_file_path (str): Path to the JSON file containing trading analysis data
        
    Returns:
        str: Formatted markdown string
    """
    import json
    import os
    
    # Check if file exists
    if not os.path.exists(json_file_path):
        return f"# Error\nFile not found: {json_file_path}"
    
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return f"# Error\nInvalid JSON file: {e}"
    except Exception as e:
        return f"# Error\nError reading file: {e}"
    
    # Get the main date key (assuming it's the first key)
    date_key = list(data.keys())[0]
    trading_data = data[date_key]
    
    # Start building markdown
    markdown = []
    
    # Header
    markdown.append(f"# Trading Analysis Report - {date_key}")
    markdown.append("")
    
    # Basic Information
    markdown.append("## Basic Information")
    markdown.append("")
    markdown.append(f"**Company:** {trading_data.get('company_of_interest', 'N/A')}")
    markdown.append(f"**Trade Date:** {trading_data.get('trade_date', 'N/A')}")
    markdown.append("")
    
    # Market Report
    markdown.append("## Market Analysis Report")
    markdown.append("")
    market_report = trading_data.get("market_report", "")
    if market_report:
        markdown.append(market_report)
    else:
        markdown.append("*No market report available*")
    markdown.append("")
    
    # Sentiment Report
    markdown.append("## Sentiment Analysis")
    markdown.append("")
    sentiment_report = trading_data.get("sentiment_report", "")
    if sentiment_report:
        markdown.append(sentiment_report)
    else:
        markdown.append("*No sentiment report available*")
    markdown.append("")
    
    # News Report
    markdown.append("## News Analysis")
    markdown.append("")
    news_report = trading_data.get("news_report", "")
    if news_report:
        markdown.append(news_report)
    else:
        markdown.append("*No news report available*")
    markdown.append("")
    
    # Fundamentals Report
    markdown.append("## Fundamentals Analysis")
    markdown.append("")
    fundamentals_report = trading_data.get("fundamentals_report", "")
    if fundamentals_report:
        markdown.append(fundamentals_report)
    else:
        markdown.append("*No fundamentals report available*")
    markdown.append("")
    
    # Investment Decision
    markdown.append("## Investment Decision")
    markdown.append("")
    investment_decision = trading_data.get("trader_investment_decision", "")
    if investment_decision:
        markdown.append(investment_decision)
    else:
        markdown.append("*No investment decision available*")
    markdown.append("")
    
    # Investment Plan
    markdown.append("## Investment Plan")
    markdown.append("")
    investment_plan = trading_data.get("investment_plan", "")
    if investment_plan:
        markdown.append(investment_plan)
    else:
        markdown.append("*No investment plan available*")
    markdown.append("")
    
    # Final Trade Decision
    markdown.append("## Final Trade Decision")
    markdown.append("")
    final_decision = trading_data.get("final_trade_decision", "")
    if final_decision:
        markdown.append(final_decision)
    else:
        markdown.append("*No final trade decision available*")
    markdown.append("")
    
    # Debate States
    if "investment_debate_state" in trading_data:
        markdown.append("## Investment Debate Analysis")
        markdown.append("")
        debate_state = trading_data["investment_debate_state"]
        
        if "judge_decision" in debate_state:
            markdown.append("### Judge Decision")
            markdown.append("")
            markdown.append(debate_state["judge_decision"])
            markdown.append("")
    
    if "risk_debate_state" in trading_data:
        markdown.append("## Risk Management Debate")
        markdown.append("")
        risk_state = trading_data["risk_debate_state"]
        
        if "judge_decision" in risk_state:
            markdown.append("### Risk Judge Decision")
            markdown.append("")
            markdown.append(risk_state["judge_decision"])
            markdown.append("")
    
    return "\n".join(markdown)

# Example usage:
if __name__ == "__main__":
    
    # Create a custom config
    config = DEFAULT_CONFIG.copy()
    config["deep_think_llm"] = "gpt-4.1-nano"  # Use a different model
    config["quick_think_llm"] = "gpt-4.1-nano"  # Use a different model
    config["max_debate_rounds"] = 1  # Increase debate rounds
    config["online_tools"] = True # Use online tools or cached data

    # Initialize with custom config
    ta = TradingAgentsGraph(debug=False, config=config)

    # forward propagate
    Ticker = "BTC"
    Date = "2024-05-11"
    _, decision = ta.propagate(Ticker, Date)
    print("--------------------------------")
    print(decision)
    print("--------------------------------")

    path = f"eval_results/{Ticker}/TradingAgentsStrategy_logs/full_states_log_{Date}.json"
    # Convert the JSON file to markdown
    
    markdown_content = json_to_markdown(path)
    
    # Print the markdown content
    print("=" * 80)
    print("MARKDOWN OUTPUT:")
    print("=" * 80)
    print(markdown_content)
    
    # Optionally save to file
    markdown_file = f"eval_results/{Ticker}/TradingAgentsStrategy_logs/report_{Date}.md"
    with open(markdown_file, 'w', encoding='utf-8') as f:
        f.write(markdown_content)
    # print(f"\nMarkdown report saved to: {markdown_file}")
