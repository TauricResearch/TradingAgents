"""
A module for reading dvi files output by TeX. Several limitations make
this not (currently) useful as a general-purpose dvi preprocessor, but
it is currently used by the pdf backend for processing usetex text.

Interface::

  with Dvi(filename, 72) as dvi:
      # iterate over pages:
      for page in dvi:
          w, h, d = page.width, page.height, page.descent
          for x, y, font, glyph, width in page.text:
              fontname = font.texname
              pointsize = font.size
              ...
          for x, y, height, width in page.boxes:
              ...
"""

from collections import namedtuple
import enum
from functools import lru_cache, partial, wraps
import logging
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

import numpy as np

from matplotlib import _api, cbook

_log = logging.getLogger(__name__)

# Many dvi related files are looked for by external processes, require
# additional parsing, and are used many times per rendering, which is why they
# are cached using lru_cache().

# Dvi is a bytecode format documented in
# https://ctan.org/pkg/dvitype
# https://texdoc.org/serve/dvitype.pdf/0
#
# The file consists of a preamble, some number of pages, a postamble,
# and a finale. Different opcodes are allowed in different contexts,
# so the Dvi object has a parser state:
#
#   pre:       expecting the preamble
#   outer:     between pages (followed by a page or the postamble,
#              also e.g. font definitions are allowed)
#   page:      processing a page
#   post_post: state after the postamble (our current implementation
#              just stops reading)
#   finale:    the finale (unimplemented in our current implementation)

_dvistate = enum.Enum('DviState', 'pre outer inpage post_post finale')

# The marks on a page consist of text and boxes. A page also has dimensions.
Page = namedtuple('Page', 'text boxes height width descent')
Box = namedtuple('Box', 'x y height width')


# Also a namedtuple, for backcompat.
class Text(namedtuple('Text', 'x y font glyph width')):
    """
    A glyph in the dvi file.

    The *x* and *y* attributes directly position the glyph.  The *font*,
    *glyph*, and *width* attributes are kept public for back-compatibility,
    but users wanting to draw the glyph themselves are encouraged to instead
    load the font specified by `font_path` at `font_size`, warp it with the
    effects specified by `font_effects`, and load the glyph specified by
    `glyph_name_or_index`.
    """

    def _get_pdftexmap_entry(self):
        return PsfontsMap(find_tex_file("pdftex.map"))[self.font.texname]

    @property
    def font_path(self):
        """The `~pathlib.Path` to the font for this glyph."""
        psfont = self._get_pdftexmap_entry()
        if psfont.filename is None:
            raise ValueError("No usable font file found for {} ({}); "
                             "the font may lack a Type-1 version"
                             .format(psfont.psname.decode("ascii"),
                                     psfont.texname.decode("ascii")))
        return Path(psfont.filename)

    @property
    def font_size(self):
        """The font size."""
        return self.font.size

    @property
    def font_effects(self):
        """
        The "font effects" dict for this glyph.

        This dict contains the values for this glyph of SlantFont and
        ExtendFont (if any), read off :file:`pdftex.map`.
        """
        return self._get_pdftexmap_entry().effects

    @property
    def glyph_name_or_index(self):
        """
        Either the glyph name or the native charmap glyph index.

        If :file:`pdftex.map` specifies an encoding for this glyph's font, that
        is a mapping of glyph indices to Adobe glyph names; use it to convert
        dvi indices to glyph names.  Callers can then convert glyph names to
        glyph indices (with FT_Get_Name_Index/get_name_index), and load the
        glyph using FT_Load_Glyph/load_glyph.

        If :file:`pdftex.map` specifies no encoding, the indices directly map
        to the font's "native" charmap; glyphs should directly load using
        FT_Load_Char/load_char after selecting the native charmap.
        """
        entry = self._get_pdftexmap_entry()
        return (_parse_enc(entry.encoding)[self.glyph]
                if entry.encoding is not None else self.glyph)


# Opcode argument parsing
#
# Each of the following functions takes a Dvi object and delta, which is the
# difference between the opcode and the minimum opcode with the same meaning.
# Dvi opcodes often encode the number of argument bytes in this delta.
_arg_mapping = dict(
    # raw: Return delta as is.
    raw=lambda dvi, delta: delta,
    # u1: Read 1 byte as an unsigned number.
    u1=lambda dvi, delta: dvi._read_arg(1, signed=False),
    # u4: Read 4 bytes as an unsigned number.
    u4=lambda dvi, delta: dvi._read_arg(4, signed=False),
    # s4: Read 4 bytes as a signed number.
    s4=lambda dvi, delta: dvi._read_arg(4, signed=True),
    # slen: Read delta bytes as a signed number, or None if delta is None.
    slen=lambda dvi, delta: dvi._read_arg(delta, signed=True) if delta else None,
    # slen1: Read (delta + 1) bytes as a signed number.
    slen1=lambda dvi, delta: dvi._read_arg(delta + 1, signed=True),
    # ulen1: Read (delta + 1) bytes as an unsigned number.
    ulen1=lambda dvi, delta: dvi._read_arg(delta + 1, signed=False),
    # olen1: Read (delta + 1) bytes as an unsigned number if less than 4 bytes,
    # as a signed number if 4 bytes.
    olen1=lambda dvi, delta: dvi._read_arg(delta + 1, signed=(delta == 3)),
)


