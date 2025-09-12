# 文心一言模型适配器
# 支持百度文心一言大模型

import os
import requests
import json
from typing import List, Dict, Any, Optional, Iterator
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.outputs import LLMResult, Generation, ChatResult, ChatGeneration
from pydantic import Field


class ErnieAdapter(BaseChatModel):
    """
    文心一言模型适配器
    支持百度文心一言大模型的调用
    """
    
    model_name: str = Field(default="ernie-4.0-8k", description="模型名称")
    api_key: Optional[str] = Field(default=None, description="API密钥")
    secret_key: Optional[str] = Field(default=None, description="Secret密钥")
    base_url: str = Field(default="https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat", description="API基础URL")
    temperature: float = Field(default=0.7, description="温度参数")
    max_tokens: int = Field(default=2000, description="最大token数")
    
    def __init__(
        self,
        model_name: str = "ernie-4.0-8k",
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        base_url: str = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat",
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ):
        super().__init__(
            model_name=model_name,
            api_key=api_key or os.getenv("BAIDU_API_KEY"),
            secret_key=secret_key or os.getenv("BAIDU_SECRET_KEY"),
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        if not self.api_key or not self.secret_key:
            raise ValueError("请设置BAIDU_API_KEY和BAIDU_SECRET_KEY环境变量")
    
    @property
    def _llm_type(self) -> str:
        return "ernie"
    
    def _get_access_token(self) -> str:
        """获取访问令牌"""
        url = "https://aip.baidubce.com/oauth/2.0/token"
        params = {
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.secret_key
        }
        
        response = requests.post(url, params=params)
        response.raise_for_status()
        result = response.json()
        
        return result["access_token"]
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """生成回复"""
        try:
            # 获取访问令牌
            access_token = self._get_access_token()
            
            # 转换消息格式
            formatted_messages = self._format_messages(messages)
            
            # 构建请求数据
            data = {
                "messages": formatted_messages,
                "temperature": self.temperature,
                "max_output_tokens": self.max_tokens,
            }
            
            # 添加停止词
            if stop:
                data["stop"] = stop
            
            # 发送请求
            url = f"{self.base_url}/{self.model_name}?access_token={access_token}"
            headers = {"Content-Type": "application/json"}
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            # 解析响应
            content = result["result"]
            message = AIMessage(content=content)
            generation = ChatGeneration(message=message)
            
            return ChatResult(generations=[generation])
            
        except Exception as e:
            raise Exception(f"文心一言API调用失败: {str(e)}")
    
    def _format_messages(self, messages: List[BaseMessage]) -> List[Dict[str, str]]:
        """将LangChain消息格式转换为文心一言格式"""
        formatted = []
        
        for message in messages:
            if isinstance(message, SystemMessage):
                formatted.append({"role": "user", "content": f"系统提示: {message.content}"})
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
