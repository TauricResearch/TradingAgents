from .utils.agent_utils import create_msg_delete
from .utils.agent_states import AgentState, InvestDebateState, RiskDebateState

from .analysts.fundamentals_analyst import create_fundamentals_analyst
from .analysts.market_analyst import create_market_analyst
from .analysts.news_analyst import create_news_analyst
from .analysts.sentiment_analyst import (
    create_sentiment_analyst,
    create_social_media_analyst,  # deprecated alias kept for back-compat
)
from .analysts.india_market_analyst import create_india_market_analyst
from .analysts.india_fundamentals_analyst import create_india_fundamentals_analyst
from .analysts.india_news_filings_analyst import create_india_news_filings_analyst
from .analysts.india_macro_policy_analyst import create_india_macro_policy_analyst
from .analysts.india_flows_analyst import create_india_flows_analyst
from .analysts.india_sentiment_analyst import create_india_sentiment_analyst
from .analysts.india_compliance_risk_analyst import (
    create_india_compliance_risk_analyst,
)

from .researchers.bear_researcher import create_bear_researcher
from .researchers.bull_researcher import create_bull_researcher

from .risk_mgmt.aggressive_debator import create_aggressive_debator
from .risk_mgmt.conservative_debator import create_conservative_debator
from .risk_mgmt.neutral_debator import create_neutral_debator

from .managers.research_manager import create_research_manager
from .managers.portfolio_manager import create_portfolio_manager

from .trader.trader import create_trader

__all__ = [
    "AgentState",
    "create_msg_delete",
    "InvestDebateState",
    "RiskDebateState",
    "create_bear_researcher",
    "create_bull_researcher",
    "create_research_manager",
    "create_fundamentals_analyst",
    "create_market_analyst",
    "create_neutral_debator",
    "create_news_analyst",
    "create_aggressive_debator",
    "create_portfolio_manager",
    "create_conservative_debator",
    "create_sentiment_analyst",
    "create_social_media_analyst",  # deprecated; will be removed in a future version
    "create_india_market_analyst",
    "create_india_fundamentals_analyst",
    "create_india_news_filings_analyst",
    "create_india_macro_policy_analyst",
    "create_india_flows_analyst",
    "create_india_sentiment_analyst",
    "create_india_compliance_risk_analyst",
    "create_trader",
]