def _dispatch(table, min, max=None, state=None, args=('raw',)):
    """
    Decorator for dispatch by opcode. Sets the values in *table*
    from *min* to *max* to this method, adds a check that the Dvi state
    matches *state* if not None, reads arguments from the file according
    to *args*.

    Parameters
    ----------
    table : dict[int, callable]
        The dispatch table to be filled in.

    min, max : int
        Range of opcodes that calls the registered function; *max* defaults to
        *min*.

    state : _dvistate, optional
        State of the Dvi object in which these opcodes are allowed.

    args : list[str], default: ['raw']
        Sequence of argument specifications:

        - 'raw': opcode minus minimum
        - 'u1': read one unsigned byte
        - 'u4': read four bytes, treat as an unsigned number
        - 's4': read four bytes, treat as a signed number
        - 'slen': read (opcode - minimum) bytes, treat as signed
        - 'slen1': read (opcode - minimum + 1) bytes, treat as signed
        - 'ulen1': read (opcode - minimum + 1) bytes, treat as unsigned
        - 'olen1': read (opcode - minimum + 1) bytes, treat as unsigned
          if under four bytes, signed if four bytes
    """
    def decorate(method):
        get_args = [_arg_mapping[x] for x in args]

        @wraps(method)
        def wrapper(self, byte):
            if state is not None and self.state != state:
                raise ValueError("state precondition failed")
            return method(self, *[f(self, byte-min) for f in get_args])
        if max is None:
            table[min] = wrapper
        else:
            for i in range(min, max+1):
                assert table[i] is None
                table[i] = wrapper
        return wrapper
    return decorate


