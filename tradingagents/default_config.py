# Legacy compatibility - import from new config module
from .config import DEFAULT_CONFIG

# Re-export for backward compatibility
__all__ = ["DEFAULT_CONFIG"]
