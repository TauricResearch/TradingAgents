from abc import ABC, abstractmethod
from typing import Any, Optional
import warnings


def normalize_content(response):
    """将 LLM 响应内容归一化为纯字符串。

    多个 Provider（OpenAI Responses API、Google Gemini 3）返回的 content 是
    typed block 列表，如 [{'type': 'reasoning', ...}, {'type': 'text', 'text': '...}]。
    下游 agent 期望 content 是字符串。本函数提取并拼接所有 text block，
    丢弃 reasoning/metadata block，并对普通字符串列表做兼容处理。
    """
    content = response.content
    if isinstance(content, list):
        texts = [
            # 情况1: Responses API 格式 {type: "text", text: "..."}
            # 只提取 text block，丢弃 reasoning/metadata block（如 thinking 过程）
            item.get("text", "")
            if isinstance(item, dict) and item.get("type") == "text"
            # 情况2: 传统 Chat Completions 格式，直接就是字符串列表
            # 如 ["第一段", "第二段"]，直接保留
            else item if isinstance(item, str)
            # 兜底: 未知类型 item → 忽略，避免抛异常
            else ""
            for item in content
        ]
        response.content = "\n".join(t for t in texts if t)
    return response


class BaseLLMClient(ABC):
    """所有 LLM Client 的抽象基类，定义统一接口。

    子类必须实现 get_llm() 和 validate_model()。
    warn_if_unknown_model() 提供统一的未知模型警告机制。
    """

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        self.model = model
        self.base_url = base_url
        self.kwargs = kwargs

    def get_provider_name(self) -> str:
        """获取 Provider 名称，用于警告信息。

        优先使用子类设置的 self.provider 属性，
        否则从类名推断（如 AzureOpenAIClient → azureopenai）。
        """
        provider = getattr(self, "provider", None)
        if provider:
            return str(provider)
        return self.__class__.__name__.removesuffix("Client").lower()

    def warn_if_unknown_model(self) -> None:
        """当模型不在已知列表中时发出 RuntimeWarning，不阻断执行。

        validate_model() 返回 False 时触发，提醒用户确认模型名是否正确。
        使用 warnings.warn 而非抛异常，因为未知模型不代表不能用
        （可能是用户自定义的模型）。
        """
        if self.validate_model():
            return

        warnings.warn(
            (
                f"Model '{self.model}' is not in the known model list for "
                f"provider '{self.get_provider_name()}'. Continuing anyway."
            ),
            RuntimeWarning,
            stacklevel=2,
        )

    @abstractmethod
    def get_llm(self) -> Any:
        """返回配置好的 LLM 实例（如 ChatOpenAI、ChatAnthropic）。"""
        pass

    @abstractmethod
    def validate_model(self) -> bool:
        """校验模型是否在 provider 支持的白名单中。

        返回 True 表示通过，返回 False 会触发 warn_if_unknown_model() 警告。
        Azure 等部署模式 provider 直接返回 True（任意已部署模型都可用）。
        """
        pass
