"""
A python interface to Adobe Font Metrics Files.

Although a number of other Python implementations exist, and may be more
complete than this, it was decided not to go with them because they were
either:

1) copyrighted or used a non-BSD compatible license
2) had too many dependencies and a free standing lib was needed
3) did more than needed and it was easier to write afresh rather than
   figure out how to get just what was needed.

It is pretty easy to use, and has no external dependencies:

>>> import matplotlib as mpl
>>> from pathlib import Path
>>> afm_path = Path(mpl.get_data_path(), 'fonts', 'afm', 'ptmr8a.afm')
>>>
>>> from matplotlib.afm import AFM
>>> with afm_path.open('rb') as fh:
...     afm = AFM(fh)
>>> afm.string_width_height('What the heck?')
(6220.0, 694)
>>> afm.get_fontname()
'Times-Roman'
>>> afm.get_kern_dist('A', 'f')
0
>>> afm.get_kern_dist('A', 'y')
-92.0
>>> afm.get_bbox_char('!')
[130, -9, 238, 676]

As in the Adobe Font Metrics File Format Specification, all dimensions
are given in units of 1/1000 of the scale factor (point size) of the font
being used.
"""

from collections import namedtuple
import logging
import re

from ._mathtext_data import uni2type1


_log = logging.getLogger(__name__)


def _to_int(x):
    # Some AFM files have floats where we are expecting ints -- there is
    # probably a better way to handle this (support floats, round rather than
    # truncate).  But I don't know what the best approach is now and this
    # change to _to_int should at least prevent Matplotlib from crashing on
    # these.  JDH (2009-11-06)
    return int(float(x))


def _to_float(x):
    # Some AFM files use "," instead of "." as decimal separator -- this
    # shouldn't be ambiguous (unless someone is wicked enough to use "," as
    # thousands separator...).
    if isinstance(x, bytes):
        # Encoding doesn't really matter -- if we have codepoints >127 the call
        # to float() will error anyways.
        x = x.decode('latin-1')
    return float(x.replace(',', '.'))


def _to_str(x):
    return x.decode('utf8')


def _to_list_of_ints(s):
    s = s.replace(b',', b' ')
    return [_to_int(val) for val in s.split()]


def _to_list_of_floats(s):
    return [_to_float(val) for val in s.split()]


def _to_bool(s):
    if s.lower().strip() in (b'false', b'0', b'no'):
        return False
    else:
        return True


def _parse_header(fh):
    """
    Read the font metrics header (up to the char metrics) and returns
    a dictionary mapping *key* to *val*.  *val* will be converted to the
    appropriate python type as necessary; e.g.:

        * 'False'->False
        * '0'->0
        * '-168 -218 1000 898'-> [-168, -218, 1000, 898]

    Dictionary keys are

      StartFontMetrics, FontName, FullName, FamilyName, Weight,
      ItalicAngle, IsFixedPitch, FontBBox, UnderlinePosition,
      UnderlineThickness, Version, Notice, EncodingScheme, CapHeight,
      XHeight, Ascender, Descender, StartCharMetrics
    """
    header_converters = {
        b'StartFontMetrics': _to_float,
        b'FontName': _to_str,
        b'FullName': _to_str,
        b'FamilyName': _to_str,
        b'Weight': _to_str,
        b'ItalicAngle': _to_float,
        b'IsFixedPitch': _to_bool,
        b'FontBBox': _to_list_of_ints,
        b'UnderlinePosition': _to_float,
        b'UnderlineThickness': _to_float,
        b'Version': _to_str,
        # Some AFM files have non-ASCII characters (which are not allowed by
        # the spec).  Given that there is actually no public API to even access
        # this field, just return it as straight bytes.
        b'Notice': lambda x: x,
        b'EncodingScheme': _to_str,
        b'CapHeight': _to_float,  # Is the second version a mistake, or
        b'Capheight': _to_float,  # do some AFM files contain 'Capheight'? -JKS
        b'XHeight': _to_float,
        b'Ascender': _to_float,
        b'Descender': _to_float,
        b'StdHW': _to_float,
        b'StdVW': _to_float,
        b'StartCharMetrics': _to_int,
        b'CharacterSet': _to_str,
        b'Characters': _to_int,
    }
    d = {}
    first_line = True
    for line in fh:
        line = line.rstrip()
        if line.startswith(b'Comment'):
            continue
        lst = line.split(b' ', 1)
        key = lst[0]
        if first_line:
            # AFM spec, Section 4: The StartFontMetrics keyword
            # [followed by a version number] must be the first line in
            # the file, and the EndFontMetrics keyword must be the
            # last non-empty line in the file.  We just check the
            # first header entry.
            if key != b'StartFontMetrics':
                raise RuntimeError('Not an AFM file')
            first_line = False
        if len(lst) == 2:
            val = lst[1]
        else:
            val = b''
        try:
            converter = header_converters[key]
        except KeyError:
            _log.error("Found an unknown keyword in AFM header (was %r)", key)
            continue
        try:
            d[key] = converter(val)
        except ValueError:
            _log.error('Value error parsing header in AFM: %s, %s', key, val)
            continue
        if key == b'StartCharMetrics':
            break
    else:
        raise RuntimeError('Bad parse')
    return d