class Dvi:
    """
    A reader for a dvi ("device-independent") file, as produced by TeX.

    The current implementation can only iterate through pages in order,
    and does not even attempt to verify the postamble.

    This class can be used as a context manager to close the underlying
    file upon exit. Pages can be read via iteration. Here is an overly
    simple way to extract text without trying to detect whitespace::

        >>> with matplotlib.dviread.Dvi('input.dvi', 72) as dvi:
        ...     for page in dvi:
        ...         print(''.join(chr(t.glyph) for t in page.text))
    """
    # dispatch table
    _dtable = [None] * 256
    _dispatch = partial(_dispatch, _dtable)

    def __init__(self, filename, dpi):
        """
        Read the data from the file named *filename* and convert
        TeX's internal units to units of *dpi* per inch.
        *dpi* only sets the units and does not limit the resolution.
        Use None to return TeX's internal units.
        """
        _log.debug('Dvi: %s', filename)
        self.file = open(filename, 'rb')
        self.dpi = dpi
        self.fonts = {}
        self.state = _dvistate.pre
        self._missing_font = None

    def __enter__(self):
        """Context manager enter method, does nothing."""
        return self

    def __exit__(self, etype, evalue, etrace):
        """
        Context manager exit method, closes the underlying file if it is open.
        """
        self.close()

    def __iter__(self):
        """
        Iterate through the pages of the file.

        Yields
        ------
        Page
            Details of all the text and box objects on the page.
            The Page tuple contains lists of Text and Box tuples and
            the page dimensions, and the Text and Box tuples contain
            coordinates transformed into a standard Cartesian
            coordinate system at the dpi value given when initializing.
            The coordinates are floating point numbers, but otherwise
            precision is not lost and coordinate values are not clipped to
            integers.
        """
        while self._read():
            yield self._output()

    def close(self):
        """Close the underlying file if it is open."""
        if not self.file.closed:
            self.file.close()

    def _output(self):
        """
        Output the text and boxes belonging to the most recent page.
        page = dvi._output()
        """
        minx = miny = np.inf
        maxx = maxy = -np.inf
        maxy_pure = -np.inf
        for elt in self.text + self.boxes:
            if isinstance(elt, Box):
                x, y, h, w = elt
                e = 0  # zero depth
            else:  # glyph
                x, y, font, g, w = elt
                h, e = font._height_depth_of(g)
            minx = min(minx, x)
            miny = min(miny, y - h)
            maxx = max(maxx, x + w)
            maxy = max(maxy, y + e)
            maxy_pure = max(maxy_pure, y)
        if self._baseline_v is not None:
            maxy_pure = self._baseline_v  # This should normally be the case.
            self._baseline_v = None

        if not self.text and not self.boxes:  # Avoid infs/nans from inf+/-inf.
            return Page(text=[], boxes=[], width=0, height=0, descent=0)

        if self.dpi is None:
            # special case for ease of debugging: output raw dvi coordinates
            return Page(text=self.text, boxes=self.boxes,
                        width=maxx-minx, height=maxy_pure-miny,
                        descent=maxy-maxy_pure)

        # convert from TeX's "scaled points" to dpi units
        d = self.dpi / (72.27 * 2**16)
        descent = (maxy - maxy_pure) * d

        text = [Text((x-minx)*d, (maxy-y)*d - descent, f, g, w*d)
                for (x, y, f, g, w) in self.text]
        boxes = [Box((x-minx)*d, (maxy-y)*d - descent, h*d, w*d)
                 for (x, y, h, w) in self.boxes]

        return Page(text=text, boxes=boxes, width=(maxx-minx)*d,
                    height=(maxy_pure-miny)*d, descent=descent)

    def _read(self):
        """
        Read one page from the file. Return True if successful,
        False if there were no more pages.
        """
        # Pages appear to start with the sequence
        #   bop (begin of page)
        #   xxx comment
        #   <push, ..., pop>  # if using chemformula
        #   down
        #   push
        #     down
        #     <push, push, xxx, right, xxx, pop, pop>  # if using xcolor
        #     down
        #     push
        #       down (possibly multiple)
        #       push  <=  here, v is the baseline position.
        #         etc.
        # (dviasm is useful to explore this structure.)
        # Thus, we use the vertical position at the first time the stack depth
        # reaches 3, while at least three "downs" have been executed (excluding
        # those popped out (corresponding to the chemformula preamble)), as the
        # baseline (the "down" count is necessary to handle xcolor).
        down_stack = [0]
        self._baseline_v = None
        while True:
            byte = self.file.read(1)[0]
            self._dtable[byte](self, byte)
            if self._missing_font:
                raise self._missing_font.to_exception()
            name = self._dtable[byte].__name__
            if name == "_push":
                down_stack.append(down_stack[-1])
            elif name == "_pop":
                down_stack.pop()
            elif name == "_down":
                down_stack[-1] += 1
            if (self._baseline_v is None
                    and len(getattr(self, "stack", [])) == 3
                    and down_stack[-1] >= 4):
                self._baseline_v = self.v
            if byte == 140:                         # end of page
                return True
            if self.state is _dvistate.post_post:   # end of file
                self.close()
                return False

    def _read_arg(self, nbytes, signed=False):
        """
        Read and return a big-endian integer *nbytes* long.
        Signedness is determined by the *signed* keyword.
        """
        return int.from_bytes(self.file.read(nbytes), "big", signed=signed)

    @_dispatch(min=0, max=127, state=_dvistate.inpage)
    def _set_char_immediate(self, char):
        self._put_char_real(char)
        if isinstance(self.fonts[self.f], cbook._ExceptionInfo):
            return
        self.h += self.fonts[self.f]._width_of(char)

    @_dispatch(min=128, max=131, state=_dvistate.inpage, args=('olen1',))
    def _set_char(self, char):
        self._put_char_real(char)
        if isinstance(self.fonts[self.f], cbook._ExceptionInfo):
            return
        self.h += self.fonts[self.f]._width_of(char)

    @_dispatch(132, state=_dvistate.inpage, args=('s4', 's4'))
    def _set_rule(self, a, b):
        self._put_rule_real(a, b)
        self.h += b

    @_dispatch(min=133, max=136, state=_dvistate.inpage, args=('olen1',))
    def _put_char(self, char):
        self._put_char_real(char)

    def _put_char_real(self, char):
        font = self.fonts[self.f]
        if isinstance(font, cbook._ExceptionInfo):
            self._missing_font = font
        elif font._vf is None:
            self.text.append(Text(self.h, self.v, font, char,
                                  font._width_of(char)))
        else:
            scale = font._scale
            for x, y, f, g, w in font._vf[char].text:
                newf = DviFont(scale=_mul2012(scale, f._scale),
                               tfm=f._tfm, texname=f.texname, vf=f._vf)
                self.text.append(Text(self.h + _mul2012(x, scale),
                                      self.v + _mul2012(y, scale),
                                      newf, g, newf._width_of(g)))
            self.boxes.extend([Box(self.h + _mul2012(x, scale),
                                   self.v + _mul2012(y, scale),
                                   _mul2012(a, scale), _mul2012(b, scale))
                               for x, y, a, b in font._vf[char].boxes])

    @_dispatch(137, state=_dvistate.inpage, args=('s4', 's4'))
    def _put_rule(self, a, b):
        self._put_rule_real(a, b)

    def _put_rule_real(self, a, b):
        if a > 0 and b > 0:
            self.boxes.append(Box(self.h, self.v, a, b))

    @_dispatch(138)
    def _nop(self, _):
        pass

    @_dispatch(139, state=_dvistate.outer, args=('s4',)*11)
    def _bop(self, c0, c1, c2, c3, c4, c5, c6, c7, c8, c9, p):
        self.state = _dvistate.inpage
        self.h = self.v = self.w = self.x = self.y = self.z = 0
        self.stack = []
        self.text = []          # list of Text objects
        self.boxes = []         # list of Box objects

    @_dispatch(140, state=_dvistate.inpage)
    def _eop(self, _):
        self.state = _dvistate.outer
        del self.h, self.v, self.w, self.x, self.y, self.z, self.stack

    @_dispatch(141, state=_dvistate.inpage)
    def _push(self, _):
        self.stack.append((self.h, self.v, self.w, self.x, self.y, self.z))

    @_dispatch(142, state=_dvistate.inpage)
    def _pop(self, _):
        self.h, self.v, self.w, self.x, self.y, self.z = self.stack.pop()

    @_dispatch(min=143, max=146, state=_dvistate.inpage, args=('slen1',))
    def _right(self, b):
        self.h += b

    @_dispatch(min=147, max=151, state=_dvistate.inpage, args=('slen',))
    def _right_w(self, new_w):
        if new_w is not None:
            self.w = new_w
        self.h += self.w

    @_dispatch(min=152, max=156, state=_dvistate.inpage, args=('slen',))
    def _right_x(self, new_x):
        if new_x is not None:
            self.x = new_x
        self.h += self.x

    @_dispatch(min=157, max=160, state=_dvistate.inpage, args=('slen1',))
    def _down(self, a):
        self.v += a

    @_dispatch(min=161, max=165, state=_dvistate.inpage, args=('slen',))
    def _down_y(self, new_y):
        if new_y is not None:
            self.y = new_y
        self.v += self.y

    @_dispatch(min=166, max=170, state=_dvistate.inpage, args=('slen',))
    def _down_z(self, new_z):
        if new_z is not None:
            self.z = new_z
        self.v += self.z

    @_dispatch(min=171, max=234, state=_dvistate.inpage)
    def _fnt_num_immediate(self, k):
        self.f = k

    @_dispatch(min=235, max=238, state=_dvistate.inpage, args=('olen1',))
    def _fnt_num(self, new_f):
        self.f = new_f

    @_dispatch(min=239, max=242, args=('ulen1',))
    def _xxx(self, datalen):
        special = self.file.read(datalen)
        _log.debug(
            'Dvi._xxx: encountered special: %s',
            ''.join([chr(ch) if 32 <= ch < 127 else '<%02x>' % ch
                     for ch in special]))

    @_dispatch(min=243, max=246, args=('olen1', 'u4', 'u4', 'u4', 'u1', 'u1'))
    def _fnt_def(self, k, c, s, d, a, l):
        self._fnt_def_real(k, c, s, d, a, l)

    def _fnt_def_real(self, k, c, s, d, a, l):
        n = self.file.read(a + l)
        fontname = n[-l:].decode('ascii')
        try:
            tfm = _tfmfile(fontname)
        except FileNotFoundError as exc:
            # Explicitly allow defining missing fonts for Vf support; we only
            # register an error when trying to load a glyph from a missing font
            # and throw that error in Dvi._read.  For Vf, _finalize_packet
            # checks whether a missing glyph has been used, and in that case
            # skips the glyph definition.
            self.fonts[k] = cbook._ExceptionInfo.from_exception(exc)
            return
        if c != 0 and tfm.checksum != 0 and c != tfm.checksum:
            raise ValueError(f'tfm checksum mismatch: {n}')
        try:
            vf = _vffile(fontname)
        except FileNotFoundError:
            vf = None
        self.fonts[k] = DviFont(scale=s, tfm=tfm, texname=n, vf=vf)

    @_dispatch(247, state=_dvistate.pre, args=('u1', 'u4', 'u4', 'u4', 'u1'))
    def _pre(self, i, num, den, mag, k):
        self.file.read(k)  # comment in the dvi file
        if i != 2:
            raise ValueError(f"Unknown dvi format {i}")
        if num != 25400000 or den != 7227 * 2**16:
            raise ValueError("Nonstandard units in dvi file")
            # meaning: TeX always uses those exact values, so it
            # should be enough for us to support those
            # (There are 72.27 pt to an inch so 7227 pt =
            # 7227 * 2**16 sp to 100 in. The numerator is multiplied
            # by 10^5 to get units of 10**-7 meters.)
        if mag != 1000:
            raise ValueError("Nonstandard magnification in dvi file")
            # meaning: LaTeX seems to frown on setting \mag, so
            # I think we can assume this is constant
        self.state = _dvistate.outer

    @_dispatch(248, state=_dvistate.outer)
    def _post(self, _):
        self.state = _dvistate.post_post
        # TODO: actually read the postamble and finale?
        # currently post_post just triggers closing the file

    @_dispatch(249)
    def _post_post(self, _):
        raise NotImplementedError

    @_dispatch(min=250, max=255)
    def _malformed(self, offset):
        raise ValueError(f"unknown command: byte {250 + offset}")


