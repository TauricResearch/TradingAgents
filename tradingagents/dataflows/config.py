import tradingagents.default_config as default_config
from typing import Dict, Optional

# Use default config but allow it to be overridden
_config: Optional[Dict] = None
DATA_DIR: Optional[str] = None

# Local LLM providers that don't support OpenAI's web_search_preview
LOCAL_LLM_PROVIDERS = ["ollama", "lm studio"]
# Methods that require OpenAI's web_search_preview tool
OPENAI_ONLY_METHODS = ["get_news", "get_global_news", "get_fundamentals"]


def validate_config(config: Dict):
    """Validate configuration and warn about incompatible settings."""
    llm_provider = config.get("llm_provider", "").lower()

    if llm_provider in LOCAL_LLM_PROVIDERS:
        # Check data vendors
        data_vendors = config.get("data_vendors", {})
        tool_vendors = config.get("tool_vendors", {})

        warnings = []
        if data_vendors.get("news_data") == "openai":
            warnings.append("data_vendors.news_data")
        if data_vendors.get("fundamental_data") == "openai":
            warnings.append("data_vendors.fundamental_data")

        for method in OPENAI_ONLY_METHODS:
            if tool_vendors.get(method) == "openai":
                warnings.append(f"tool_vendors.{method}")

        if warnings:
            print(f"WARNING: Using local LLM provider '{llm_provider}' with 'openai' data vendors.")
            print(f"  The following settings use OpenAI's web_search_preview which is not available locally:")
            for w in warnings:
                print(f"    - {w}")
            print(f"  Recommendation: Change these to 'alpha_vantage', 'google', or 'local'.")


def initialize_config():
    """Initialize the configuration with default values."""
    global _config, DATA_DIR
    if _config is None:
        _config = default_config.DEFAULT_CONFIG.copy()
        DATA_DIR = _config["data_dir"]


def set_config(config: Dict):
    """Update the configuration with custom values."""
    global _config, DATA_DIR
    if _config is None:
        _config = default_config.DEFAULT_CONFIG.copy()
    _config.update(config)
    DATA_DIR = _config["data_dir"]
    validate_config(_config)


def get_config() -> Dict:
    """Get the current configuration."""
    if _config is None:
        initialize_config()
    return _config.copy()


# Initialize with default config
initialize_config()
