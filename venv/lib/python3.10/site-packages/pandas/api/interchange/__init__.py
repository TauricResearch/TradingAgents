"""
Public API for DataFrame interchange protocol.
"""

from pandas.core.interchange.dataframe_protocol import DataFrame
from pandas.core.interchange.from_dataframe import from_dataframe

__all__ = ["from_dataframe", "DataFrame"]
