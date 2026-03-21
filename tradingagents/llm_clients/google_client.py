import time
import random
from typing import Any, Optional

from langchain_google_genai import ChatGoogleGenerativeAI

from .base_client import BaseLLMClient
from .validators import validate_model


class NormalizedChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """ChatGoogleGenerativeAI with normalized content output and auto-retry on SSL/connection errors."""

    def _normalize_content(self, response):
        content = response.content
        if isinstance(content, list):
            texts = [
                item.get("text", "") if isinstance(item, dict) and item.get("type") == "text"
                else item if isinstance(item, str) else ""
                for item in content
            ]
            response.content = "\n".join(t for t in texts if t)
        return response

    def invoke(self, input, config=None, **kwargs):
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                return self._normalize_content(super().invoke(input, config, **kwargs))
            except Exception as e:
                err = str(e)
                # 判断是否为可重试的网络错误
                retryable = any(kw in err for kw in [
                    "SSL", "EOF", "RemoteProtocolError", "ConnectError",
                    "Server disconnected", "ConnectionError", "timeout",
                    "503", "502", "500",
                ])
                if retryable and attempt < max_retries:
                    wait = 2 ** attempt + random.uniform(0, 2)
                    print(f"\n⚠️  Gemini 连接失败（第 {attempt}/{max_retries} 次），{wait:.1f}s 后重试... [{type(e).__name__}]")
                    time.sleep(wait)
                else:
                    raise


class GoogleClient(BaseLLMClient):
    """Client for Google Gemini models."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatGoogleGenerativeAI instance."""
        llm_kwargs = {"model": self.model}

        for key in ("timeout", "max_retries", "google_api_key", "callbacks", "http_client", "http_async_client"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        thinking_level = self.kwargs.get("thinking_level")
        if thinking_level:
            model_lower = self.model.lower()
            if "gemini-3" in model_lower:
                if "pro" in model_lower and thinking_level == "minimal":
                    thinking_level = "low"
                llm_kwargs["thinking_level"] = thinking_level
            else:
                llm_kwargs["thinking_budget"] = -1 if thinking_level == "high" else 0

        return NormalizedChatGoogleGenerativeAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Google."""
        return validate_model("google", self.model)
