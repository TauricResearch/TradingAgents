from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_sentiment,
    get_insider_transactions,
    get_global_news
)

def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]
        
        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        
        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")
        
        return {"messages": removal_operations + [placeholder]}
    
    return delete_messages


import json
import os
import tempfile
from typing import Dict, Any

def write_json_atomic(path: str, data: Dict[str, Any]):
    """
    Atomically write JSON data to a file.
    
    1. Writes to a temporary file in the same directory.
    2. Renames the temp file to the target path (atomic operation).
    """
    directory = os.path.dirname(path)
    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
        
    try:
        # Create temp file in the same directory to ensure atomic rename works
        with tempfile.NamedTemporaryFile(mode='w', dir=directory, delete=False) as tf:
            json.dump(data, tf, indent=4)
            temp_path = tf.name
            
        # Atomic rename
        os.replace(temp_path, path)
    except Exception as e:
        # Cleanup if something failed before rename
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        raise e


        