CharMetrics = namedtuple('CharMetrics', 'width, name, bbox')
CharMetrics.__doc__ = """
    Represents the character metrics of a single character.

    Notes
    -----
    The fields do currently only describe a subset of character metrics
    information defined in the AFM standard.
    """
CharMetrics.width.__doc__ = """The character width (WX)."""
CharMetrics.name.__doc__ = """The character name (N)."""
CharMetrics.bbox.__doc__ = """
    The bbox of the character (B) as a tuple (*llx*, *lly*, *urx*, *ury*)."""


def _parse_char_metrics(fh):
    """
    Parse the given filehandle for character metrics information and return
    the information as dicts.

    It is assumed that the file cursor is on the line behind
    'StartCharMetrics'.

    Returns
    -------
    ascii_d : dict
         A mapping "ASCII num of the character" to `.CharMetrics`.
    name_d : dict
         A mapping "character name" to `.CharMetrics`.

    Notes
    -----
    This function is incomplete per the standard, but thus far parses
    all the sample afm files tried.
    """
    required_keys = {'C', 'WX', 'N', 'B'}

    ascii_d = {}
    name_d = {}
    for line in fh:
        # We are defensively letting values be utf8. The spec requires
        # ascii, but there are non-compliant fonts in circulation
        line = _to_str(line.rstrip())  # Convert from byte-literal
        if line.startswith('EndCharMetrics'):
            return ascii_d, name_d
        # Split the metric line into a dictionary, keyed by metric identifiers
        vals = dict(s.strip().split(' ', 1) for s in line.split(';') if s)
        # There may be other metrics present, but only these are needed
        if not required_keys.issubset(vals):
            raise RuntimeError('Bad char metrics line: %s' % line)
        num = _to_int(vals['C'])
        wx = _to_float(vals['WX'])
        name = vals['N']
        bbox = _to_list_of_floats(vals['B'])
        bbox = list(map(int, bbox))
        metrics = CharMetrics(wx, name, bbox)
        # Workaround: If the character name is 'Euro', give it the
        # corresponding character code, according to WinAnsiEncoding (see PDF
        # Reference).
        if name == 'Euro':
            num = 128
        elif name == 'minus':
            num = ord("\N{MINUS SIGN}")  # 0x2212
        if num != -1:
            ascii_d[num] = metrics
        name_d[name] = metrics
    raise RuntimeError('Bad parse')


