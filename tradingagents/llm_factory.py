"""
LLM Factory for creating AI model instances from different providers.

This module provides a unified interface for creating LLM instances from various
providers including OpenAI, Ollama, Anthropic, Google, and others.
"""

from typing import Any, Dict, Optional
import os


class LLMFactory:
    """Factory class for creating LLM instances from different providers."""
    
    @staticmethod
    def create_llm(
        provider: str,
        model: str,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs
    ):
        """
        Create an LLM instance based on the specified provider.
        
        Args:
            provider: The LLM provider (openai, ollama, anthropic, google, azure, etc.)
            model: The model name/identifier
            base_url: Optional custom base URL for API endpoints
            temperature: Model temperature setting (default: 0.7)
            **kwargs: Additional provider-specific parameters
            
        Returns:
            An initialized LLM instance compatible with LangChain
            
        Raises:
            ValueError: If the provider is not supported
            ImportError: If the required library for the provider is not installed
        """
        provider = provider.lower().strip()
        
        if provider in ["openai", "openrouter"]:
            return LLMFactory._create_openai_llm(model, base_url, temperature, **kwargs)
        elif provider == "ollama":
            return LLMFactory._create_ollama_llm(model, base_url, temperature, **kwargs)
        elif provider == "anthropic":
            return LLMFactory._create_anthropic_llm(model, base_url, temperature, **kwargs)
        elif provider == "google":
            return LLMFactory._create_google_llm(model, temperature, **kwargs)
        elif provider == "azure":
            return LLMFactory._create_azure_llm(model, base_url, temperature, **kwargs)
        elif provider == "huggingface":
            return LLMFactory._create_huggingface_llm(model, base_url, temperature, **kwargs)
        elif provider == "groq":
            return LLMFactory._create_groq_llm(model, temperature, **kwargs)
        elif provider == "together":
            return LLMFactory._create_together_llm(model, temperature, **kwargs)
        else:
            raise ValueError(
                f"Unsupported LLM provider: {provider}. "
                f"Supported providers: openai, ollama, anthropic, google, azure, "
                f"huggingface, groq, together, openrouter"
            )
    
    @staticmethod
    def _create_openai_llm(model: str, base_url: Optional[str], temperature: float, **kwargs):
        """Create an OpenAI-compatible LLM instance."""
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise ImportError(
                "langchain-openai is required for OpenAI provider. "
                "Install it with: pip install langchain-openai"
            )
        
        params = {
            "model": model,
            "temperature": temperature,
            **kwargs
        }
        
        if base_url:
            params["base_url"] = base_url
            
        return ChatOpenAI(**params)
    
    @staticmethod
    def _create_ollama_llm(model: str, base_url: Optional[str], temperature: float, **kwargs):
        """Create an Ollama LLM instance."""
        try:
            # Try the new langchain-ollama package first (supports tool binding)
            from langchain_ollama import ChatOllama
        except ImportError:
            try:
                # Fall back to langchain-community (older, may not support all features)
                from langchain_community.chat_models import ChatOllama
                import warnings
                warnings.warn(
                    "Using langchain-community for Ollama. For better compatibility, "
                    "install langchain-ollama: pip install langchain-ollama",
                    UserWarning
                )
            except ImportError:
                raise ImportError(
                    "langchain-ollama or langchain-community is required for Ollama provider. "
                    "Install with: pip install langchain-ollama (recommended) or pip install langchain-community"
                )
        
        params = {
            "model": model,
            "temperature": temperature,
            **kwargs
        }
        
        if base_url:
            params["base_url"] = base_url
        else:
            # Default Ollama endpoint
            params["base_url"] = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        
        # Use ChatOllama for chat-based interactions (compatible with LangChain chat models)
        return ChatOllama(**params)
    
    @staticmethod
    def _create_anthropic_llm(model: str, base_url: Optional[str], temperature: float, **kwargs):
        """Create an Anthropic Claude LLM instance."""
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise ImportError(
                "langchain-anthropic is required for Anthropic provider. "
                "Install it with: pip install langchain-anthropic"
            )
        
        params = {
            "model": model,
            "temperature": temperature,
            **kwargs
        }
        
        if base_url:
            params["base_url"] = base_url
            
        return ChatAnthropic(**params)
    
    @staticmethod
    def _create_google_llm(model: str, temperature: float, **kwargs):
        """Create a Google Generative AI LLM instance."""
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            raise ImportError(
                "langchain-google-genai is required for Google provider. "
                "Install it with: pip install langchain-google-genai"
            )
        
        params = {
            "model": model,
            "temperature": temperature,
            **kwargs
        }
        
        return ChatGoogleGenerativeAI(**params)
    
    @staticmethod
    def _create_azure_llm(model: str, base_url: Optional[str], temperature: float, **kwargs):
        """Create an Azure OpenAI LLM instance."""
        try:
            from langchain_openai import AzureChatOpenAI
        except ImportError:
            raise ImportError(
                "langchain-openai is required for Azure OpenAI provider. "
                "Install it with: pip install langchain-openai"
            )
        
        params = {
            "deployment_name": model,
            "temperature": temperature,
            **kwargs
        }
        
        if base_url:
            params["azure_endpoint"] = base_url
            
        return AzureChatOpenAI(**params)
    
    @staticmethod
    def _create_huggingface_llm(model: str, base_url: Optional[str], temperature: float, **kwargs):
        """Create a HuggingFace LLM instance."""
        try:
            from langchain_community.llms import HuggingFaceHub
        except ImportError:
            raise ImportError(
                "langchain-community is required for HuggingFace provider. "
                "Install it with: pip install langchain-community"
            )
        
        params = {
            "repo_id": model,
            "model_kwargs": {"temperature": temperature, **kwargs}
        }
        
        if base_url:
            params["huggingfacehub_api_url"] = base_url
            
        return HuggingFaceHub(**params)
    
    @staticmethod
    def _create_groq_llm(model: str, temperature: float, **kwargs):
        """Create a Groq LLM instance."""
        try:
            from langchain_groq import ChatGroq
        except ImportError:
            raise ImportError(
                "langchain-groq is required for Groq provider. "
                "Install it with: pip install langchain-groq"
            )
        
        params = {
            "model": model,
            "temperature": temperature,
            **kwargs
        }
        
        return ChatGroq(**params)
    
    @staticmethod
    def _create_together_llm(model: str, temperature: float, **kwargs):
        """Create a Together AI LLM instance."""
        try:
            from langchain_together import ChatTogether
        except ImportError:
            raise ImportError(
                "langchain-together is required for Together AI provider. "
                "Install it with: pip install langchain-together"
            )
        
        params = {
            "model": model,
            "temperature": temperature,
            **kwargs
        }
        
        return ChatTogether(**params)


def get_llm_instance(config: Dict[str, Any], model_type: str = "quick_think"):
    """
    Convenience function to create an LLM instance from a config dictionary.
    
    Args:
        config: Configuration dictionary with provider, model, and other settings
        model_type: Type of model to create ('quick_think' or 'deep_think')
        
    Returns:
        An initialized LLM instance
    """
    provider = config.get("llm_provider", "openai")
    
    if model_type == "deep_think":
        model = config.get("deep_think_llm", "gpt-4o")
    else:
        model = config.get("quick_think_llm", "gpt-4o-mini")
    
    base_url = config.get("backend_url")
    temperature = config.get("temperature", 0.7)
    
    # Extract any additional provider-specific settings
    llm_kwargs = config.get("llm_kwargs", {})
    
    return LLMFactory.create_llm(
        provider=provider,
        model=model,
        base_url=base_url,
        temperature=temperature,
        **llm_kwargs
    )
