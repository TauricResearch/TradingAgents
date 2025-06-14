"""
LLM Wrapper
A flexible wrapper for integrating multiple LLM providers (OpenAI, Anthropic, local models, etc.)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union, Generator
from dataclasses import dataclass
from enum import Enum
import os
import json
from datetime import datetime


class LLMProvider(Enum):
    """Supported LLM providers"""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    HUGGINGFACE = "huggingface"
    OLLAMA = "ollama"
    CUSTOM = "custom"


@dataclass
class LLMConfig:
    """Configuration for LLM instances"""

    provider: LLMProvider
    model_name: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 60
    extra_params: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra_params is None:
            self.extra_params = {}


@dataclass
class LLMResponse:
    """Standardized response from LLM"""

    content: str
    model: str
    usage: Dict[str, int] = None
    raw_response: Any = None
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class BaseLLM(ABC):
    """Abstract base class for all LLM implementations"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.validate_config()

    @abstractmethod
    def validate_config(self):
        """Validate the configuration for the specific LLM"""
        pass

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate a response from the LLM"""
        pass

    @abstractmethod
    def generate_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """Generate a streaming response from the LLM"""
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count tokens in the given text"""
        pass


class OpenAILLM(BaseLLM):
    """OpenAI API implementation"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            import openai

            self.client = openai.OpenAI(
                api_key=config.api_key or os.getenv("OPENAI_API_KEY"),
                base_url=config.api_base,
                timeout=config.timeout,
            )
        except ImportError:
            raise ImportError("Please install openai: pip install openai")

    def validate_config(self):
        if not self.config.api_key and not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OpenAI API key required")

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        params = {
            "model": self.config.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            **self.config.extra_params,
            **kwargs,
        }

        response = self.client.chat.completions.create(**params)

        return LLMResponse(
            content=response.choices[0].message.content,
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            raw_response=response,
        )

    def generate_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        params = {
            "model": self.config.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "stream": True,
            **self.config.extra_params,
            **kwargs,
        }

        stream = self.client.chat.completions.create(**params)
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def count_tokens(self, text: str) -> int:
        try:
            import tiktoken

            encoding = tiktoken.encoding_for_model(self.config.model_name)
            return len(encoding.encode(text))
        except:
            # Rough estimation if tiktoken fails
            return len(text) // 4


class AnthropicLLM(BaseLLM):
    """Anthropic Claude API implementation"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            import anthropic

            self.client = anthropic.Anthropic(
                api_key=config.api_key or os.getenv("ANTHROPIC_API_KEY"),
                base_url=config.api_base,
                timeout=config.timeout,
            )
        except ImportError:
            raise ImportError("Please install anthropic: pip install anthropic")

    def validate_config(self):
        if not self.config.api_key and not os.getenv("ANTHROPIC_API_KEY"):
            raise ValueError("Anthropic API key required")

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        params = {
            "model": self.config.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            **self.config.extra_params,
            **kwargs,
        }

        response = self.client.messages.create(**params)

        return LLMResponse(
            content=response.content[0].text,
            model=response.model,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            raw_response=response,
        )

    def generate_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        params = {
            "model": self.config.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "stream": True,
            **self.config.extra_params,
            **kwargs,
        }

        with self.client.messages.stream(**params) as stream:
            for text in stream.text_stream:
                yield text

    def count_tokens(self, text: str) -> int:
        # Rough estimation for Claude
        return len(text) // 4


