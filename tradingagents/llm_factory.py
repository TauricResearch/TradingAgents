"""
LLM Factory for TradingAgents.

Provides unified interface for creating LLM instances from different providers
(OpenAI, Anthropic, Google, etc.) with consistent configuration.
"""

import os
from typing import Optional, Dict, Any, Union
import logging

logger = logging.getLogger(__name__)

# Type definitions for LLM instances
# Define LLMType as Union of supported LLM providers
try:
    from langchain_openai import ChatOpenAI
    from langchain_anthropic import ChatAnthropic
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    # Fallback imports not available during type checking
    ChatOpenAI = Any  # type: ignore
    ChatAnthropic = Any  # type: ignore
    ChatGoogleGenerativeAI = Any  # type: ignore

# LLMType union for return type annotations
LLMType = Union[ChatOpenAI, ChatAnthropic, ChatGoogleGenerativeAI]


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
    ) -> LLMType:
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
            error_msg = (f"Unsupported LLM provider: {provider}. "
                        f"Supported providers: {', '.join(LLMFactory.SUPPORTED_PROVIDERS)}")
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info("Creating LLM: provider=%s, model=%s, temperature=%.2f",
                   provider, model, temperature)

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
        else:
            # This should never be reached due to provider validation above
            logger.error("Unsupported provider after validation: %s", provider)
            raise ValueError(f"Unsupported provider: {provider}")

    @staticmethod
    def _create_openai_llm(
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        backend_url: Optional[str],
        **kwargs
    ) -> LLMType:
        """
        Create OpenAI LLM instance with specified configuration.

        Args:
            model: OpenAI model name (e.g., "gpt-4o", "gpt-4-turbo")
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            backend_url: Optional custom API endpoint for OpenAI-compatible APIs
            **kwargs: Additional provider-specific arguments

        Returns:
            Configured ChatOpenAI instance

        Raises:
            ImportError: If langchain-openai package not installed
            ValueError: If OPENAI_API_KEY not configured
        """
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as e:
            logger.error("Failed to import langchain_openai: %s", str(e))
            raise ImportError(
                "langchain-openai is required for OpenAI models. "
                "Install with: pip install langchain-openai"
            )

        # Check API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY environment variable not set")
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
            logger.debug("Using custom backend URL for OpenAI: %s", backend_url)

        logger.info("Creating OpenAI LLM: model=%s, temperature=%.2f, max_tokens=%s",
                   model, temperature, max_tokens)
        logger.debug("OpenAI LLM config: %s", config)
        return ChatOpenAI(**config)

    @staticmethod
    def _create_anthropic_llm(
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        **kwargs
    ) -> LLMType:
        """
        Create Anthropic (Claude) LLM instance with specified configuration.

        Args:
            model: Anthropic model name (e.g., "claude-3-5-sonnet-20241022")
            temperature: Sampling temperature (0.0 to 1.0 for Claude)
            max_tokens: Maximum tokens to generate (defaults to 4096 for Claude)
            **kwargs: Additional provider-specific arguments

        Returns:
            Configured ChatAnthropic instance

        Raises:
            ImportError: If langchain-anthropic package not installed
            ValueError: If ANTHROPIC_API_KEY not configured
        """
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as e:
            logger.error("Failed to import langchain_anthropic: %s", str(e))
            raise ImportError(
                "langchain-anthropic is required for Anthropic models. "
                "Install with: pip install langchain-anthropic"
            )

        # Check API key
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("ANTHROPIC_API_KEY environment variable not set")
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
            logger.debug("Using default max_tokens for Claude: 4096")

        logger.info("Creating Anthropic LLM: model=%s, temperature=%.2f, max_tokens=%d",
                   model, temperature, config["max_tokens"])
        logger.debug("Anthropic LLM config keys: %s", list(config.keys()))
        return ChatAnthropic(**config)

    @staticmethod
    def _create_google_llm(
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        **kwargs
    ) -> LLMType:
        """
        Create Google (Gemini) LLM instance with specified configuration.

        Args:
            model: Google model name (e.g., "gemini-1.5-pro", "gemini-1.5-flash")
            temperature: Sampling temperature (0.0 to 2.0 for Gemini)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific arguments

        Returns:
            Configured ChatGoogleGenerativeAI instance

        Raises:
            ImportError: If langchain-google-genai package not installed
            ValueError: If GOOGLE_API_KEY not configured
        """
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as e:
            logger.error("Failed to import langchain_google_genai: %s", str(e))
            raise ImportError(
                "langchain-google-genai is required for Google models. "
                "Install with: pip install langchain-google-genai"
            )

        # Check API key
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.error("GOOGLE_API_KEY environment variable not set")
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

        logger.info("Creating Google LLM: model=%s, temperature=%.2f, max_tokens=%s",
                   model, temperature, max_tokens)
        logger.debug("Google LLM config keys: %s", list(config.keys()))
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

        Checks if the required package is installed and API key is configured
        for the specified provider.

        Args:
            provider: Provider to validate (openai, anthropic, google)

        Returns:
            Dictionary with validation results containing:
            - provider: Provider name
            - valid: Overall validation status (True if ready to use)
            - api_key_set: Whether API key environment variable is set
            - package_installed: Whether required langchain package is installed
            - errors: List of validation errors encountered

        Examples:
            >>> result = LLMFactory.validate_provider_setup("anthropic")
            >>> if result["valid"]:
            ...     print("Anthropic is properly configured!")
            >>> else:
            ...     for error in result["errors"]:
            ...         print(error)
        """
        provider = provider.lower()
        logger.debug("Validating provider setup: %s", provider)

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
                logger.debug("langchain_openai package found")
            elif provider == "anthropic":
                import langchain_anthropic
                result["package_installed"] = True
                logger.debug("langchain_anthropic package found")
            elif provider == "google":
                import langchain_google_genai
                result["package_installed"] = True
                logger.debug("langchain_google_genai package found")
        except ImportError as e:
            error_msg = f"Package not installed: {e}"
            result["errors"].append(error_msg)
            logger.warning("Package check failed: %s", error_msg)

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
                logger.debug("%s environment variable is set", env_var)
            else:
                error_msg = f"{env_var} not set in environment"
                result["errors"].append(error_msg)
                logger.warning("API key not found: %s", error_msg)

        # Overall validation
        result["valid"] = result["package_installed"] and result["api_key_set"]
        logger.info("Provider validation for %s: valid=%s, errors=%d",
                   provider, result["valid"], len(result["errors"]))

        return result


# Convenience function
def create_llm(provider: str = "openai", model: Optional[str] = None, **kwargs) -> LLMType:
    """
    Convenience wrapper for LLMFactory.create_llm() with smart defaults.

    If model is not specified, uses the recommended best-in-class model for
    the provider (optimized for deep thinking and complex reasoning).

    Args:
        provider: LLM provider (default: "openai")
            - "openai": Uses o1-preview as default
            - "anthropic": Uses Claude 3.5 Sonnet as default
            - "google": Uses Gemini 1.5 Pro as default
        model: Specific model to use. If None, uses provider's recommended model
        **kwargs: Additional arguments to pass to LLMFactory.create_llm()

    Returns:
        Configured LLM instance

    Raises:
        ValueError: If provider is not supported or API key is missing
        ImportError: If required package not installed

    Examples:
        >>> llm = create_llm("anthropic")  # Uses Claude 3.5 Sonnet
        >>> llm = create_llm("openai", "gpt-4o")  # Uses GPT-4O
        >>> llm = create_llm("google", "gemini-1.5-flash")  # Fast Gemini
    """
    if model is None:
        # Use recommended deep thinking model
        logger.debug("No model specified for %s, using recommended default", provider)
        try:
            recommended = LLMFactory.get_recommended_models(provider)
            model = recommended["deep_thinking"]
            logger.info("Using recommended model for %s: %s", provider, model)
        except ValueError as e:
            logger.error("Failed to get recommended model: %s", str(e))
            raise

    return LLMFactory.create_llm(provider, model, **kwargs)
