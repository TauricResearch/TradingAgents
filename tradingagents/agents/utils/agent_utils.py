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
from typing import Dict, Any, Union, List

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

def normalize_agent_output(content: Union[str, List, Any]) -> str:
    """
    Normalize LLM output into a clean string.
    
    Handlers:
    - String: Returns as-is
    - List (Anthropic/Gemini): Extracts 'text' fields or joins items
    - Other: Converts to string via str()
    
    This ensures AgentState always contains normalized strings, 
    preventing downstream crashes in CLI/UI.
    """
    if not content:
        return ""
        
    if isinstance(content, str):
        return content
        
    elif isinstance(content, list):
        # Handle Anthropic/Gemini list format
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    text_parts.append(item.get('text', ''))
                # Skip 'tool_use' blocks in the final report string
            else:
                text_parts.append(str(item))
        return ' '.join(text_parts)
        
    return str(content)

def smart_truncate(content: Any, max_length: int = 15000, max_list_items: int = 50) -> str:
    """
    Intelligently truncate content to preserve structure/validity primarily.
    
    Strategies:
    - List: Slice to first N items.
    - Dict: (Naive) Convertible to string, capped. (Advanced) Could pop keys.
    - String: Char limit with indicator.
    
    Returns a string representation.
    """
    try:
        if isinstance(content, list):
            # Semantic Truncation for Lists (e.g. News articles, Insider rows)
            if len(content) > max_list_items:
                truncated = content[:max_list_items]
                return json.dumps(truncated, indent=2) + f"\n... [TRUNCATED {len(content)-max_list_items} ITEMS] ..."
            return json.dumps(content, indent=2)
            
        elif isinstance(content, dict):
            # For Dicts, we trust json.dumps but safe guard size
            dump = json.dumps(content, indent=2)
            if len(dump) > max_length:
                return dump[:max_length] + "\n... [TRUNCATED JSON] ...}" # Try to close brace? A bit risky but better.
            return dump
            
        else:
            # Raw String Fallback
            s = str(content)
            if len(s) > max_length:
                return s[:max_length] + "\n... [TRUNCATED] ..."
            return s
    except Exception as e:
        # Fallback to safe string truncation
        s = str(content)
        return s[:max_length] + "..." if len(s) > max_length else s