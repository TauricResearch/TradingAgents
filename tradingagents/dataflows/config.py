from copy import deepcopy

import tradingagents.default_config as default_config

# Use default config but allow it to be overridden
_config: dict | None = None


def initialize_config():
    """Initialize the configuration with default values."""
    global _config
    if _config is None:
        _config = deepcopy(default_config.DEFAULT_CONFIG)


def set_config(config: dict):
    """Update the configuration with custom values.

    Dict-valued keys (e.g. ``data_vendors``) are merged one level deep so a
    partial update like ``{"data_vendors": {"core_stock_apis": "alpha_vantage"}}``
    keeps the other nested keys from the default; scalar keys are replaced.
    """
    global _config
    initialize_config()
    incoming = deepcopy(config)
    for key, value in incoming.items():
        if key == "research_symbol_aliases":
            # This mapping is per experiment. Merging would let a masked ticker
            # silently survive into a later ordinary run.
            _config[key] = value
        elif isinstance(value, dict) and isinstance(_config.get(key), dict):
            _config[key].update(value)
        else:
            _config[key] = value


def get_config() -> dict:
    """Get the current configuration."""
    if _config is None:
        initialize_config()
    return deepcopy(_config)


def resolve_data_symbol(symbol: str) -> str:
    """Resolve an LLM-visible research alias to the real vendor symbol."""
    mapping = get_config().get("research_symbol_aliases", {})
    normalized = {str(alias).upper(): real for alias, real in mapping.items()}
    if not normalized:
        return symbol
    try:
        return normalized[symbol.upper()]
    except KeyError as exc:
        raise ValueError(
            f"symbol {symbol!r} is not an allowed research alias"
        ) from exc


def mask_data_symbol(text: str, visible_symbol: str, real_symbol: str) -> str:
    """Keep raw vendor ticker labels from defeating the ticker-mask control."""
    if visible_symbol.upper() == real_symbol.upper():
        return text
    import re

    return re.sub(
        rf"(?<![A-Za-z0-9]){re.escape(real_symbol)}(?![A-Za-z0-9])",
        visible_symbol,
        text,
        flags=re.IGNORECASE,
    )


# Initialize with default config
initialize_config()
