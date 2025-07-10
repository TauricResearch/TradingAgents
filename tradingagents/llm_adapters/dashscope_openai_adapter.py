"""
DashScope OpenAI兼容接口适配器
使用DashScope的OpenAI兼容API，支持原生工具调用
"""

import os
from typing import Any, Dict, List, Optional
from langchain_openai import ChatOpenAI
from pydantic import Field


class ChatDashScopeOpenAI(ChatOpenAI):
    """DashScope的OpenAI兼容接口适配器"""
    
    def __init__(
        self,
        model: str = "qwen-turbo",
        api_key: Optional[str] = None,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        **kwargs
    ):
        """
        初始化DashScope OpenAI兼容适配器
        
        Args:
            model: 模型名称，如 qwen-turbo, qwen-plus, qwen-max
            api_key: DashScope API密钥
            base_url: DashScope OpenAI兼容接口地址
            **kwargs: 其他参数
        """
        
        # 获取API密钥
        if api_key is None:
            api_key = os.getenv("DASHSCOPE_API_KEY")
        
        if api_key is None:
            raise ValueError(
                "DashScope API key not found. Please set DASHSCOPE_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        # 调用父类初始化
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            **kwargs
        )
    
    @property
    def _llm_type(self) -> str:
        """返回LLM类型"""
        return "dashscope_openai"
    
    @property
    def _identifying_params(self) -> Dict[str, Any]:
        """返回标识参数"""
        return {
            "model": self.model_name,
            "base_url": self.openai_api_base,
            "api_key": "***" if self.openai_api_key else None,
        }
