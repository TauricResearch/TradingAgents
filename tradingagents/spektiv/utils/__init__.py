"""
TradingAgents utilities package.

This package provides utility functions and classes for the TradingAgents framework.
"""

from spektiv.utils.exceptions import (
    LLMRateLimitError,
    OpenAIRateLimitError,
    AnthropicRateLimitError,
    OpenRouterRateLimitError,
    from_provider_error,
)

from spektiv.utils.logging_config import (
    setup_dual_logger,
    sanitize_log_message,
)

from spektiv.utils.report_exporter import (
    format_metadata_frontmatter,
    create_report_with_frontmatter,
    generate_section_filename,
    save_json_metadata,
    generate_comprehensive_report,
)

__all__ = [
    "LLMRateLimitError",
    "OpenAIRateLimitError",
    "AnthropicRateLimitError",
    "OpenRouterRateLimitError",
    "from_provider_error",
    "setup_dual_logger",
    "sanitize_log_message",
    "format_metadata_frontmatter",
    "create_report_with_frontmatter",
    "generate_section_filename",
    "save_json_metadata",
    "generate_comprehensive_report",
]
