import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # dotenv not installed, skip loading
    pass


@dataclass
class TradingAgentsConfig:
    """Configuration for TradingAgents system with type safety and validation."""

    # Directory settings
    project_dir: str = field(
        default_factory=lambda: str(Path(__file__).parent.absolute())
    )
    results_dir: str = field(
        default_factory=lambda: os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results")
    )
    data_dir: str = "/Users/yluo/Documents/Code/ScAI/FR1-data"
    data_cache_dir: str = field(init=False)

    # LLM settings
    llm_provider: Literal["openai", "anthropic", "google", "ollama", "openrouter"] = (
        "openai"
    )
    deep_think_llm: str = "o4-mini"
    quick_think_llm: str = "gpt-4o-mini"
    news_sentiment_llm: str = "openai/gpt-oss-120b"
    news_embedding_llm: str = "qwen/qwen3-embedding-8b"
    backend_url: str = "https://api.openai.com/v1"

    # Debate and discussion settings
    max_debate_rounds: int = 1
    max_risk_discuss_rounds: int = 1
    max_recur_limit: int = 100

    # Tool settings
    online_tools: bool = True

    # Data retrieval settings
    default_lookback_days: int = 30
    default_ta_lookback_days: int = 30

    # Database settings
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", "postgresql://localhost:5432/tradingagents"
        )
    )

    def __post_init__(self):
        """Set computed fields after initialization."""
        self.data_cache_dir = os.path.join(self.project_dir, "dataflows/data_cache")

    @classmethod
    def _get_llm_provider(
        cls, default: str = "openai"
    ) -> Literal["openai", "anthropic", "google", "ollama", "openrouter"]:
        """Get and validate LLM provider from environment."""
        valid_providers = ["openai", "anthropic", "google", "ollama", "openrouter"]
        provider = os.getenv("LLM_PROVIDER", default)

        if provider not in valid_providers:
            raise ValueError(
                f"Invalid LLM_PROVIDER: {provider}. Must be one of: {', '.join(valid_providers)}"
            )

        return cast(
            "Literal['openai', 'anthropic', 'google', 'ollama', 'openrouter']", provider
        )

    @classmethod
    def from_env(cls) -> "TradingAgentsConfig":
        """Create config with environment variable overrides."""
        return cls(
            results_dir=os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
            data_dir=os.getenv(
                "TRADINGAGENTS_DATA_DIR", "/Users/yluo/Documents/Code/ScAI/FR1-data"
            ),
            llm_provider=cls._get_llm_provider(),
            deep_think_llm=os.getenv("DEEP_THINK_LLM", "o4-mini"),
            quick_think_llm=os.getenv("QUICK_THINK_LLM", "gpt-4o-mini"),
            news_sentiment_llm=os.getenv("NEWS_SENTIMENT_LLM", "openai/gpt-oss-120b"),
            news_embedding_llm=os.getenv(
                "NEWS_EMBEDDING_LLM", "qwen/qwen3-embedding-8b"
            ),
            backend_url=os.getenv("BACKEND_URL", "https://api.openai.com/v1"),
            max_debate_rounds=int(os.getenv("MAX_DEBATE_ROUNDS", "1")),
            max_risk_discuss_rounds=int(os.getenv("MAX_RISK_DISCUSS_ROUNDS", "1")),
            max_recur_limit=int(os.getenv("MAX_RECUR_LIMIT", "100")),
            online_tools=os.getenv("ONLINE_TOOLS", "true").lower() == "true",
            default_lookback_days=int(os.getenv("DEFAULT_LOOKBACK_DAYS", "30")),
            default_ta_lookback_days=int(os.getenv("DEFAULT_TA_LOOKBACK_DAYS", "30")),
            database_url=os.getenv(
                "DATABASE_URL", "postgresql://localhost:5432/tradingagents"
            ),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for backward compatibility."""
        return {
            "project_dir": self.project_dir,
            "results_dir": self.results_dir,
            "data_dir": self.data_dir,
            "data_cache_dir": self.data_cache_dir,
            "llm_provider": self.llm_provider,
            "deep_think_llm": self.deep_think_llm,
            "quick_think_llm": self.quick_think_llm,
            "news_sentiment_llm": self.news_sentiment_llm,
            "news_embedding_llm": self.news_embedding_llm,
            "backend_url": self.backend_url,
            "max_debate_rounds": self.max_debate_rounds,
            "max_risk_discuss_rounds": self.max_risk_discuss_rounds,
            "max_recur_limit": self.max_recur_limit,
            "online_tools": self.online_tools,
            "default_lookback_days": self.default_lookback_days,
            "default_ta_lookback_days": self.default_ta_lookback_days,
            "database_url": self.database_url,
        }

    def copy(self) -> "TradingAgentsConfig":
        """Create a copy of the configuration."""
        return TradingAgentsConfig(
            project_dir=self.project_dir,
            results_dir=self.results_dir,
            data_dir=self.data_dir,
            llm_provider=self.llm_provider,
            deep_think_llm=self.deep_think_llm,
            quick_think_llm=self.quick_think_llm,
            news_sentiment_llm=self.news_sentiment_llm,
            news_embedding_llm=self.news_embedding_llm,
            backend_url=self.backend_url,
            max_debate_rounds=self.max_debate_rounds,
            max_risk_discuss_rounds=self.max_risk_discuss_rounds,
            max_recur_limit=self.max_recur_limit,
            online_tools=self.online_tools,
            default_lookback_days=self.default_lookback_days,
            default_ta_lookback_days=self.default_ta_lookback_days,
            database_url=self.database_url,
        )


# For backward compatibility, create a default instance
DEFAULT_CONFIG = TradingAgentsConfig()
