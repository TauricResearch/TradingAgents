from __future__ import annotations

from fontTools.misc.textTools import byteord, tostr

import re
from bisect import bisect_right
from typing import Literal, TypeVar, overload


try:
    # use unicodedata backport compatible with python2:
    # https://github.com/fonttools/unicodedata2
    from unicodedata2 import *
except ImportError:  # pragma: no cover
    # fall back to built-in unicodedata (possibly outdated)
    from unicodedata import *

from . import Blocks, Mirrored, Scripts, ScriptExtensions, OTTags

__all__ = [
    # names from built-in unicodedata module
    "lookup",
    "name",
    "decimal",
    "digit",
    "numeric",
    "category",
    "bidirectional",
    "combining",
    "east_asian_width",
    "mirrored",
    "decomposition",
    "normalize",
    "unidata_version",
    "ucd_3_2_0",
    # additonal functions
    "block",
    "script",
    "script_extension",
    "script_name",
    "script_code",
    "script_horizontal_direction",
    "ot_tags_from_script",
    "ot_tag_to_script",
]


def mirrored(code):
    """If code (unicode codepoint) has a mirrored version returns it, otherwise None."""
    return Mirrored.MIRRORED.get(code)


def script(char):
    """Return the four-letter script code assigned to the Unicode character
    'char' as string.

    >>> script("a")
    'Latn'
    >>> script(",")
    'Zyyy'
    >>> script(chr(0x10FFFF))
    'Zzzz'
    """
    code = byteord(char)
    # 'bisect_right(a, x, lo=0, hi=len(a))' returns an insertion point which
    # comes after (to the right of) any existing entries of x in a, and it
    # partitions array a into two halves so that, for the left side
    # all(val <= x for val in a[lo:i]), and for the right side
    # all(val > x for val in a[i:hi]).
    # Our 'SCRIPT_RANGES' is a sorted list of ranges (only their starting
    # breakpoints); we want to use `bisect_right` to look up the range that
    # contains the given codepoint: i.e. whose start is less than or equal
    # to the codepoint. Thus, we subtract -1 from the index returned.
    i = bisect_right(Scripts.RANGES, code)
    return Scripts.VALUES[i - 1]


def script_extension(char):
    """Return the script extension property assigned to the Unicode character
    'char' as a set of string.

    >>> script_extension("a") == {'Latn'}
    True
    >>> script_extension(chr(0x060C)) == {'Nkoo', 'Arab', 'Rohg', 'Thaa', 'Syrc', 'Gara', 'Yezi'}
    True
    >>> script_extension(chr(0x10FFFF)) == {'Zzzz'}
    True
    """
    code = byteord(char)
    i = bisect_right(ScriptExtensions.RANGES, code)
    value = ScriptExtensions.VALUES[i - 1]
    if value is None:
        # code points not explicitly listed for Script Extensions
        # have as their value the corresponding Script property value
        return {script(char)}
    return value


def script_name(code, default=KeyError):
    """Return the long, human-readable script name given a four-letter
    Unicode script code.

    If no matching name is found, a KeyError is raised by default.

    You can use the 'default' argument to return a fallback value (e.g.
    'Unknown' or None) instead of throwing an error.
    """
    try:
        return str(Scripts.NAMES[code].replace("_", " "))
    except KeyError:
        if isinstance(default, type) and issubclass(default, KeyError):
            raise
        return default


_normalize_re = re.compile(r"[-_ ]+")


def _normalize_property_name(string):
    """Remove case, strip space, '-' and '_' for loose matching."""
    return _normalize_re.sub("", string).lower()


_SCRIPT_CODES = {_normalize_property_name(v): k for k, v in Scripts.NAMES.items()}


def script_code(script_name, default=KeyError):
    """Returns the four-letter Unicode script code from its long name

    If no matching script code is found, a KeyError is raised by default.

    You can use the 'default' argument to return a fallback string (e.g.
    'Zzzz' or None) instead of throwing an error.
    """
    normalized_name = _normalize_property_name(script_name)
    try:
        return _SCRIPT_CODES[normalized_name]
    except KeyError:
        if isinstance(default, type) and issubclass(default, KeyError):
            raise
        return default


