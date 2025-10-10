"""
A module for parsing and generating `fontconfig patterns`_.

.. _fontconfig patterns:
   https://www.freedesktop.org/software/fontconfig/fontconfig-user.html
"""

# This class logically belongs in `matplotlib.font_manager`, but placing it
# there would have created cyclical dependency problems, because it also needs
# to be available from `matplotlib.rcsetup` (for parsing matplotlibrc files).

from functools import lru_cache, partial
import re

from pyparsing import (
    Group, Optional, ParseException, Regex, StringEnd, Suppress, ZeroOrMore, one_of)


_family_punc = r'\\\-:,'
_family_unescape = partial(re.compile(r'\\(?=[%s])' % _family_punc).sub, '')
_family_escape = partial(re.compile(r'(?=[%s])' % _family_punc).sub, r'\\')
_value_punc = r'\\=_:,'
_value_unescape = partial(re.compile(r'\\(?=[%s])' % _value_punc).sub, '')
_value_escape = partial(re.compile(r'(?=[%s])' % _value_punc).sub, r'\\')


_CONSTANTS = {
    'thin':           ('weight', 'light'),
    'extralight':     ('weight', 'light'),
    'ultralight':     ('weight', 'light'),
    'light':          ('weight', 'light'),
    'book':           ('weight', 'book'),
    'regular':        ('weight', 'regular'),
    'normal':         ('weight', 'normal'),
    'medium':         ('weight', 'medium'),
    'demibold':       ('weight', 'demibold'),
    'semibold':       ('weight', 'semibold'),
    'bold':           ('weight', 'bold'),
    'extrabold':      ('weight', 'extra bold'),
    'black':          ('weight', 'black'),
    'heavy':          ('weight', 'heavy'),
    'roman':          ('slant', 'normal'),
    'italic':         ('slant', 'italic'),
    'oblique':        ('slant', 'oblique'),
    'ultracondensed': ('width', 'ultra-condensed'),
    'extracondensed': ('width', 'extra-condensed'),
    'condensed':      ('width', 'condensed'),
    'semicondensed':  ('width', 'semi-condensed'),
    'expanded':       ('width', 'expanded'),
    'extraexpanded':  ('width', 'extra-expanded'),
    'ultraexpanded':  ('width', 'ultra-expanded'),
}


@lru_cache  # The parser instance is a singleton.
def _make_fontconfig_parser():
    def comma_separated(elem):
        return elem + ZeroOrMore(Suppress(",") + elem)

    family = Regex(fr"([^{_family_punc}]|(\\[{_family_punc}]))*")
    size = Regex(r"([0-9]+\.?[0-9]*|\.[0-9]+)")
    name = Regex(r"[a-z]+")
    value = Regex(fr"([^{_value_punc}]|(\\[{_value_punc}]))*")
    prop = Group((name + Suppress("=") + comma_separated(value)) | one_of(_CONSTANTS))
    return (
        Optional(comma_separated(family)("families"))
        + Optional("-" + comma_separated(size)("sizes"))
        + ZeroOrMore(":" + prop("properties*"))
        + StringEnd()
    )


# `parse_fontconfig_pattern` is a bottleneck during the tests because it is
# repeatedly called when the rcParams are reset (to validate the default
# fonts).  In practice, the cache size doesn't grow beyond a few dozen entries
# during the test suite.
@lru_cache
def parse_fontconfig_pattern(pattern):
    """
    Parse a fontconfig *pattern* into a dict that can initialize a
    `.font_manager.FontProperties` object.
    """
    parser = _make_fontconfig_parser()
    try:
        parse = parser.parse_string(pattern)
    except ParseException as err:
        # explain becomes a plain method on pyparsing 3 (err.explain(0)).
        raise ValueError("\n" + ParseException.explain(err, 0)) from None
    parser.reset_cache()
    props = {}
    if "families" in parse:
        props["family"] = [*map(_family_unescape, parse["families"])]
    if "sizes" in parse:
        props["size"] = [*parse["sizes"]]
    for prop in parse.get("properties", []):
        if len(prop) == 1:
            prop = _CONSTANTS[prop[0]]
        k, *v = prop
        props.setdefault(k, []).extend(map(_value_unescape, v))
    return props


def generate_fontconfig_pattern(d):
    """Convert a `.FontProperties` to a fontconfig pattern string."""
    kvs = [(k, getattr(d, f"get_{k}")())
           for k in ["style", "variant", "weight", "stretch", "file", "size"]]
    # Families is given first without a leading keyword.  Other entries (which
    # are necessarily scalar) are given as key=value, skipping Nones.
    return (",".join(_family_escape(f) for f in d.get_family())
            + "".join(f":{k}={_value_escape(str(v))}"
                      for k, v in kvs if v is not None))
