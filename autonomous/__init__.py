"""
Autonomous Trading System
========================

A 24/7 monitoring system that integrates with IBKR and multiple data sources
to provide real-time trading recommendations.
"""

__version__ = "0.1.0"

from .ibkr_connector import IBKRConnector
from .data_aggregator import DataAggregator
from .signal_processor import SignalProcessor
from .alert_engine import AlertEngine

__all__ = [
    "IBKRConnector",
    "DataAggregator",
    "SignalProcessor",
    "AlertEngine",
]