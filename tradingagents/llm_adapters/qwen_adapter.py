# 通义千问模型适配器
# 支持阿里云通义千问大模型

import os
import requests
import json
from typing import List, Dict, Any, Optional, Iterator
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.outputs import LLMResult, Generation, ChatResult, ChatGeneration
from pydantic import Field


class QwenAdapter(BaseChatModel):
    """
    通义千问模型适配器
    支持阿里云通义千问大模型的调用
    """
    
    model_name: str = Field(default="qwen-plus", description="模型名称")
    api_key: Optional[str] = Field(default=None, description="API密钥")
    base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1", description="API基础URL")
    temperature: float = Field(default=0.7, description="温度参数")
    max_tokens: int = Field(default=2000, description="最大token数")
    
    def __init__(
        self,
        model_name: str = "qwen-plus",
        api_key: Optional[str] = None,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ):
        super().__init__(
            model_name=model_name,
            api_key=api_key or os.getenv("DASHSCOPE_API_KEY"),
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        if not self.api_key:
            raise ValueError("请设置DASHSCOPE_API_KEY环境变量或传入api_key参数")
    
    @property
    def _llm_type(self) -> str:
        return "qwen"
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """生成回复"""
        try:
            # 转换消息格式
            formatted_messages = self._format_messages(messages)
            
            # 构建请求数据
            data = {
                "model": self.model_name,
                "messages": formatted_messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }
            
            # 添加停止词
            if stop:
                data["stop"] = stop
            
            # 发送请求（带重试机制）
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # 添加重试机制
            import time
            max_retries = 5  # 增加重试次数
            for attempt in range(max_retries):
                try:
                    response = requests.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=data,
                        timeout=60  # 增加超时时间到60秒
                    )
                    break
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ReadTimeout) as e:
                    if attempt < max_retries - 1:
                        wait_time = min(2 ** attempt, 10)  # 最大等待10秒
                        print(f"⚠️  网络请求失败，第{attempt + 1}次重试，等待{wait_time}秒...")
                        time.sleep(wait_time)
                    else:
                        print(f"❌ 网络请求最终失败: {str(e)}")
                        raise e
            
            response.raise_for_status()
            result = response.json()
            
            # 解析响应
            content = result["choices"][0]["message"]["content"]
            message = AIMessage(content=content)
            generation = ChatGeneration(message=message)
            
            return ChatResult(generations=[generation])
            
        except Exception as e:
            raise Exception(f"通义千问API调用失败: {str(e)}")
    
    def _format_messages(self, messages: List[BaseMessage]) -> List[Dict[str, str]]:
        """将LangChain消息格式转换为通义千问格式"""
        formatted = []
        
        for message in messages:
            if isinstance(message, SystemMessage):
                formatted.append({"role": "system", "content": message.content})
            elif isinstance(message, HumanMessage):
                formatted.append({"role": "user", "content": message.content})
            elif isinstance(message, AIMessage):
                formatted.append({"role": "assistant", "content": message.content})
        
        return formatted
    
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGeneration]:
        """流式生成（暂不支持）"""
        # 对于不支持流式生成的模型，我们返回一个包含完整响应的生成
        result = self._generate(messages, stop, run_manager, **kwargs)
        for generation in result.generations:
            yield generation
    
    def bind_tools(self, tools, **kwargs):
        """绑定工具到模型（简化实现）"""
        # 对于国内模型，我们简化工具绑定
        # 直接返回self，让上层处理工具调用
        return self
    
    @property
    def _identifying_params(self) -> Dict[str, Any]:
        """返回识别参数"""
        return {
            "model_name": self.model_name,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
