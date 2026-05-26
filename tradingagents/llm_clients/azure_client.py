import os
from typing import Any, Optional

from langchain_openai import AzureChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "api_key", "reasoning_effort",
    "callbacks", "http_client", "http_async_client",
)


class NormalizedAzureChatOpenAI(AzureChatOpenAI):
    """对 AzureChatOpenAI 的标准化封装，归一化响应内容为字符串。

    与 NormalizedChatOpenAI 逻辑一致：Responses API 返回 block 列表，
    normalize_content 提取并拼接所有 text block，保证下游收到纯字符串。
    """

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))


class AzureOpenAIClient(BaseLLMClient):
    """Azure OpenAI 部署的 LLM Client。

    通过环境变量配置：
        AZURE_OPENAI_API_KEY: API 密钥
        AZURE_OPENAI_ENDPOINT: 端点 URL（如 https://<resource>.openai.azure.com/）
        AZURE_OPENAI_DEPLOYMENT_NAME: 部署名称（优先读此变量，回退到 model 参数）
        OPENAI_API_VERSION: API 版本（如 2025-03-01-preview）
    """

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """构建 NormalizedAzureChatOpenAI 实例。"""
        self.warn_if_unknown_model()

        llm_kwargs = {
            "model": self.model,
            # azure_deployment 优先读取环境变量，回退到 model 名
            "azure_deployment": os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", self.model),
        }

        # 将允许透传的参数（timeout、max_retries 等）从 kwargs 复制到 llm_kwargs
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return NormalizedAzureChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Azure 接受任意已部署的模型名，不做白名单校验。"""
        return True
