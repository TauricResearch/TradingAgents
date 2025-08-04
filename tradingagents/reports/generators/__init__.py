"""
PDF and Report Generators

This module contains various generators for creating reports in different formats.
"""

try:
    from .pdf_generator import TradingReportPDFGenerator
    __all__ = ['TradingReportPDFGenerator']
except ImportError as e:
    # Handle missing dependencies gracefully
    print(f"Warning: Could not import PDF generator: {e}")
    __all__ = []