class DviFont:
    """
    Encapsulation of a font that a DVI file can refer to.

    This class holds a font's texname and size, supports comparison,
    and knows the widths of glyphs in the same units as the AFM file.
    There are also internal attributes (for use by dviread.py) that
    are *not* used for comparison.

    The size is in Adobe points (converted from TeX points).

    Parameters
    ----------
    scale : float
        Factor by which the font is scaled from its natural size.
    tfm : Tfm
        TeX font metrics for this font
    texname : bytes
       Name of the font as used internally by TeX and friends, as an ASCII
       bytestring.  This is usually very different from any external font
       names; `PsfontsMap` can be used to find the external name of the font.
    vf : Vf
       A TeX "virtual font" file, or None if this font is not virtual.

    Attributes
    ----------
    texname : bytes
    size : float
       Size of the font in Adobe points, converted from the slightly
       smaller TeX points.
    widths : list
       Widths of glyphs in glyph-space units, typically 1/1000ths of
       the point size.

    """
    __slots__ = ('texname', 'size', 'widths', '_scale', '_vf', '_tfm')

    def __init__(self, scale, tfm, texname, vf):
        _api.check_isinstance(bytes, texname=texname)
        self._scale = scale
        self._tfm = tfm
        self.texname = texname
        self._vf = vf
        self.size = scale * (72.0 / (72.27 * 2**16))
        try:
            nchars = max(tfm.width) + 1
        except ValueError:
            nchars = 0
        self.widths = [(1000*tfm.width.get(char, 0)) >> 20
                       for char in range(nchars)]

    def __eq__(self, other):
        return (type(self) is type(other)
                and self.texname == other.texname and self.size == other.size)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return f"<{type(self).__name__}: {self.texname}>"

    def _width_of(self, char):
        """Width of char in dvi units."""
        width = self._tfm.width.get(char, None)
        if width is not None:
            return _mul2012(width, self._scale)
        _log.debug('No width for char %d in font %s.', char, self.texname)
        return 0

    def _height_depth_of(self, char):
        """Height and depth of char in dvi units."""
        result = []
        for metric, name in ((self._tfm.height, "height"),
                             (self._tfm.depth, "depth")):
            value = metric.get(char, None)
            if value is None:
                _log.debug('No %s for char %d in font %s',
                           name, char, self.texname)
                result.append(0)
            else:
                result.append(_mul2012(value, self._scale))
        # cmsyXX (symbols font) glyph 0 ("minus") has a nonzero descent
        # so that TeX aligns equations properly
        # (https://tex.stackexchange.com/q/526103/)
        # but we actually care about the rasterization depth to align
        # the dvipng-generated images.
        if re.match(br'^cmsy\d+$', self.texname) and char == 0:
            result[-1] = 0
        return result