def _parse_kern_pairs(fh):
    """
    Return a kern pairs dictionary; keys are (*char1*, *char2*) tuples and
    values are the kern pair value.  For example, a kern pairs line like
    ``KPX A y -50``

    will be represented as::

      d[ ('A', 'y') ] = -50

    """

    line = next(fh)
    if not line.startswith(b'StartKernPairs'):
        raise RuntimeError('Bad start of kern pairs data: %s' % line)

    d = {}
    for line in fh:
        line = line.rstrip()
        if not line:
            continue
        if line.startswith(b'EndKernPairs'):
            next(fh)  # EndKernData
            return d
        vals = line.split()
        if len(vals) != 4 or vals[0] != b'KPX':
            raise RuntimeError('Bad kern pairs line: %s' % line)
        c1, c2, val = _to_str(vals[1]), _to_str(vals[2]), _to_float(vals[3])
        d[(c1, c2)] = val
    raise RuntimeError('Bad kern pairs parse')


CompositePart = namedtuple('CompositePart', 'name, dx, dy')
CompositePart.__doc__ = """
    Represents the information on a composite element of a composite char."""
CompositePart.name.__doc__ = """Name of the part, e.g. 'acute'."""
CompositePart.dx.__doc__ = """x-displacement of the part from the origin."""
CompositePart.dy.__doc__ = """y-displacement of the part from the origin."""


def _parse_composites(fh):
    """
    Parse the given filehandle for composites information return them as a
    dict.

    It is assumed that the file cursor is on the line behind 'StartComposites'.

    Returns
    -------
    dict
        A dict mapping composite character names to a parts list. The parts
        list is a list of `.CompositePart` entries describing the parts of
        the composite.

    Examples
    --------
    A composite definition line::

      CC Aacute 2 ; PCC A 0 0 ; PCC acute 160 170 ;

    will be represented as::

      composites['Aacute'] = [CompositePart(name='A', dx=0, dy=0),
                              CompositePart(name='acute', dx=160, dy=170)]

    """
    composites = {}
    for line in fh:
        line = line.rstrip()
        if not line:
            continue
        if line.startswith(b'EndComposites'):
            return composites
        vals = line.split(b';')
        cc = vals[0].split()
        name, _num_parts = cc[1], _to_int(cc[2])
        pccParts = []
        for s in vals[1:-1]:
            pcc = s.split()
            part = CompositePart(pcc[1], _to_float(pcc[2]), _to_float(pcc[3]))
            pccParts.append(part)
        composites[name] = pccParts

    raise RuntimeError('Bad composites parse')


def _parse_optional(fh):
    """
    Parse the optional fields for kern pair data and composites.

    Returns
    -------
    kern_data : dict
        A dict containing kerning information. May be empty.
        See `._parse_kern_pairs`.
    composites : dict
        A dict containing composite information. May be empty.
        See `._parse_composites`.
    """
    optional = {
        b'StartKernData': _parse_kern_pairs,
        b'StartComposites':  _parse_composites,
        }

    d = {b'StartKernData': {},
         b'StartComposites': {}}
    for line in fh:
        line = line.rstrip()
        if not line:
            continue
        key = line.split()[0]

        if key in optional:
            d[key] = optional[key](fh)

    return d[b'StartKernData'], d[b'StartComposites']


