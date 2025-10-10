""" TSI{0,1,2,3,5} are private tables used by Microsoft Visual TrueType (VTT)
tool to store its hinting source data.

TSI3 contains the text of the glyph programs in the form of 'VTTTalk' code.

See also https://learn.microsoft.com/en-us/typography/tools/vtt/tsi-tables
"""

from fontTools import ttLib

superclass = ttLib.getTableClass("TSI1")


class table_T_S_I__3(superclass):
    extras = {
        0xFFFA: "reserved0",
        0xFFFB: "reserved1",
        0xFFFC: "reserved2",
        0xFFFD: "reserved3",
    }

    indextable = "TSI2"