class Vf(Dvi):
    r"""
    A virtual font (\*.vf file) containing subroutines for dvi files.

    Parameters
    ----------
    filename : str or path-like

    Notes
    -----
    The virtual font format is a derivative of dvi:
    http://mirrors.ctan.org/info/knuth/virtual-fonts
    This class reuses some of the machinery of `Dvi`
    but replaces the `_read` loop and dispatch mechanism.

    Examples
    --------
    ::

        vf = Vf(filename)
        glyph = vf[code]
        glyph.text, glyph.boxes, glyph.width
    """

    def __init__(self, filename):
        super().__init__(filename, 0)
        try:
            self._first_font = None
            self._chars = {}
            self._read()
        finally:
            self.close()

    def __getitem__(self, code):
        return self._chars[code]

    def _read(self):
        """
        Read one page from the file. Return True if successful,
        False if there were no more pages.
        """
        packet_char = packet_ends = None
        packet_len = packet_width = None
        while True:
            byte = self.file.read(1)[0]
            # If we are in a packet, execute the dvi instructions
            if self.state is _dvistate.inpage:
                byte_at = self.file.tell()-1
                if byte_at == packet_ends:
                    self._finalize_packet(packet_char, packet_width)
                    packet_len = packet_char = packet_width = None
                    # fall through to out-of-packet code
                elif byte_at > packet_ends:
                    raise ValueError("Packet length mismatch in vf file")
                else:
                    if byte in (139, 140) or byte >= 243:
                        raise ValueError(f"Inappropriate opcode {byte} in vf file")
                    Dvi._dtable[byte](self, byte)
                    continue

            # We are outside a packet
            if byte < 242:          # a short packet (length given by byte)
                packet_len = byte
                packet_char = self._read_arg(1)
                packet_width = self._read_arg(3)
                packet_ends = self._init_packet(byte)
                self.state = _dvistate.inpage
            elif byte == 242:       # a long packet
                packet_len = self._read_arg(4)
                packet_char = self._read_arg(4)
                packet_width = self._read_arg(4)
                self._init_packet(packet_len)
            elif 243 <= byte <= 246:
                k = self._read_arg(byte - 242, byte == 246)
                c = self._read_arg(4)
                s = self._read_arg(4)
                d = self._read_arg(4)
                a = self._read_arg(1)
                l = self._read_arg(1)
                self._fnt_def_real(k, c, s, d, a, l)
                if self._first_font is None:
                    self._first_font = k
            elif byte == 247:       # preamble
                i = self._read_arg(1)
                k = self._read_arg(1)
                x = self.file.read(k)
                cs = self._read_arg(4)
                ds = self._read_arg(4)
                self._pre(i, x, cs, ds)
            elif byte == 248:       # postamble (just some number of 248s)
                break
            else:
                raise ValueError(f"Unknown vf opcode {byte}")

    def _init_packet(self, pl):
        if self.state != _dvistate.outer:
            raise ValueError("Misplaced packet in vf file")
        self.h = self.v = self.w = self.x = self.y = self.z = 0
        self.stack = []
        self.text = []
        self.boxes = []
        self.f = self._first_font
        self._missing_font = None
        return self.file.tell() + pl

    def _finalize_packet(self, packet_char, packet_width):
        if not self._missing_font:  # Otherwise we don't have full glyph definition.
            self._chars[packet_char] = Page(
                text=self.text, boxes=self.boxes, width=packet_width,
                height=None, descent=None)
        self.state = _dvistate.outer

    def _pre(self, i, x, cs, ds):
        if self.state is not _dvistate.pre:
            raise ValueError("pre command in middle of vf file")
        if i != 202:
            raise ValueError(f"Unknown vf format {i}")
        if len(x):
            _log.debug('vf file comment: %s', x)
        self.state = _dvistate.outer
        # cs = checksum, ds = design size


