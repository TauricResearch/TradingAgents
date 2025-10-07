"""
Configuration Settings
=====================

Central configuration for the autonomous trading system.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Configuration class for autonomous trading system"""

    # === IBKR Settings ===
    IBKR_HOST = os.getenv('IBKR_HOST', '127.0.0.1')
    IBKR_PORT = int(os.getenv('IBKR_PORT', 7497))  # 7497=paper, 7496=live
    IBKR_CLIENT_ID = int(os.getenv('IBKR_CLIENT_ID', 1))

    # === API Keys ===
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY')
    QUIVER_API_KEY = os.getenv('QUIVER_API_KEY')
    POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')
    NEWS_API_KEY = os.getenv('NEWS_API_KEY')

    # === Notification Settings ===
    # Discord
    DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

    # Email
    EMAIL_SMTP_SERVER = os.getenv('EMAIL_SMTP_SERVER', 'smtp.gmail.com')
    EMAIL_SMTP_PORT = int(os.getenv('EMAIL_SMTP_PORT', 587))
    EMAIL_SENDER = os.getenv('EMAIL_SENDER')
    EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
    EMAIL_RECIPIENT = os.getenv('EMAIL_RECIPIENT')

    # === Portfolio Settings ===
    # Your IBKR portfolio tickers
    PORTFOLIO_TICKERS = [
        "AVGO",  # Broadcom - 43 shares
        "MSFT",  # Microsoft - 12 shares
        "MU",    # Micron - 13 shares
        "NVDA",  # Nvidia - 30 shares
        "TSM",   # Taiwan Semi - 15 shares
    ]

    # Additional tickers to monitor
    WATCHLIST = os.getenv('WATCHLIST', 'AAPL,TSLA,META,GOOGL,AMZN').split(',')

    # === Trading Settings ===
    TRADING_ENABLED = os.getenv('TRADING_ENABLED', 'false').lower() == 'true'
    PAPER_TRADING = os.getenv('PAPER_TRADING', 'true').lower() == 'true'

    # Risk Management
    MAX_POSITION_SIZE = float(os.getenv('MAX_POSITION_SIZE', 0.20))  # 20% max per position
    MAX_DAILY_LOSS = float(os.getenv('MAX_DAILY_LOSS', 0.05))  # 5% daily loss limit
    MAX_TRADES_PER_DAY = int(os.getenv('MAX_TRADES_PER_DAY', 10))
    STOP_LOSS_PERCENT = float(os.getenv('STOP_LOSS_PERCENT', 0.03))  # 3% stop loss

    # Position Sizing
    BASE_POSITION_SIZE = float(os.getenv('BASE_POSITION_SIZE', 0.10))  # 10% base
    MIN_POSITION_SIZE = float(os.getenv('MIN_POSITION_SIZE', 0.05))  # 5% minimum
    CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD', 70))  # Min 70% confidence

    # === AI Model Settings ===
    DEEP_THINK_MODEL = os.getenv('DEEP_THINK_MODEL', 'gpt-4o-mini')
    QUICK_THINK_MODEL = os.getenv('QUICK_THINK_MODEL', 'gpt-4o-mini')
    MAX_DEBATE_ROUNDS = int(os.getenv('MAX_DEBATE_ROUNDS', 1))

    # === Schedule Settings (in minutes) ===
    PORTFOLIO_CHECK_INTERVAL = int(os.getenv('PORTFOLIO_CHECK_INTERVAL', 5))
    MARKET_SCAN_INTERVAL = int(os.getenv('MARKET_SCAN_INTERVAL', 15))
    NEWS_CHECK_INTERVAL = int(os.getenv('NEWS_CHECK_INTERVAL', 30))
    CONGRESS_CHECK_INTERVAL = int(os.getenv('CONGRESS_CHECK_INTERVAL', 60))
    RISK_CHECK_INTERVAL = int(os.getenv('RISK_CHECK_INTERVAL', 30))

    # === Database Settings ===
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', 5432))
    DB_NAME = os.getenv('DB_NAME', 'trading_autonomous')
    DB_USER = os.getenv('DB_USER', 'trader')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')

    @classmethod
    def get_db_url(cls):
        """Get database connection URL"""
        return f"postgresql://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"

    @classmethod
    def to_dict(cls):
        """Convert config to dictionary"""
        return {
            # IBKR
            'ibkr_host': cls.IBKR_HOST,
            'ibkr_port': cls.IBKR_PORT,
            'ibkr_client_id': cls.IBKR_CLIENT_ID,

            # API Keys
            'openai_api_key': cls.OPENAI_API_KEY,
            'alpha_vantage_api_key': cls.ALPHA_VANTAGE_API_KEY,
            'quiver_api_key': cls.QUIVER_API_KEY,

            # Notifications
            'discord_webhook_url': cls.DISCORD_WEBHOOK_URL,
            'telegram_bot_token': cls.TELEGRAM_BOT_TOKEN,
            'telegram_chat_id': cls.TELEGRAM_CHAT_ID,
            'email': {
                'smtp_server': cls.EMAIL_SMTP_SERVER,
                'smtp_port': cls.EMAIL_SMTP_PORT,
                'sender_email': cls.EMAIL_SENDER,
                'sender_password': cls.EMAIL_PASSWORD,
                'recipient_email': cls.EMAIL_RECIPIENT
            },

            # Portfolio
            'portfolio_tickers': cls.PORTFOLIO_TICKERS,
            'watchlist': cls.WATCHLIST,

            # Trading
            'trading_enabled': cls.TRADING_ENABLED,
            'paper_trading': cls.PAPER_TRADING,
            'max_position_size': cls.MAX_POSITION_SIZE,
            'confidence_threshold': cls.CONFIDENCE_THRESHOLD,

            # AI Models
            'deep_think_llm': cls.DEEP_THINK_MODEL,
            'quick_think_llm': cls.QUICK_THINK_MODEL,
            'max_debate_rounds': cls.MAX_DEBATE_ROUNDS
        }

    @classmethod
    def validate(cls):
        """Validate configuration"""
        errors = []

        # Check required API keys
        if not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY is required")

        if not cls.ALPHA_VANTAGE_API_KEY:
            errors.append("ALPHA_VANTAGE_API_KEY is required")

        # Check notification settings
        if not any([cls.DISCORD_WEBHOOK_URL, cls.TELEGRAM_BOT_TOKEN, cls.EMAIL_SENDER]):
            errors.append("At least one notification method must be configured")

        # Validate risk settings
        if cls.MAX_POSITION_SIZE > 0.5:
            errors.append("MAX_POSITION_SIZE should not exceed 50%")

        if cls.MAX_DAILY_LOSS > 0.1:
            errors.append("MAX_DAILY_LOSS should not exceed 10%")

        if errors:
            print("Configuration errors:")
            for error in errors:
                print(f"  - {error}")
            return False

        return True


# Example config validation
if __name__ == "__main__":
    if Config.validate():
        print("✅ Configuration valid")
        print(f"Portfolio: {Config.PORTFOLIO_TICKERS}")
        print(f"Trading: {'ENABLED' if Config.TRADING_ENABLED else 'DISABLED'}")
        print(f"Mode: {'PAPER' if Config.PAPER_TRADING else 'LIVE'}")
    else:
        print("❌ Configuration invalid")