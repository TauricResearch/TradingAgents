"""
Universal LLM Wrapper
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
    GOOGLE = "google"
    HUGGINGFACE = "huggingface"
    OLLAMA = "ollama"
    CUSTOM = "custom"


@dataclass
class LLMConfig:
    """Configuration for LLM instances"""

    provider: Union[LLMProvider, str]  # Accept both enum and string
    model_name: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    timeout: int = 60
    extra_params: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra_params is None:
            self.extra_params = {}
        
        # Convert string provider to enum if needed
        if isinstance(self.provider, str):
            try:
                self.provider = LLMProvider(self.provider.lower())
            except ValueError:
                valid_providers = [p.value for p in LLMProvider]
                raise ValueError(f"Invalid provider '{self.provider}'. Valid providers: {valid_providers}")


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
            **self.config.extra_params,
            **kwargs,
        }

        # Only add temperature if specified
        temperature = kwargs.get("temperature", self.config.temperature)
        if temperature is not None:
            params["temperature"] = temperature

        # Only add max_tokens if specified
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        if max_tokens is not None:
            params["max_tokens"] = max_tokens

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
            "stream": True,
            **self.config.extra_params,
            **kwargs,
        }

        # Only add temperature if specified
        temperature = kwargs.get("temperature", self.config.temperature)
        if temperature is not None:
            params["temperature"] = temperature

        # Only add max_tokens if specified
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        if max_tokens is not None:
            params["max_tokens"] = max_tokens

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
            **self.config.extra_params,
            **kwargs,
        }

        # Anthropic REQUIRES max_tokens - set default if not provided
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        if max_tokens is None:
            max_tokens = 4096  # Default value for Anthropic
        params["max_tokens"] = max_tokens

        # Only add temperature if specified
        temperature = kwargs.get("temperature", self.config.temperature)
        if temperature is not None:
            params["temperature"] = temperature

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
            "stream": True,
            **self.config.extra_params,
            **kwargs,
        }

        # Anthropic REQUIRES max_tokens - set default if not provided
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        if max_tokens is None:
            max_tokens = 4096  # Default value for Anthropic
        params["max_tokens"] = max_tokens

        # Only add temperature if specified
        temperature = kwargs.get("temperature", self.config.temperature)
        if temperature is not None:
            params["temperature"] = temperature

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
            "stream": False,
            **self.config.extra_params,
            **kwargs,
        }

        # Only add temperature if specified
        temperature = kwargs.get("temperature", self.config.temperature)
        if temperature is not None:
            params["temperature"] = temperature

        # Only add num_predict (max_tokens equivalent) if specified
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        if max_tokens is not None:
            params["num_predict"] = max_tokens
            # Remove max_tokens from params if it was in kwargs
            params.pop("max_tokens", None)

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
            "stream": True,
            **self.config.extra_params,
            **kwargs,
        }

        # Only add temperature if specified
        temperature = kwargs.get("temperature", self.config.temperature)
        if temperature is not None:
            params["temperature"] = temperature

        # Only add num_predict (max_tokens equivalent) if specified
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        if max_tokens is not None:
            params["num_predict"] = max_tokens
            # Remove max_tokens from params if it was in kwargs
            params.pop("max_tokens", None)

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


class GoogleLLM(BaseLLM):
    """Google Gemini API implementation using OpenAI compatibility"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            import openai

            # Use Google's OpenAI-compatible endpoint
            self.client = openai.OpenAI(
                api_key=config.api_key
                or os.getenv("GOOGLE_API_KEY")
                or os.getenv("GEMINI_API_KEY"),
                base_url=config.api_base
                or "https://generativelanguage.googleapis.com/v1beta/openai/",
                timeout=config.timeout,
            )
        except ImportError:
            raise ImportError("Please install openai: pip install openai")

    def validate_config(self):
        if (
            not self.config.api_key
            and not os.getenv("GOOGLE_API_KEY")
            and not os.getenv("GEMINI_API_KEY")
        ):
            raise ValueError(
                "Google/Gemini API key required (set GOOGLE_API_KEY or GEMINI_API_KEY)"
            )

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        # Build parameters - similar to OpenAI
        params = {
            "model": self.config.model_name,
            "messages": [{"role": "user", "content": prompt}],
        }

        # Only add temperature if specified
        temperature = kwargs.get("temperature", self.config.temperature)
        if temperature is not None:
            params["temperature"] = temperature

        # Only add max_tokens if specified
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        if max_tokens is not None:
            params["max_tokens"] = max_tokens

        # Add any extra parameters from config
        if self.config.extra_params:
            params.update(self.config.extra_params)

        # Add reasoning_effort for Gemini 2.5 models if specified
        if "reasoning_effort" in kwargs:
            params["reasoning_effort"] = kwargs["reasoning_effort"]

        # Handle extra_body for advanced features
        if "extra_body" in kwargs:
            params["extra_body"] = kwargs["extra_body"]

        # Override with any additional kwargs
        params.update(
            {
                k: v
                for k, v in kwargs.items()
                if k
                not in ["temperature", "max_tokens", "reasoning_effort", "extra_body"]
            }
        )

        response = self.client.chat.completions.create(**params)

        return LLMResponse(
            content=response.choices[0].message.content,
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": (
                    response.usage.completion_tokens if response.usage else 0
                ),
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
            raw_response=response,
        )

    def generate_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        params = {
            "model": self.config.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }

        # Only add temperature if specified
        temperature = kwargs.get("temperature", self.config.temperature)
        if temperature is not None:
            params["temperature"] = temperature

        # Only add max_tokens if specified
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        if max_tokens is not None:
            params["max_tokens"] = max_tokens

        # Add any extra parameters from config
        if self.config.extra_params:
            params.update(self.config.extra_params)

        # Add reasoning_effort for Gemini 2.5 models if specified
        if "reasoning_effort" in kwargs:
            params["reasoning_effort"] = kwargs["reasoning_effort"]

        # Handle extra_body for advanced features
        if "extra_body" in kwargs:
            params["extra_body"] = kwargs["extra_body"]

        # Override with any additional kwargs
        params.update(
            {
                k: v
                for k, v in kwargs.items()
                if k
                not in [
                    "temperature",
                    "max_tokens",
                    "reasoning_effort",
                    "extra_body",
                    "stream",
                ]
            }
        )

        stream = self.client.chat.completions.create(**params)
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def count_tokens(self, text: str) -> int:
        # For Gemini models, use a rough estimation similar to GPT models
        # You could also make an API call to count tokens if needed
        try:
            import tiktoken

            # Use cl100k_base encoding as a reasonable approximation
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except:
            # Fallback to rough estimation
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

        # Build generation parameters
        gen_params = {"do_sample": True, **self.config.extra_params, **kwargs}

        # Only add temperature if specified
        temperature = kwargs.get("temperature", self.config.temperature)
        if temperature is not None:
            gen_params["temperature"] = temperature

        # Only add max_new_tokens if specified
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        if max_tokens is not None:
            gen_params["max_new_tokens"] = max_tokens
            # Remove max_tokens from gen_params if it was in kwargs
            gen_params.pop("max_tokens", None)

        with torch.no_grad():
            outputs = self.model.generate(**inputs, **gen_params)

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
        LLMProvider.GOOGLE: GoogleLLM,
        LLMProvider.OLLAMA: OllamaLLM,
        LLMProvider.HUGGINGFACE: HuggingFaceLLM,
        LLMProvider.CUSTOM: CustomLLM,
    }

    @classmethod
    def create(cls, config: Union[LLMConfig, Dict[str, Any]]) -> BaseLLM:
        """Create an LLM instance from configuration"""
        if isinstance(config, dict):
            # Convert string provider to enum before creating LLMConfig
            if 'provider' in config and isinstance(config['provider'], str):
                try:
                    config = config.copy()  # Don't modify original dict
                    config['provider'] = LLMProvider(config['provider'].lower())
                except ValueError:
                    valid_providers = [p.value for p in LLMProvider]
                    raise ValueError(f"Invalid provider '{config['provider']}'. Valid providers: {valid_providers}")
            
            config = LLMConfig(**config)

        # Ensure provider is an enum by this point
        if not isinstance(config.provider, LLMProvider):
            valid_providers = [p.value for p in LLMProvider]
            raise ValueError(f"Provider must be LLMProvider enum or valid string. Valid providers: {valid_providers}")

        if config.provider not in cls._providers:
            valid_providers = [p.value for p in LLMProvider]
            raise ValueError(f"Unknown provider: {config.provider}. Valid providers: {valid_providers}")

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
        # Convert string to enum with better error handling
        try:
            provider_enum = LLMProvider(provider.lower())
        except ValueError:
            valid_providers = [p.value for p in LLMProvider]
            raise ValueError(f"Invalid provider '{provider}'. Valid providers: {valid_providers}")

        # Default models
        default_models = {
            LLMProvider.OPENAI: "gpt-3.5-turbo",
            LLMProvider.ANTHROPIC: "claude-3-sonnet-20240229",
            LLMProvider.GOOGLE: "gemini-1.5-flash",
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
    # All of these will now work with your updated code:

    # 1. Dictionary with string provider (your original use case)
    config_dict = {
        "provider": "anthropic",  # ✅ String works!
        "model_name": "claude-3-5-sonnet-latest",
    }
    llm2 = LLMWrapper(config_dict)
    llm2_response = llm2.generate("What is the meaning of life?")
    print(llm2_response)

    # 2. Dictionary with enum provider
    config_dict_enum = {
        "provider": LLMProvider.ANTHROPIC,  # ✅ Enum also works
        "model_name": "claude-3.5-sonnet",
    }
    llm3 = LLMWrapper(config_dict_enum)

    # 3. Direct LLMConfig with string
    config_direct = LLMConfig(
        provider="openai",  # ✅ String converted automatically
        model_name="gpt-4o-mini",
        temperature=0.7,
    )
    llm4 = LLMWrapper(config_direct)
    print(llm4.generate("Tell me a joke"))
    

    # 4. Direct LLMConfig with enum
    config_direct_enum = LLMConfig(
        provider=LLMProvider.GOOGLE,  # ✅ Enum also works
        model_name="gemini-1.5-flash"
    )
    llm5 = LLMWrapper(config_direct_enum)

    # 5. from_env method with string
    llm6 = LLMWrapper.from_env(provider="anthropic", model="claude-3.5-sonnet")

    # 6. Case insensitive strings
    config_case = {
        "provider": "OPENAI",  # ✅ Uppercase works
        "model_name": "gpt-4",
    }
    llm7 = LLMWrapper(config_case)

    config_case2 = {
        "provider": "AnThRoPiC",  # ✅ Mixed case works
        "model_name": "claude-3.5-sonnet",
    }
    llm8 = LLMWrapper(config_case2)

    # 7. Error handling example
    try:
        bad_config = {
            "provider": "invalid_provider",  # ❌ Will give helpful error
            "model_name": "some-model",
        }
        llm_bad = LLMWrapper(bad_config)
    except ValueError as e:
        print(f"Error: {e}")
        # Output: Invalid provider 'invalid_provider'. Valid providers: ['openai', 'anthropic', 'google', 'huggingface', 'ollama', 'custom']

    print("All configurations work now!")
