"""TradingAgents: multi-agent LLM financial trading framework."""

__version__ = "0.7.1"

try:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv(usecwd=True))
    load_dotenv(find_dotenv(".env.enterprise", usecwd=True), override=False)
except ImportError:
    pass
