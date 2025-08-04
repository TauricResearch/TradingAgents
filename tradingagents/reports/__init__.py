"""
TradingAgents Reports Module

This module provides comprehensive report generation capabilities for TradingAgents analysis,
including PDF generation, HTML conversion, and structured formatting.

Structure:
- generators/: PDF and other report generators
- formatters/: Report structure and formatting logic
- converters/: Content conversion utilities
"""

try:
    from .generators import TradingReportPDFGenerator
    from .formatters import ReportFormatter
    from .converters import RichToHTMLConverter
    __all__ = ['TradingReportPDFGenerator', 'ReportFormatter', 'RichToHTMLConverter']
except ImportError as e:
    # Handle missing dependencies gracefully
    print(f"Warning: Could not import report components: {e}")
    __all__ = []