def _mul2012(num1, num2):
    """Multiply two numbers in 20.12 fixed point format."""
    # Separated into a function because >> has surprising precedence
    return (num1*num2) >> 20


class Tfm:
    """
    A TeX Font Metric file.

    This implementation covers only the bare minimum needed by the Dvi class.

    Parameters
    ----------
    filename : str or path-like

    Attributes
    ----------
    checksum : int
       Used for verifying against the dvi file.
    design_size : int
       Design size of the font (unknown units)
    width, height, depth : dict
       Dimensions of each character, need to be scaled by the factor
       specified in the dvi file. These are dicts because indexing may
       not start from 0.
    """
    __slots__ = ('checksum', 'design_size', 'width', 'height', 'depth')

    def __init__(self, filename):
        _log.debug('opening tfm file %s', filename)
        with open(filename, 'rb') as file:
            header1 = file.read(24)
            lh, bc, ec, nw, nh, nd = struct.unpack('!6H', header1[2:14])
            _log.debug('lh=%d, bc=%d, ec=%d, nw=%d, nh=%d, nd=%d',
                       lh, bc, ec, nw, nh, nd)
            header2 = file.read(4*lh)
            self.checksum, self.design_size = struct.unpack('!2I', header2[:8])
            # there is also encoding information etc.
            char_info = file.read(4*(ec-bc+1))
            widths = struct.unpack(f'!{nw}i', file.read(4*nw))
            heights = struct.unpack(f'!{nh}i', file.read(4*nh))
            depths = struct.unpack(f'!{nd}i', file.read(4*nd))
        self.width = {}
        self.height = {}
        self.depth = {}
        for idx, char in enumerate(range(bc, ec+1)):
            byte0 = char_info[4*idx]
            byte1 = char_info[4*idx+1]
            self.width[char] = widths[byte0]
            self.height[char] = heights[byte1 >> 4]
            self.depth[char] = depths[byte1 & 0xf]


PsFont = namedtuple('PsFont', 'texname psname effects encoding filename')


