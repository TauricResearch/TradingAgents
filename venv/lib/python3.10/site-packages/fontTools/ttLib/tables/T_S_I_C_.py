""" TSI{B,C,D,J,P,S,V} are private tables used by Microsoft Visual TrueType (VTT)
tool to store its table source data.

TSIC contains the source text for the Variation CVT window and data for
the ``cvar`` table.

See also https://learn.microsoft.com/en-us/typography/tools/vtt/tsi-tables
"""

from .otBase import BaseTTXConverter


class table_T_S_I_C_(BaseTTXConverter):
    pass