class OllamaLLM(BaseLLM):
    """Ollama local model implementation"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        import requests

        self.base_url = config.api_base or "http://localhost:11434"
        self.session = requests.Session()

    def validate_config(self):
        # Check if Ollama is running
        try:
            response = self.session.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
        except Exception as e:
            raise ConnectionError(f"Cannot connect to Ollama: {e}")

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        params = {
            "model": self.config.model_name,
            "prompt": prompt,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
            "stream": False,
            **self.config.extra_params,
            **kwargs,
        }

        response = self.session.post(
            f"{self.base_url}/api/generate", json=params, timeout=self.config.timeout
        )
        response.raise_for_status()
        data = response.json()

        return LLMResponse(
            content=data["response"],
            model=self.config.model_name,
            usage={
                "total_duration": data.get("total_duration"),
                "eval_duration": data.get("eval_duration"),
            },
            raw_response=data,
        )

    def generate_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        params = {
            "model": self.config.model_name,
            "prompt": prompt,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
            "stream": True,
            **self.config.extra_params,
            **kwargs,
        }

        response = self.session.post(
            f"{self.base_url}/api/generate",
            json=params,
            stream=True,
            timeout=self.config.timeout,
        )
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                data = json.loads(line)
                if "response" in data:
                    yield data["response"]

    def count_tokens(self, text: str) -> int:
        # Rough estimation
        return len(text) // 4


class HuggingFaceLLM(BaseLLM):
    """HuggingFace Transformers implementation"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            import torch

            self.tokenizer = AutoTokenizer.from_pretrained(config.model_name)
            self.model = AutoModelForCausalLM.from_pretrained(
                config.model_name,
                torch_dtype=(
                    torch.float16 if torch.cuda.is_available() else torch.float32
                ),
                device_map="auto",
            )
        except ImportError:
            raise ImportError("Please install transformers and torch")

    def validate_config(self):
        # Model loading validates itself
        pass

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        inputs = self.tokenizer(prompt, return_tensors="pt")

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                temperature=kwargs.get("temperature", self.config.temperature),
                do_sample=True,
                **self.config.extra_params,
                **kwargs,
            )

        response_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        # Remove the prompt from the response
        response_text = response_text[len(prompt) :].strip()

        return LLMResponse(
            content=response_text,
            model=self.config.model_name,
            usage={"tokens": len(outputs[0])},
        )

    def generate_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        # Simple implementation - for better streaming, use TextStreamer
        response = self.generate(prompt, **kwargs)
        words = response.content.split()
        for word in words:
            yield word + " "

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text))


# Template for custom implementations
class CustomLLM(BaseLLM):
    """Template for custom LLM implementations"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        # Initialize your custom model here
        # self.model = YourCustomModel(...)

    def validate_config(self):
        # Add your validation logic
        pass

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        # Implement your generation logic
        # response = self.model.generate(prompt, **kwargs)
        # return LLMResponse(content=response, model=self.config.model_name)
        raise NotImplementedError("Implement your custom generation logic")

    def generate_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        # Implement your streaming logic
        raise NotImplementedError("Implement your custom streaming logic")

    def count_tokens(self, text: str) -> int:
        # Implement your token counting logic
        return len(text) // 4  # Default estimation


class LLMFactory:
    """Factory class for creating LLM instances"""

    _providers = {
        LLMProvider.OPENAI: OpenAILLM,
        LLMProvider.ANTHROPIC: AnthropicLLM,
        LLMProvider.OLLAMA: OllamaLLM,
        LLMProvider.HUGGINGFACE: HuggingFaceLLM,
        LLMProvider.CUSTOM: CustomLLM,
    }

    @classmethod
    def create(cls, config: Union[LLMConfig, Dict[str, Any]]) -> BaseLLM:
        """Create an LLM instance from configuration"""
        if isinstance(config, dict):
            config = LLMConfig(**config)

        if config.provider not in cls._providers:
            raise ValueError(f"Unknown provider: {config.provider}")

        llm_class = cls._providers[config.provider]
        return llm_class(config)

    @classmethod
    def register_provider(cls, provider: LLMProvider, llm_class: type):
        """Register a new LLM provider"""
        cls._providers[provider] = llm_class


# Convenience wrapper class
class LLMWrapper:
    """High-level wrapper for easy LLM usage"""

    def __init__(self, config: Union[LLMConfig, Dict[str, Any]]):
        self.llm = LLMFactory.create(config)
        self.config = self.llm.config

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text response"""
        response = self.llm.generate(prompt, **kwargs)
        return response.content

    def generate_full(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate full response with metadata"""
        return self.llm.generate(prompt, **kwargs)

    def stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """Stream text response"""
        return self.llm.generate_stream(prompt, **kwargs)

    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        return self.llm.count_tokens(text)

    @classmethod
    def from_env(cls, provider: str = "openai", model: str = None):
        """Create wrapper from environment variables"""
        provider_enum = LLMProvider(provider.lower())

        # Default models
        default_models = {
            LLMProvider.OPENAI: "gpt-3.5-turbo",
            LLMProvider.ANTHROPIC: "claude-3-sonnet-20240229",
            LLMProvider.OLLAMA: "llama2",
            LLMProvider.HUGGINGFACE: "gpt2",
        }

        config = LLMConfig(
            provider=provider_enum,
            model_name=model or default_models.get(provider_enum, "default"),
        )

        return cls(config)


# Example usage
if __name__ == "__main__":
    # Example 1: Using OpenAI
    openai_config = LLMConfig(
        provider=LLMProvider.OPENAI,
        model_name="gpt-4.1-mini",
        temperature=0.7,
    )
    llm = LLMWrapper(openai_config)
    response = llm.generate("Hello, how are you?")
    print(response)
