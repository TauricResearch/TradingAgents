"""
LLM Factory for TradingAgents.

Provides unified interface for creating LLM instances from different providers
(OpenAI, Anthropic, Google, etc.) with consistent configuration.
"""

import os
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class LLMFactory:
    """Factory for creating LLM instances from different providers."""

    SUPPORTED_PROVIDERS = ["openai", "anthropic", "google"]

    @staticmethod
    def create_llm(
        provider: str,
        model: str,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        backend_url: Optional[str] = None,
        **kwargs
    ):
        """
        Create an LLM instance for the specified provider.

        Args:
            provider: LLM provider ("openai", "anthropic", "google")
            model: Model name (e.g., "gpt-4o", "claude-3-5-sonnet-20241022")
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            backend_url: Custom API endpoint (for OpenAI-compatible APIs)
            **kwargs: Additional provider-specific arguments

        Returns:
            LLM instance from the appropriate langchain provider

        Raises:
            ValueError: If provider is not supported or API key is missing
            ImportError: If required package is not installed

        Examples:
            >>> # OpenAI
            >>> llm = LLMFactory.create_llm("openai", "gpt-4o")

            >>> # Anthropic
            >>> llm = LLMFactory.create_llm("anthropic", "claude-3-5-sonnet-20241022")

            >>> # Google
            >>> llm = LLMFactory.create_llm("google", "gemini-pro")
        """
        provider = provider.lower()

        if provider not in LLMFactory.SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported LLM provider: {provider}. "
                f"Supported providers: {', '.join(LLMFactory.SUPPORTED_PROVIDERS)}"
            )

        if provider == "openai":
            return LLMFactory._create_openai_llm(
                model, temperature, max_tokens, backend_url, **kwargs
            )
        elif provider == "anthropic":
            return LLMFactory._create_anthropic_llm(
                model, temperature, max_tokens, **kwargs
            )
        elif provider == "google":
            return LLMFactory._create_google_llm(
                model, temperature, max_tokens, **kwargs
            )

    @staticmethod
    def _create_openai_llm(
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        backend_url: Optional[str],
        **kwargs
    ):
        """Create OpenAI LLM instance."""
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise ImportError(
                "langchain-openai is required for OpenAI models. "
                "Install with: pip install langchain-openai"
            )

        # Check API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required. "
                "Set it in your .env file or environment."
            )

        # Build configuration
        config = {
            "model": model,
            "temperature": temperature,
            **kwargs
        }

        if max_tokens:
            config["max_tokens"] = max_tokens

        if backend_url:
            config["base_url"] = backend_url

        logger.info(f"Creating OpenAI LLM: {model} (temp={temperature})")
        return ChatOpenAI(**config)

    @staticmethod
    def _create_anthropic_llm(
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        **kwargs
    ):
        """Create Anthropic (Claude) LLM instance."""
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise ImportError(
                "langchain-anthropic is required for Anthropic models. "
                "Install with: pip install langchain-anthropic"
            )

        # Check API key
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is required. "
                "Set it in your .env file or environment."
            )

        # Build configuration
        config = {
            "model": model,
            "temperature": temperature,
            "anthropic_api_key": api_key,
            **kwargs
        }

        if max_tokens:
            config["max_tokens"] = max_tokens
        else:
            # Claude requires max_tokens, use reasonable default
            config["max_tokens"] = 4096

        logger.info(f"Creating Anthropic LLM: {model} (temp={temperature})")
        return ChatAnthropic(**config)

    @staticmethod
    def _create_google_llm(
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        **kwargs
    ):
        """Create Google (Gemini) LLM instance."""
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            raise ImportError(
                "langchain-google-genai is required for Google models. "
                "Install with: pip install langchain-google-genai"
            )

        # Check API key
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY environment variable is required. "
                "Set it in your .env file or environment."
            )

        # Build configuration
        config = {
            "model": model,
            "temperature": temperature,
            "google_api_key": api_key,
            **kwargs
        }

        if max_tokens:
            config["max_output_tokens"] = max_tokens

        logger.info(f"Creating Google LLM: {model} (temp={temperature})")
        return ChatGoogleGenerativeAI(**config)

    @staticmethod
    def get_recommended_models(provider: str) -> Dict[str, str]:
        """
        Get recommended model names for a provider.

        Args:
            provider: LLM provider name

        Returns:
            Dictionary with model recommendations for different use cases

        Examples:
            >>> models = LLMFactory.get_recommended_models("anthropic")
            >>> print(models["deep_thinking"])  # claude-3-5-sonnet-20241022
        """
        recommendations = {
            "openai": {
                "deep_thinking": "o1-preview",  # Best reasoning
                "fast_thinking": "gpt-4o",      # Fast, capable
                "budget": "gpt-4o-mini",        # Cost-effective
                "legacy": "gpt-4-turbo"         # Previous generation
            },
            "anthropic": {
                "deep_thinking": "claude-3-5-sonnet-20241022",  # Best overall
                "fast_thinking": "claude-3-5-sonnet-20241022",  # Same (very fast)
                "budget": "claude-3-5-haiku-20241022",          # Cost-effective
                "legacy": "claude-3-opus-20240229"              # Previous best
            },
            "google": {
                "deep_thinking": "gemini-1.5-pro",    # Best reasoning
                "fast_thinking": "gemini-1.5-flash",  # Fastest
                "budget": "gemini-1.5-flash",         # Same as fast
                "legacy": "gemini-pro"                # Previous generation
            }
        }

        provider = provider.lower()
        if provider not in recommendations:
            raise ValueError(f"Unknown provider: {provider}")

        return recommendations[provider]

    @staticmethod
    def validate_provider_setup(provider: str) -> Dict[str, Any]:
        """
        Validate that a provider is properly configured.

        Args:
            provider: Provider to validate

        Returns:
            Dictionary with validation results

        Examples:
            >>> result = LLMFactory.validate_provider_setup("anthropic")
            >>> if result["valid"]:
            ...     print("Anthropic is configured!")
        """
        provider = provider.lower()

        result = {
            "provider": provider,
            "valid": False,
            "api_key_set": False,
            "package_installed": False,
            "errors": []
        }

        # Check package installation
        try:
            if provider == "openai":
                import langchain_openai
                result["package_installed"] = True
            elif provider == "anthropic":
                import langchain_anthropic
                result["package_installed"] = True
            elif provider == "google":
                import langchain_google_genai
                result["package_installed"] = True
        except ImportError as e:
            result["errors"].append(f"Package not installed: {e}")

        # Check API key
        key_env_vars = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY"
        }

        if provider in key_env_vars:
            env_var = key_env_vars[provider]
            if os.getenv(env_var):
                result["api_key_set"] = True
            else:
                result["errors"].append(f"{env_var} not set in environment")

        # Overall validation
        result["valid"] = result["package_installed"] and result["api_key_set"]

        return result


# Convenience function
def create_llm(provider: str = "openai", model: str = None, **kwargs):
    """
    Convenience wrapper for LLMFactory.create_llm().

    If model is not specified, uses recommended model for the provider.

    Examples:
        >>> llm = create_llm("anthropic")  # Uses Claude 3.5 Sonnet
        >>> llm = create_llm("openai", "gpt-4o")
    """
    if model is None:
        # Use recommended deep thinking model
        recommended = LLMFactory.get_recommended_models(provider)
        model = recommended["deep_thinking"]
        logger.info(f"No model specified, using recommended: {model}")

    return LLMFactory.create_llm(provider, model, **kwargs)
