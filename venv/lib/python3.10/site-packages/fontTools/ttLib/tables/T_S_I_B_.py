""" TSI{B,C,D,J,P,S,V} are private tables used by Microsoft Visual TrueType (VTT)
tool to store its table source data.

TSIB contains the source text for the ``BASE`` table.

See also https://learn.microsoft.com/en-us/typography/tools/vtt/tsi-tables
"""

from .T_S_I_V_ import table_T_S_I_V_


class table_T_S_I_B_(table_T_S_I_V_):
    pass
