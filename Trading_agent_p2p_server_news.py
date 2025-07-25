from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from isek.adapter.base import Adapter, AdapterCard
from isek.node.etcd_registry import EtcdRegistry
from isek.node.node_v2 import Node
import dotenv
from isek.utils.log import LoggerManager
from isek.utils.log import log
import json

LoggerManager.plain_mode()
dotenv.load_dotenv()

NODE_ID = "TA_Agent_News"
# selected_analysts=["market", "social", "news", "fundamentals"]
selected_analysts=["news"]

def json_to_markdown(data: dict) -> str:
    """
    Convert trading analysis JSON to formatted markdown string, extracting only market analysis.
    Assumes input is a dict with a single key (date), and the value is the trading data dict.
    """
    # Extract the first value (trading data dict)
    trading_data = next(iter(data.values()))

    # Start building markdown
    markdown = []
    
    # Header
    markdown.append("# Analysis Report")
    markdown.append("")
    
    # Basic Information
    markdown.append("## Basic Information")
    markdown.append("")
    markdown.append(f"**Company:** {trading_data.get('company_of_interest', 'N/A')}")
    markdown.append(f"**Trade Date:** {trading_data.get('trade_date', 'N/A')}")
    markdown.append("")
    
    # Market Report (only section we want)
    markdown.append(f"## {selected_analysts[0]} Analysis")
    
    markdown.append("")
    if "market_report" in trading_data:
        market_report = trading_data.get("market_report", "")
        if market_report:
            markdown.append(market_report)
    if "news_report" in trading_data:
        news_report = trading_data.get("news_report", "")
        if news_report:
            markdown.append(news_report)
    if "fundamentals_report" in trading_data:
        fundamentals_report = trading_data.get("fundamentals_report", "")
        if fundamentals_report:
            markdown.append(fundamentals_report)
    if "sentiment_report" in trading_data:
        sentiment_report = trading_data.get("sentiment_report", "")
        if sentiment_report:
            markdown.append(sentiment_report)
    else:
        markdown.append("*No market analysis available*")
    markdown.append("")
    
    return "\n".join(markdown)



class TradingAgentAdapter(Adapter):

    def __init__(self):
        
                # Create a custom config
        self.config = DEFAULT_CONFIG.copy()
        self.config["deep_think_llm"] = "gpt-4.1-nano"  # Use a different model
        self.config["quick_think_llm"] = "gpt-4.1-nano"  # Use a different model
        self.config["max_debate_rounds"] = 1  # Increase debate rounds
        self.config["online_tools"] = True # Use online tools or cached data
        self.config["max_completion_tokens"] = 1000

        # Initialize with custom config
        # self.ta = TradingAgentsGraph(debug=True, config=self.config, debate=False, selected_analysts=["market", "social", "news", "fundamentals"])
        self.ta = TradingAgentsGraph(debug=True, config=self.config, debate=False, selected_analysts=selected_analysts)

    def run(self, prompt: str) -> str:
        """Prompt format must be like this: Ticker,Date"""
        try:
            # Try to parse as JSON first
            received = json.loads(prompt)
            # Extract text from the structure
            if isinstance(received, dict) and 'parts' in received and received['parts']:
                result = received['parts'][0]['text']
            else:
                result = str(received)
        except (json.JSONDecodeError, KeyError, TypeError):
            # If not JSON or structure doesn't match, use prompt as is
            result = prompt
        log.debug(f"prompt: {result}")
        
        Ticker = prompt.split(",")[0]
        Date = prompt.split(",")[1]
        print(f"Ticker: {Ticker}, Date: {Date}")
        final_state, decision = self.ta.propagate(Ticker, Date)
        
        # path = f"eval_results/{Ticker}/TradingAgentsStrategy_logs/full_states_log_{Date}.json"
        # # read the json file
        # with open(path, 'r') as f:
        #     final_state = json.load(f)
        
        # final_state is already a dict, no need to parse it
        markdown_content = json_to_markdown(final_state)
        
        return markdown_content

    def get_adapter_card(self) -> AdapterCard:
        return AdapterCard(
            name="Random Number Generator",
            bio="",
            lore="",
            knowledge="",
            routine="",
        )

# Create the server node.
etcd_registry = EtcdRegistry(host="47.236.116.81", port=2379)
# Create the server node.
server_node = Node(node_id=NODE_ID, port=8868, p2p=True, p2p_server_port=9000, adapter=TradingAgentAdapter(), registry=etcd_registry)

# Start the server in the foreground.
server_node.build_server(daemon=False)
# print(server_node.adapter.run("random a number 0-10"))

