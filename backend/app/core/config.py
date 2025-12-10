"""
Configuration management for TradingAgentsX Backend API
"""
from pydantic_settings import BaseSettings
from typing import Optional
import os
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Application settings
    app_name: str = "TradingAgentsX API"
    app_version: str = "1.0.0"
    debug: bool = Field(default=False)
    results_dir: str = Field(default="./results")
    
    # API Keys
    openai_api_key: Optional[str] = None
    alpha_vantage_api_key: Optional[str] = None
    
    # CORS Configuration
    cors_origins: list = [
        "http://localhost:3000",
        "http://frontend:3000",
        "https://*.vercel.app",  # Vercel deployments
        "https://*.onrender.com",  # Render deployments
        "https://*.railway.app",  # Railway deployments
    ]
    
    # TradingAgentsX Configuration
    results_dir: str = "./results"
    max_debate_rounds: int = 1
    max_risk_discuss_rounds: int = 1
    deep_think_llm: str = "gpt-5-mini"
    quick_think_llm: str = "gpt-5-mini"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra environment variables like ANTHROPIC_API_KEY, etc.


# Global settings instance
settings = Settings()
