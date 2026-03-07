"""Configuration validation for the TradingAgents framework.

This module provides validation functions to ensure configuration
settings are correct before runtime.
"""

import os
from typing import Any

# Valid LLM providers
VALID_PROVIDERS = ["openai", "anthropic", "google", "xai", "ollama", "openrouter"]

# Valid data vendors
VALID_DATA_VENDORS = ["yfinance", "alpha_vantage"]

# Required API key environment variables by provider
PROVIDER_API_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "xai": "XAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def validate_config(config: dict[str, Any]) -> list[str]:
    """Validate configuration dictionary.

    Args:
        config: Configuration dictionary to validate.

    Returns:
        List of validation error messages (empty if valid).

    Example:
        >>> errors = validate_config(config)
        >>> if errors:
        ...     print("Configuration errors:", errors)
    """
    errors = []

    # Validate LLM provider
    provider = config.get("llm_provider", "").lower()
    if provider not in VALID_PROVIDERS:
        errors.append(
            f"Invalid llm_provider: '{provider}'. Must be one of {VALID_PROVIDERS}"
        )

    # Validate deep_think_llm
    if not config.get("deep_think_llm"):
        errors.append("deep_think_llm is required")

    # Validate quick_think_llm
    if not config.get("quick_think_llm"):
        errors.append("quick_think_llm is required")

    # Validate data vendors
    data_vendors = config.get("data_vendors", {})
    for category, vendor in data_vendors.items():
        if vendor not in VALID_DATA_VENDORS:
            errors.append(
                f"Invalid data vendor for {category}: '{vendor}'. "
                f"Must be one of {VALID_DATA_VENDORS}"
            )

    # Validate tool vendors
    tool_vendors = config.get("tool_vendors", {})
    for tool, vendor in tool_vendors.items():
        if vendor not in VALID_DATA_VENDORS:
            errors.append(
                f"Invalid tool vendor for {tool}: '{vendor}'. "
                f"Must be one of {VALID_DATA_VENDORS}"
            )

    # Validate numeric settings
    max_debate_rounds = config.get("max_debate_rounds", 1)
    if not isinstance(max_debate_rounds, int) or max_debate_rounds < 1:
        errors.append("max_debate_rounds must be a positive integer")

    max_risk_discuss_rounds = config.get("max_risk_discuss_rounds", 1)
    if not isinstance(max_risk_discuss_rounds, int) or max_risk_discuss_rounds < 1:
        errors.append("max_risk_discuss_rounds must be a positive integer")

    max_recur_limit = config.get("max_recur_limit", 100)
    if not isinstance(max_recur_limit, int) or max_recur_limit < 1:
        errors.append("max_recur_limit must be a positive integer")

    return errors


def validate_api_keys(config: dict[str, Any]) -> list[str]:
    """Validate that required API keys are set for the configured provider.

    Args:
        config: Configuration dictionary containing llm_provider.

    Returns:
        List of validation error messages (empty if valid).

    Example:
        >>> errors = validate_api_keys(config)
        >>> if errors:
        ...     print("Missing API keys:", errors)
    """
    errors = []

    provider = config.get("llm_provider", "").lower()
    env_key = PROVIDER_API_KEYS.get(provider)

    if env_key and not os.environ.get(env_key):
        errors.append(f"{env_key} not set for {provider} provider")

    # Check for Alpha Vantage key if using alpha_vantage vendor
    data_vendors = config.get("data_vendors", {})
    tool_vendors = config.get("tool_vendors", {})

    uses_alpha_vantage = (
        any(v == "alpha_vantage" for v in data_vendors.values()) or
        any(v == "alpha_vantage" for v in tool_vendors.values())
    )

    if uses_alpha_vantage and not os.environ.get("ALPHA_VANTAGE_API_KEY"):
        errors.append("ALPHA_VANTAGE_API_KEY not set but alpha_vantage vendor is configured")

    return errors


def validate_config_full(config: dict[str, Any]) -> list[str]:
    """Perform full configuration validation including API keys.

    Args:
        config: Configuration dictionary to validate.

    Returns:
        List of all validation error messages (empty if valid).

    Example:
        >>> errors = validate_config_full(config)
        >>> if errors:
        ...     for error in errors:
        ...         print(f"Error: {error}")
        ...     sys.exit(1)
    """
    errors = validate_config(config)
    errors.extend(validate_api_keys(config))
    return errors


def get_validation_report(config: dict[str, Any]) -> str:
    """Get a human-readable validation report.

    Args:
        config: Configuration dictionary to validate.

    Returns:
        Formatted string with validation results.

    Example:
        >>> report = get_validation_report(config)
        >>> print(report)
    """
    errors = validate_config_full(config)

    lines = ["Configuration Validation Report", "=" * 40]

    # Show configuration summary
    lines.append(f"\nLLM Provider: {config.get('llm_provider', 'not set')}")
    lines.append(f"Deep Think LLM: {config.get('deep_think_llm', 'not set')}")
    lines.append(f"Quick Think LLM: {config.get('quick_think_llm', 'not set')}")
    lines.append(f"Max Debate Rounds: {config.get('max_debate_rounds', 'not set')}")
    lines.append(f"Max Risk Discuss Rounds: {config.get('max_risk_discuss_rounds', 'not set')}")

    data_vendors = config.get("data_vendors", {})
    if data_vendors:
        lines.append("\nData Vendors:")
        for category, vendor in data_vendors.items():
            lines.append(f"  {category}: {vendor}")

    if errors:
        lines.append("\nValidation Errors:")
        for error in errors:
            lines.append(f"  - {error}")
    else:
        lines.append("\n✓ Configuration is valid")

    return "\n".join(lines)