# The data on script direction is taken from Harfbuzz source code:
# https://github.com/harfbuzz/harfbuzz/blob/3.2.0/src/hb-common.cc#L514-L613
# This in turn references the following "Script_Metadata" document:
# https://docs.google.com/spreadsheets/d/1Y90M0Ie3MUJ6UVCRDOypOtijlMDLNNyyLk36T6iMu0o
RTL_SCRIPTS = {
    # Unicode-1.1 additions
    "Arab",  # Arabic
    "Hebr",  # Hebrew
    # Unicode-3.0 additions
    "Syrc",  # Syriac
    "Thaa",  # Thaana
    # Unicode-4.0 additions
    "Cprt",  # Cypriot
    # Unicode-4.1 additions
    "Khar",  # Kharoshthi
    # Unicode-5.0 additions
    "Phnx",  # Phoenician
    "Nkoo",  # Nko
    # Unicode-5.1 additions
    "Lydi",  # Lydian
    # Unicode-5.2 additions
    "Avst",  # Avestan
    "Armi",  # Imperial Aramaic
    "Phli",  # Inscriptional Pahlavi
    "Prti",  # Inscriptional Parthian
    "Sarb",  # Old South Arabian
    "Orkh",  # Old Turkic
    "Samr",  # Samaritan
    # Unicode-6.0 additions
    "Mand",  # Mandaic
    # Unicode-6.1 additions
    "Merc",  # Meroitic Cursive
    "Mero",  # Meroitic Hieroglyphs
    # Unicode-7.0 additions
    "Mani",  # Manichaean
    "Mend",  # Mende Kikakui
    "Nbat",  # Nabataean
    "Narb",  # Old North Arabian
    "Palm",  # Palmyrene
    "Phlp",  # Psalter Pahlavi
    # Unicode-8.0 additions
    "Hatr",  # Hatran
    "Hung",  # Old Hungarian
    # Unicode-9.0 additions
    "Adlm",  # Adlam
    # Unicode-11.0 additions
    "Rohg",  # Hanifi Rohingya
    "Sogo",  # Old Sogdian
    "Sogd",  # Sogdian
    # Unicode-12.0 additions
    "Elym",  # Elymaic
    # Unicode-13.0 additions
    "Chrs",  # Chorasmian
    "Yezi",  # Yezidi
    # Unicode-14.0 additions
    "Ougr",  # Old Uyghur
    # Unicode-16.0 additions
    "Gara",  # Garay
}


HorizDirection = Literal["RTL", "LTR"]
T = TypeVar("T")


@overload
def script_horizontal_direction(script_code: str, default: T) -> HorizDirection | T: ...


@overload
def script_horizontal_direction(
    script_code: str, default: type[KeyError] = KeyError
) -> HorizDirection: ...


def script_horizontal_direction(
    script_code: str, default: T | type[KeyError] = KeyError
) -> HorizDirection | T:
    """Return "RTL" for scripts that contain right-to-left characters
    according to the Bidi_Class property. Otherwise return "LTR".
    """
    if script_code not in Scripts.NAMES:
        if isinstance(default, type) and issubclass(default, KeyError):
            raise default(script_code)
        return default
    return "RTL" if script_code in RTL_SCRIPTS else "LTR"


def block(char):
    """Return the block property assigned to the Unicode character 'char'
    as a string.

    >>> block("a")
    'Basic Latin'
    >>> block(chr(0x060C))
    'Arabic'
    >>> block(chr(0xEFFFF))
    'No_Block'
    """
    code = byteord(char)
    i = bisect_right(Blocks.RANGES, code)
    return Blocks.VALUES[i - 1]


def ot_tags_from_script(script_code):
    """Return a list of OpenType script tags associated with a given
    Unicode script code.
    Return ['DFLT'] script tag for invalid/unknown script codes.
    """
    if script_code in OTTags.SCRIPT_EXCEPTIONS:
        return [OTTags.SCRIPT_EXCEPTIONS[script_code]]

    if script_code not in Scripts.NAMES:
        return [OTTags.DEFAULT_SCRIPT]

    script_tags = [script_code[0].lower() + script_code[1:]]
    if script_code in OTTags.NEW_SCRIPT_TAGS:
        script_tags.extend(OTTags.NEW_SCRIPT_TAGS[script_code])
        script_tags.reverse()  # last in, first out

    return script_tags


def ot_tag_to_script(tag):
    """Return the Unicode script code for the given OpenType script tag, or
    None for "DFLT" tag or if there is no Unicode script associated with it.
    Raises ValueError if the tag is invalid.
    """
    tag = tostr(tag).strip()
    if not tag or " " in tag or len(tag) > 4:
        raise ValueError("invalid OpenType tag: %r" % tag)

    if tag in OTTags.SCRIPT_ALIASES:
        tag = OTTags.SCRIPT_ALIASES[tag]

    while len(tag) != 4:
        tag += str(" ")  # pad with spaces

    if tag == OTTags.DEFAULT_SCRIPT:
        # it's unclear which Unicode script the "DFLT" OpenType tag maps to,
        # so here we return None
        return None

    if tag in OTTags.NEW_SCRIPT_TAGS_REVERSED:
        return OTTags.NEW_SCRIPT_TAGS_REVERSED[tag]

    if tag in OTTags.SCRIPT_EXCEPTIONS_REVERSED:
        return OTTags.SCRIPT_EXCEPTIONS_REVERSED[tag]

    # This side of the conversion is fully algorithmic

    # Any spaces at the end of the tag are replaced by repeating the last
    # letter. Eg 'nko ' -> 'Nkoo'.
    # Change first char to uppercase
    script_code = tag[0].upper() + tag[1]
    for i in range(2, 4):
        script_code += script_code[i - 1] if tag[i] == " " else tag[i]

    if script_code not in Scripts.NAMES:
        return None
    return script_code
