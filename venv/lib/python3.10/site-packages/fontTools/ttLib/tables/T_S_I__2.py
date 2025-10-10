""" TSI{0,1,2,3,5} are private tables used by Microsoft Visual TrueType (VTT)
tool to store its hinting source data.

TSI2 is the index table containing the lengths and offsets for the glyph
programs that are contained in the TSI3 table. It uses the same format as
the TSI0 table.

See also https://learn.microsoft.com/en-us/typography/tools/vtt/tsi-tables
"""

from fontTools import ttLib

superclass = ttLib.getTableClass("TSI0")


class table_T_S_I__2(superclass):
    dependencies = ["TSI3"]