class PsfontsMap:
    """
    A psfonts.map formatted file, mapping TeX fonts to PS fonts.

    Parameters
    ----------
    filename : str or path-like

    Notes
    -----
    For historical reasons, TeX knows many Type-1 fonts by different
    names than the outside world. (For one thing, the names have to
    fit in eight characters.) Also, TeX's native fonts are not Type-1
    but Metafont, which is nontrivial to convert to PostScript except
    as a bitmap. While high-quality conversions to Type-1 format exist
    and are shipped with modern TeX distributions, we need to know
    which Type-1 fonts are the counterparts of which native fonts. For
    these reasons a mapping is needed from internal font names to font
    file names.

    A texmf tree typically includes mapping files called e.g.
    :file:`psfonts.map`, :file:`pdftex.map`, or :file:`dvipdfm.map`.
    The file :file:`psfonts.map` is used by :program:`dvips`,
    :file:`pdftex.map` by :program:`pdfTeX`, and :file:`dvipdfm.map`
    by :program:`dvipdfm`. :file:`psfonts.map` might avoid embedding
    the 35 PostScript fonts (i.e., have no filename for them, as in
    the Times-Bold example above), while the pdf-related files perhaps
    only avoid the "Base 14" pdf fonts. But the user may have
    configured these files differently.

    Examples
    --------
    >>> map = PsfontsMap(find_tex_file('pdftex.map'))
    >>> entry = map[b'ptmbo8r']
    >>> entry.texname
    b'ptmbo8r'
    >>> entry.psname
    b'Times-Bold'
    >>> entry.encoding
    '/usr/local/texlive/2008/texmf-dist/fonts/enc/dvips/base/8r.enc'
    >>> entry.effects
    {'slant': 0.16700000000000001}
    >>> entry.filename
    """
    __slots__ = ('_filename', '_unparsed', '_parsed')

    # Create a filename -> PsfontsMap cache, so that calling
    # `PsfontsMap(filename)` with the same filename a second time immediately
    # returns the same object.
    @lru_cache
    def __new__(cls, filename):
        self = object.__new__(cls)
        self._filename = os.fsdecode(filename)
        # Some TeX distributions have enormous pdftex.map files which would
        # take hundreds of milliseconds to parse, but it is easy enough to just
        # store the unparsed lines (keyed by the first word, which is the
        # texname) and parse them on-demand.
        with open(filename, 'rb') as file:
            self._unparsed = {}
            for line in file:
                tfmname = line.split(b' ', 1)[0]
                self._unparsed.setdefault(tfmname, []).append(line)
        self._parsed = {}
        return self

    def __getitem__(self, texname):
        assert isinstance(texname, bytes)
        if texname in self._unparsed:
            for line in self._unparsed.pop(texname):
                if self._parse_and_cache_line(line):
                    break
        try:
            return self._parsed[texname]
        except KeyError:
            raise LookupError(
                f"An associated PostScript font (required by Matplotlib) "
                f"could not be found for TeX font {texname.decode('ascii')!r} "
                f"in {self._filename!r}; this problem can often be solved by "
                f"installing a suitable PostScript font package in your TeX "
                f"package manager") from None

    def _parse_and_cache_line(self, line):
        """
        Parse a line in the font mapping file.

        The format is (partially) documented at
        http://mirrors.ctan.org/systems/doc/pdftex/manual/pdftex-a.pdf
        https://tug.org/texinfohtml/dvips.html#psfonts_002emap
        Each line can have the following fields:

        - tfmname (first, only required field),
        - psname (defaults to tfmname, must come immediately after tfmname if
          present),
        - fontflags (integer, must come immediately after psname if present,
          ignored by us),
        - special (SlantFont and ExtendFont, only field that is double-quoted),
        - fontfile, encodingfile (optional, prefixed by <, <<, or <[; << always
          precedes a font, <[ always precedes an encoding, < can precede either
          but then an encoding file must have extension .enc; < and << also
          request different font subsetting behaviors but we ignore that; < can
          be separated from the filename by whitespace).

        special, fontfile, and encodingfile can appear in any order.
        """
        # If the map file specifies multiple encodings for a font, we
        # follow pdfTeX in choosing the last one specified. Such
        # entries are probably mistakes but they have occurred.
        # https://tex.stackexchange.com/q/10826/

        if not line or line.startswith((b" ", b"%", b"*", b";", b"#")):
            return
        tfmname = basename = special = encodingfile = fontfile = None
        is_subsetted = is_t1 = is_truetype = False
        matches = re.finditer(br'"([^"]*)(?:"|$)|(\S+)', line)
        for match in matches:
            quoted, unquoted = match.groups()
            if unquoted:
                if unquoted.startswith(b"<<"):  # font
                    fontfile = unquoted[2:]
                elif unquoted.startswith(b"<["):  # encoding
                    encodingfile = unquoted[2:]
                elif unquoted.startswith(b"<"):  # font or encoding
                    word = (
                        # <foo => foo
                        unquoted[1:]
                        # < by itself => read the next word
                        or next(filter(None, next(matches).groups())))
                    if word.endswith(b".enc"):
                        encodingfile = word
                    else:
                        fontfile = word
                        is_subsetted = True
                elif tfmname is None:
                    tfmname = unquoted
                elif basename is None:
                    basename = unquoted
            elif quoted:
                special = quoted
        effects = {}
        if special:
            words = reversed(special.split())
            for word in words:
                if word == b"SlantFont":
                    effects["slant"] = float(next(words))
                elif word == b"ExtendFont":
                    effects["extend"] = float(next(words))

        # Verify some properties of the line that would cause it to be ignored
        # otherwise.
        if fontfile is not None:
            if fontfile.endswith((b".ttf", b".ttc")):
                is_truetype = True
            elif not fontfile.endswith(b".otf"):
                is_t1 = True
        elif basename is not None:
            is_t1 = True
        if is_truetype and is_subsetted and encodingfile is None:
            return
        if not is_t1 and ("slant" in effects or "extend" in effects):
            return
        if abs(effects.get("slant", 0)) > 1:
            return
        if abs(effects.get("extend", 0)) > 2:
            return

        if basename is None:
            basename = tfmname
        if encodingfile is not None:
            encodingfile = find_tex_file(encodingfile)
        if fontfile is not None:
            fontfile = find_tex_file(fontfile)
        self._parsed[tfmname] = PsFont(
            texname=tfmname, psname=basename, effects=effects,
            encoding=encodingfile, filename=fontfile)
        return True


