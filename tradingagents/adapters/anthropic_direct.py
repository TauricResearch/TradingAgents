"""
Direct Anthropic API Adapter for TradingAgents
This adapter bypasses LangChain's proxy issues by using direct API calls
"""

import os
import json
import requests
from typing import List, Dict, Any, Optional
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class DirectChatAnthropic(Runnable):
    """
    Direct Anthropic API adapter that bypasses LangChain proxy issues.
    Mimics the ChatAnthropic interface but uses direct HTTP requests.
    """
    
    def __init__(self, model: str = "claude-3-5-haiku-20241022", **kwargs):
        super().__init__()
        self.model = model
        self.api_key = os.environ.get('ANTHROPIC_API_KEY')
        self.base_url = "https://api.anthropic.com/v1"
        self.max_tokens = kwargs.get('max_tokens', 4096)
        self.temperature = kwargs.get('temperature', 0.7)
        
        # Setup HTTP session with proxy support
        self.session = self._create_session()
        
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
    
    def _create_session(self) -> requests.Session:
        """Create a requests session with proxy and retry configuration"""
        session = requests.Session()
        
        # Retry strategy
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
            backoff_factor=1
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Corporate proxy configuration
        proxy_url = os.environ.get('HTTP_PROXY') or os.environ.get('HTTPS_PROXY')
        if proxy_url:
            session.proxies.update({
                'http': proxy_url,
                'https': proxy_url,
            })
        
        return session
    
    def _convert_messages(self, messages: List[BaseMessage]) -> tuple[str, List[Dict]]:
        """Convert LangChain messages to Anthropic API format"""
        system_message = ""
        formatted_messages = []
        
        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_message = msg.content
            elif isinstance(msg, HumanMessage):
                formatted_messages.append({
                    "role": "user",
                    "content": msg.content
                })
            elif isinstance(msg, AIMessage):
                formatted_messages.append({
                    "role": "assistant", 
                    "content": msg.content
                })
            elif isinstance(msg, dict):
                # Handle dictionary messages
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                if role == 'system':
                    system_message = content
                elif role in ['user', 'assistant']:
                    formatted_messages.append({
                        "role": role,
                        "content": content
                    })
            elif hasattr(msg, 'role') and hasattr(msg, 'content'):
                # Handle object-like messages with attributes
                role = msg.role if msg.role in ['user', 'assistant'] else 'user'
                formatted_messages.append({
                    "role": role,
                    "content": msg.content
                })
        
        return system_message, formatted_messages
    
    def _make_request(self, messages: List[BaseMessage]) -> Dict[str, Any]:
        """Make direct API request to Anthropic"""
        system_message, formatted_messages = self._convert_messages(messages)
        
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": formatted_messages
        }
        
        if system_message:
            payload["system"] = system_message
        
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/messages",
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Anthropic API error: {response.status_code} - {response.text}")
                
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {e}")
    
    def invoke(self, input: Any, config=None, **kwargs) -> AIMessage:
        """Invoke the model with messages (mimics ChatAnthropic.invoke)"""
        
        # Handle different input formats
        messages = input
        if isinstance(input, dict) and 'messages' in input:
            messages = input['messages']
        elif hasattr(input, 'messages'):
            messages = input.messages
        elif not isinstance(input, list):
            # Convert single message
            messages = [HumanMessage(content=str(input))]
            
        if isinstance(messages, list):
            if len(messages) > 0 and isinstance(messages[0], tuple):
                # Handle tuple format: [("system", "content"), ("human", "content")]
                converted_messages = []
                for role, content in messages:
                    if role == "system":
                        converted_messages.append(SystemMessage(content=content))
                    elif role == "human":
                        converted_messages.append(HumanMessage(content=content))
                    elif role == "assistant":
                        converted_messages.append(AIMessage(content=content))
                messages = converted_messages
        
        # Make the API request
        response_data = self._make_request(messages)
        
        # Extract content from response
        if "content" in response_data and len(response_data["content"]) > 0:
            content = response_data["content"][0]["text"]
        else:
            content = "No response generated"
        
        # Return AIMessage to match LangChain interface
        return AIMessage(content=content)
    
    def __call__(self, input: Any, config=None, **kwargs) -> AIMessage:
        """Allow direct calling of the instance"""
        return self.invoke(input, config, **kwargs)
    
    def bind_tools(self, tools):
        """Bind tools to the model (compatibility method for LangChain)"""
        # For now, we'll return a simplified version that doesn't actually use tools
        # This is to maintain compatibility with LangChain patterns
        return ToolBoundDirectChatAnthropic(self, tools)


class ToolBoundDirectChatAnthropic(Runnable):
    """A wrapper that handles tool binding for DirectChatAnthropic"""
    
    def __init__(self, llm: DirectChatAnthropic, tools):
        super().__init__()
        self.llm = llm
        self.tools = tools
        
    def invoke(self, input: Any, config=None, **kwargs) -> AIMessage:
        """Invoke with tool awareness (simplified for now)"""
        # Handle different input formats
        if isinstance(input, list):
            messages = input
        elif isinstance(input, dict) and 'messages' in input:
            messages = input['messages']
        elif hasattr(input, 'messages'):
            messages = input.messages
        else:
            # Fallback
            messages = input if isinstance(input, list) else [HumanMessage(content=str(input))]
            
        # For now, just pass through to the underlying LLM
        # In a full implementation, we'd handle tool calls properly
        response = self.llm.invoke(messages)
        
        # Add some tool-like behavior if needed
        if hasattr(response, 'content') and 'ticker' in str(response.content).lower():
            # This is a simplified approach - in reality we'd parse tool calls
            pass
            
        return response


def create_anthropic_adapter(model: str = "claude-3-5-haiku-20241022", **kwargs) -> DirectChatAnthropic:
    """Factory function to create the Anthropic adapter"""
    return DirectChatAnthropic(model=model, **kwargs)


# Test function to verify the adapter works
def test_anthropic_adapter():
    """Test the Anthropic adapter"""
    try:
        adapter = create_anthropic_adapter()
        
        # Test with tuple format
        messages = [
            ("system", "You are a helpful assistant."),
            ("human", "Say 'Anthropic adapter working!'")
        ]
        
        response = adapter.invoke(messages)
        print(f"✅ Test SUCCESS: {response.content}")
        return True
        
    except Exception as e:
        print(f"❌ Test FAILED: {e}")
        return False


if __name__ == "__main__":
    test_anthropic_adapter() 