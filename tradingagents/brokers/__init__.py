"""
Broker integrations for live and paper trading.

Supported brokers:
- Alpaca: Free paper trading, easy API
- Interactive Brokers: Professional platform
"""

from .base import BaseBroker, BrokerOrder, BrokerPosition, BrokerAccount

try:
    from .alpaca_broker import AlpacaBroker
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False

try:
    from .ib_broker import InteractiveBrokersBroker
    IB_AVAILABLE = False  # Requires more setup
except ImportError:
    IB_AVAILABLE = False

__all__ = [
    'BaseBroker',
    'BrokerOrder',
    'BrokerPosition',
    'BrokerAccount',
]

if ALPACA_AVAILABLE:
    __all__.append('AlpacaBroker')

if IB_AVAILABLE:
    __all__.append('InteractiveBrokersBroker')
