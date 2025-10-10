# Copyright 2013 Google, Inc. All Rights Reserved.
#
# Google Author(s): Matt Fontaine

from . import E_B_L_C_


class table_C_B_L_C_(E_B_L_C_.table_E_B_L_C_):
    """Color Bitmap Location table

    The ``CBLC`` table contains the locations of color bitmaps for glyphs. It must
    be used in concert with the ``CBDT`` table.

    It is backwards-compatible with the monochrome/grayscale ``EBLC`` table.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/cblc
    """

    dependencies = ["CBDT"]