class AFM:

    def __init__(self, fh):
        """Parse the AFM file in file object *fh*."""
        self._header = _parse_header(fh)
        self._metrics, self._metrics_by_name = _parse_char_metrics(fh)
        self._kern, self._composite = _parse_optional(fh)

    def get_bbox_char(self, c, isord=False):
        if not isord:
            c = ord(c)
        return self._metrics[c].bbox

    def string_width_height(self, s):
        """
        Return the string width (including kerning) and string height
        as a (*w*, *h*) tuple.
        """
        if not len(s):
            return 0, 0
        total_width = 0
        namelast = None
        miny = 1e9
        maxy = 0
        for c in s:
            if c == '\n':
                continue
            wx, name, bbox = self._metrics[ord(c)]

            total_width += wx + self._kern.get((namelast, name), 0)
            l, b, w, h = bbox
            miny = min(miny, b)
            maxy = max(maxy, b + h)

            namelast = name

        return total_width, maxy - miny

    def get_str_bbox_and_descent(self, s):
        """Return the string bounding box and the maximal descent."""
        if not len(s):
            return 0, 0, 0, 0, 0
        total_width = 0
        namelast = None
        miny = 1e9
        maxy = 0
        left = 0
        if not isinstance(s, str):
            s = _to_str(s)
        for c in s:
            if c == '\n':
                continue
            name = uni2type1.get(ord(c), f"uni{ord(c):04X}")
            try:
                wx, _, bbox = self._metrics_by_name[name]
            except KeyError:
                name = 'question'
                wx, _, bbox = self._metrics_by_name[name]
            total_width += wx + self._kern.get((namelast, name), 0)
            l, b, w, h = bbox
            left = min(left, l)
            miny = min(miny, b)
            maxy = max(maxy, b + h)

            namelast = name

        return left, miny, total_width, maxy - miny, -miny

    def get_str_bbox(self, s):
        """Return the string bounding box."""
        return self.get_str_bbox_and_descent(s)[:4]

    def get_name_char(self, c, isord=False):
        """Get the name of the character, i.e., ';' is 'semicolon'."""
        if not isord:
            c = ord(c)
        return self._metrics[c].name

    def get_width_char(self, c, isord=False):
        """
        Get the width of the character from the character metric WX field.
        """
        if not isord:
            c = ord(c)
        return self._metrics[c].width

    def get_width_from_char_name(self, name):
        """Get the width of the character from a type1 character name."""
        return self._metrics_by_name[name].width

    def get_height_char(self, c, isord=False):
        """Get the bounding box (ink) height of character *c* (space is 0)."""
        if not isord:
            c = ord(c)
        return self._metrics[c].bbox[-1]

    def get_kern_dist(self, c1, c2):
        """
        Return the kerning pair distance (possibly 0) for chars *c1* and *c2*.
        """
        name1, name2 = self.get_name_char(c1), self.get_name_char(c2)
        return self.get_kern_dist_from_name(name1, name2)

    def get_kern_dist_from_name(self, name1, name2):
        """
        Return the kerning pair distance (possibly 0) for chars
        *name1* and *name2*.
        """
        return self._kern.get((name1, name2), 0)

    def get_fontname(self):
        """Return the font name, e.g., 'Times-Roman'."""
        return self._header[b'FontName']

    @property
    def postscript_name(self):  # For consistency with FT2Font.
        return self.get_fontname()

    def get_fullname(self):
        """Return the font full name, e.g., 'Times-Roman'."""
        name = self._header.get(b'FullName')
        if name is None:  # use FontName as a substitute
            name = self._header[b'FontName']
        return name

    def get_familyname(self):
        """Return the font family name, e.g., 'Times'."""
        name = self._header.get(b'FamilyName')
        if name is not None:
            return name

        # FamilyName not specified so we'll make a guess
        name = self.get_fullname()
        extras = (r'(?i)([ -](regular|plain|italic|oblique|bold|semibold|'
                  r'light|ultralight|extra|condensed))+$')
        return re.sub(extras, '', name)

    @property
    def family_name(self):
        """The font family name, e.g., 'Times'."""
        return self.get_familyname()

    def get_weight(self):
        """Return the font weight, e.g., 'Bold' or 'Roman'."""
        return self._header[b'Weight']

    def get_angle(self):
        """Return the fontangle as float."""
        return self._header[b'ItalicAngle']

    def get_capheight(self):
        """Return the cap height as float."""
        return self._header[b'CapHeight']

    def get_xheight(self):
        """Return the xheight as float."""
        return self._header[b'XHeight']

    def get_underline_thickness(self):
        """Return the underline thickness as float."""
        return self._header[b'UnderlineThickness']

    def get_horizontal_stem_width(self):
        """
        Return the standard horizontal stem width as float, or *None* if
        not specified in AFM file.
        """
        return self._header.get(b'StdHW', None)

    def get_vertical_stem_width(self):
        """
        Return the standard vertical stem width as float, or *None* if
        not specified in AFM file.
        """
        return self._header.get(b'StdVW', None)