def _parse_enc(path):
    r"""
    Parse a \*.enc file referenced from a psfonts.map style file.

    The format supported by this function is a tiny subset of PostScript.

    Parameters
    ----------
    path : `os.PathLike`

    Returns
    -------
    list
        The nth entry of the list is the PostScript glyph name of the nth
        glyph.
    """
    no_comments = re.sub("%.*", "", Path(path).read_text(encoding="ascii"))
    array = re.search(r"(?s)\[(.*)\]", no_comments).group(1)
    lines = [line for line in array.split() if line]
    if all(line.startswith("/") for line in lines):
        return [line[1:] for line in lines]
    else:
        raise ValueError(f"Failed to parse {path} as Postscript encoding")


class _LuatexKpsewhich:
    @lru_cache  # A singleton.
    def __new__(cls):
        self = object.__new__(cls)
        self._proc = self._new_proc()
        return self

    def _new_proc(self):
        return subprocess.Popen(
            ["luatex", "--luaonly",
             str(cbook._get_data_path("kpsewhich.lua"))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def search(self, filename):
        if self._proc.poll() is not None:  # Dead, restart it.
            self._proc = self._new_proc()
        self._proc.stdin.write(os.fsencode(filename) + b"\n")
        self._proc.stdin.flush()
        out = self._proc.stdout.readline().rstrip()
        return None if out == b"nil" else os.fsdecode(out)


@lru_cache
def find_tex_file(filename):
    """
    Find a file in the texmf tree using kpathsea_.

    The kpathsea library, provided by most existing TeX distributions, both
    on Unix-like systems and on Windows (MikTeX), is invoked via a long-lived
    luatex process if luatex is installed, or via kpsewhich otherwise.

    .. _kpathsea: https://www.tug.org/kpathsea/

    Parameters
    ----------
    filename : str or path-like

    Raises
    ------
    FileNotFoundError
        If the file is not found.
    """

    # we expect these to always be ascii encoded, but use utf-8
    # out of caution
    if isinstance(filename, bytes):
        filename = filename.decode('utf-8', errors='replace')

    try:
        lk = _LuatexKpsewhich()
    except FileNotFoundError:
        lk = None  # Fallback to directly calling kpsewhich, as below.

    if lk:
        path = lk.search(filename)
    else:
        if sys.platform == 'win32':
            # On Windows only, kpathsea can use utf-8 for cmd args and output.
            # The `command_line_encoding` environment variable is set to force
            # it to always use utf-8 encoding.  See Matplotlib issue #11848.
            kwargs = {'env': {**os.environ, 'command_line_encoding': 'utf-8'},
                      'encoding': 'utf-8'}
        else:  # On POSIX, run through the equivalent of os.fsdecode().
            kwargs = {'encoding': sys.getfilesystemencoding(),
                      'errors': 'surrogateescape'}

        try:
            path = (cbook._check_and_log_subprocess(['kpsewhich', filename],
                                                    _log, **kwargs)
                    .rstrip('\n'))
        except (FileNotFoundError, RuntimeError):
            path = None

    if path:
        return path
    else:
        raise FileNotFoundError(
            f"Matplotlib's TeX implementation searched for a file named "
            f"{filename!r} in your texmf tree, but could not find it")


@lru_cache
def _fontfile(cls, suffix, texname):
    return cls(find_tex_file(texname + suffix))


_tfmfile = partial(_fontfile, Tfm, ".tfm")
_vffile = partial(_fontfile, Vf, ".vf")


if __name__ == '__main__':
    from argparse import ArgumentParser
    import itertools

    parser = ArgumentParser()
    parser.add_argument("filename")
    parser.add_argument("dpi", nargs="?", type=float, default=None)
    args = parser.parse_args()
    with Dvi(args.filename, args.dpi) as dvi:
        fontmap = PsfontsMap(find_tex_file('pdftex.map'))
        for page in dvi:
            print(f"=== new page === "
                  f"(w: {page.width}, h: {page.height}, d: {page.descent})")
            for font, group in itertools.groupby(
                    page.text, lambda text: text.font):
                print(f"font: {font.texname.decode('latin-1')!r}\t"
                      f"scale: {font._scale / 2 ** 20}")
                print("x", "y", "glyph", "chr", "w", "(glyphs)", sep="\t")
                for text in group:
                    print(text.x, text.y, text.glyph,
                          chr(text.glyph) if chr(text.glyph).isprintable()
                          else ".",
                          text.width, sep="\t")
            if page.boxes:
                print("x", "y", "h", "w", "", "(boxes)", sep="\t")
                for box in page.boxes:
                    print(box.x, box.y, box.height, box.width, sep="\t")
