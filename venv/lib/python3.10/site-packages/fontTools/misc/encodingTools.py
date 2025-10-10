"""fontTools.misc.encodingTools.py -- tools for working with OpenType encodings.
"""

import fontTools.encodings.codecs

# Map keyed by platformID, then platEncID, then possibly langID
_encodingMap = {
    0: {  # Unicode
        0: "utf_16_be",
        1: "utf_16_be",
        2: "utf_16_be",
        3: "utf_16_be",
        4: "utf_16_be",
        5: "utf_16_be",
        6: "utf_16_be",
    },
    1: {  # Macintosh
        # See
        # https://github.com/fonttools/fonttools/issues/236
        0: {  # Macintosh, platEncID==0, keyed by langID
            15: "mac_iceland",
            17: "mac_turkish",
            18: "mac_croatian",
            24: "mac_latin2",
            25: "mac_latin2",
            26: "mac_latin2",
            27: "mac_latin2",
            28: "mac_latin2",
            36: "mac_latin2",
            37: "mac_romanian",
            38: "mac_latin2",
            39: "mac_latin2",
            40: "mac_latin2",
            Ellipsis: "mac_roman",  # Other
        },
        1: "x_mac_japanese_ttx",
        2: "x_mac_trad_chinese_ttx",
        3: "x_mac_korean_ttx",
        6: "mac_greek",
        7: "mac_cyrillic",
        25: "x_mac_simp_chinese_ttx",
        29: "mac_latin2",
        35: "mac_turkish",
        37: "mac_iceland",
    },
    2: {  # ISO
        0: "ascii",
        1: "utf_16_be",
        2: "latin1",
    },
    3: {  # Microsoft
        0: "utf_16_be",
        1: "utf_16_be",
        2: "shift_jis",
        3: "gb2312",
        4: "big5",
        5: "euc_kr",
        6: "johab",
        10: "utf_16_be",
    },
}


def getEncoding(platformID, platEncID, langID, default=None):
    """Returns the Python encoding name for OpenType platformID/encodingID/langID
    triplet.  If encoding for these values is not known, by default None is
    returned.  That can be overriden by passing a value to the default argument.
    """
    encoding = _encodingMap.get(platformID, {}).get(platEncID, default)
    if isinstance(encoding, dict):
        encoding = encoding.get(langID, encoding[Ellipsis])
    return encoding
