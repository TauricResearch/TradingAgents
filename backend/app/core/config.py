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
    # Set CORS_ORIGINS environment variable to comma-separated list of allowed origins
    # Example: CORS_ORIGINS=https://your-app.railway.app,https://your-frontend.vercel.app
    cors_origins_str: Optional[str] = Field(default=None, alias="CORS_ORIGINS")
    
    @property
    def cors_origins(self) -> list:
        """Get CORS origins from environment or use defaults"""
        if self.cors_origins_str:
            # Parse comma-separated origins from environment
            origins = [o.strip() for o in self.cors_origins_str.split(",") if o.strip()]
            # Always include localhost for development
            if "http://localhost:3000" not in origins:
                origins.append("http://localhost:3000")
            return origins
        
        # Default origins (fallback - consider removing wildcards in production)
        return [
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
        populate_by_name = True  # Allow using alias names


# Global settings instance
settings = Settings()
