"""
Cross-Asset Correlation Engine (CACE)
Advanced correlation analysis for multi-asset trading strategies.

This module implements sophisticated correlation analysis techniques
for detecting relationships between different financial instruments.
Based on academic research in multivariate time series analysis.

Author: Research Team
Date: 2026-02-07
"""

from .correlation_analyzer import CorrelationAnalyzer
from .multi_asset_processor import MultiAssetProcessor
from .correlation_regime_detector import CorrelationRegimeDetector

__version__ = "1.0.0"
__all__ = [
    "CorrelationAnalyzer",
    "MultiAssetProcessor",
    "CorrelationRegimeDetector",
]