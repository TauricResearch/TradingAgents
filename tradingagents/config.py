import os
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class DataVendorsConfig(BaseModel):
    core_stock_apis: str = "yfinance"
    technical_indicators: str = "yfinance"
    fundamental_data: str = "alpha_vantage"
    news_data: str = "alpha_vantage"


class QuantitativeWeightsConfig(BaseModel):
    news_sentiment_weight: float = Field(default=0.50, ge=0.0, le=1.0)
    quantitative_weight: float = Field(default=0.50, ge=0.0, le=1.0)

    momentum_weight: float = Field(default=0.30, ge=0.0, le=1.0)
    volume_weight: float = Field(default=0.25, ge=0.0, le=1.0)
    relative_strength_weight: float = Field(default=0.25, ge=0.0, le=1.0)
    risk_reward_weight: float = Field(default=0.20, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_weights_sum(self) -> "QuantitativeWeightsConfig":
        top_level_sum = self.news_sentiment_weight + self.quantitative_weight
        if abs(top_level_sum - 1.0) > 0.01:
            raise ValueError(
                f"Top-level weights (news_sentiment_weight + quantitative_weight) "
                f"must sum to 1.0, got {top_level_sum}"
            )

        sub_weights_sum = (
            self.momentum_weight
            + self.volume_weight
            + self.relative_strength_weight
            + self.risk_reward_weight
        )
        if abs(sub_weights_sum - 1.0) > 0.01:
            raise ValueError(
                f"Sub-weights (momentum + volume + relative_strength + risk_reward) "
                f"must sum to 1.0, got {sub_weights_sum}"
            )

        return self


class TradingAgentsSettings(BaseSettings):
    project_dir: str = Field(
        default_factory=lambda: os.path.abspath(
            os.path.join(os.path.dirname(__file__), ".")
        )
    )
    results_dir: str = Field(default="./results")
    data_dir: str = Field(default="./data")
    data_cache_dir: str | None = None

    llm_provider: str = Field(default="openai")
    deep_think_llm: str = Field(default="gpt-5")
    quick_think_llm: str = Field(default="gpt-5-mini")
    backend_url: str = Field(default="https://api.openai.com/v1")

    max_debate_rounds: int = Field(default=2, ge=1, le=10)
    max_risk_discuss_rounds: int = Field(default=2, ge=1, le=10)
    max_recur_limit: int = Field(default=100, ge=10, le=500)

    discovery_timeout: int = Field(default=60, ge=10)
    discovery_hard_timeout: int = Field(default=120, ge=30)
    discovery_cache_ttl: int = Field(default=300, ge=60)
    discovery_max_results: int = Field(default=20, ge=1, le=100)
    discovery_min_mentions: int = Field(default=2, ge=1)

    bulk_news_vendor_order: list[str] = Field(
        default=["tavily", "brave", "alpha_vantage", "openai", "google"]
    )
    bulk_news_timeout: int = Field(default=30, ge=5)
    bulk_news_max_retries: int = Field(default=3, ge=1)

    log_level: str = Field(default="INFO")
    log_dir: str = Field(default="./logs")
    log_console_enabled: bool = Field(default=True)
    log_file_enabled: bool = Field(default=True)

    openai_api_key: str | None = Field(default=None)
    alpha_vantage_api_key: str | None = Field(default=None)
    brave_api_key: str | None = Field(default=None)
    tavily_api_key: str | None = Field(default=None)
    google_api_key: str | None = Field(default=None)
    anthropic_api_key: str | None = Field(default=None)

    data_vendors: DataVendorsConfig = Field(default_factory=DataVendorsConfig)
    tool_vendors: dict[str, Any] = Field(default_factory=dict)

    quantitative_weights: QuantitativeWeightsConfig = Field(
        default_factory=QuantitativeWeightsConfig
    )
    quantitative_max_stocks: int = Field(default=50, ge=10, le=100)
    quantitative_cache_ttl_intraday: int = Field(default=1, ge=1)
    quantitative_cache_ttl_relative_strength: int = Field(default=4, ge=1)
    min_dollar_volume: float = Field(default=1_000_000.0, ge=0.0)

    model_config = {
        "env_prefix": "TRADINGAGENTS_",
        "env_nested_delimiter": "__",
        "extra": "ignore",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    def model_post_init(self, __context: Any) -> None:
        if self.data_cache_dir is None:
            self.data_cache_dir = os.path.join(self.project_dir, "dataflows/data_cache")

        if self.openai_api_key is None:
            self.openai_api_key = os.getenv("OPENAI_API_KEY")
        if self.alpha_vantage_api_key is None:
            self.alpha_vantage_api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        if self.brave_api_key is None:
            self.brave_api_key = os.getenv("BRAVE_API_KEY")
        if self.tavily_api_key is None:
            self.tavily_api_key = os.getenv("TAVILY_API_KEY")
        if self.google_api_key is None:
            self.google_api_key = os.getenv("GOOGLE_API_KEY")
        if self.anthropic_api_key is None:
            self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, v: str) -> str:
        valid_providers = {"openai", "anthropic", "google", "ollama", "openrouter"}
        if v.lower() not in valid_providers:
            raise ValueError(
                f"Invalid LLM provider: {v}. Must be one of {valid_providers}"
            )
        return v.lower()

    def to_dict(self) -> dict[str, Any]:
        result = self.model_dump()
        result["data_vendors"] = self.data_vendors.model_dump()
        result["quantitative_weights"] = self.quantitative_weights.model_dump()
        return result

    def get_api_key(self, vendor: str) -> str | None:
        key_map = {
            "openai": self.openai_api_key,
            "alpha_vantage": self.alpha_vantage_api_key,
            "brave": self.brave_api_key,
            "tavily": self.tavily_api_key,
            "google": self.google_api_key,
            "anthropic": self.anthropic_api_key,
        }
        return key_map.get(vendor.lower())

    def require_api_key(self, vendor: str) -> str:
        key = self.get_api_key(vendor)
        if not key:
            env_var = f"{vendor.upper()}_API_KEY"
            raise ValueError(
                f"{vendor} API key not configured. "
                f"Set {env_var} environment variable or TRADINGAGENTS_{env_var}."
            )
        return key


_settings: TradingAgentsSettings | None = None


def get_settings() -> TradingAgentsSettings:
    global _settings
    if _settings is None:
        _settings = TradingAgentsSettings()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None


def update_settings(**kwargs) -> TradingAgentsSettings:
    global _settings
    current = get_settings()
    new_values = current.model_dump()
    new_values.update(kwargs)
    _settings = TradingAgentsSettings(**new_values)
    return _settings
