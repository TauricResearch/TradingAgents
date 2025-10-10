"""
A PostScript backend, which can produce both PostScript .ps and .eps.
"""

import bisect
import codecs
import datetime
from enum import Enum
import functools
from io import StringIO
import itertools
import logging
import math
import os
import pathlib
import shutil
import struct
from tempfile import TemporaryDirectory
import textwrap
import time

import fontTools
import numpy as np

import matplotlib as mpl
from matplotlib import _api, cbook, _path, _text_helpers
from matplotlib._afm import AFM
from matplotlib.backend_bases import (
    _Backend, FigureCanvasBase, FigureManagerBase, RendererBase)
from matplotlib.cbook import is_writable_file_like, file_requires_unicode
from matplotlib.font_manager import get_font
from matplotlib.ft2font import LoadFlags
from matplotlib._mathtext_data import uni2type1
from matplotlib.path import Path
from matplotlib.texmanager import TexManager
from matplotlib.transforms import Affine2D
from matplotlib.backends.backend_mixed import MixedModeRenderer
from . import _backend_pdf_ps


_log = logging.getLogger(__name__)
debugPS = False


papersize = {'letter': (8.5, 11),
             'legal': (8.5, 14),
             'ledger': (11, 17),
             'a0': (33.11, 46.81),
             'a1': (23.39, 33.11),
             'a2': (16.54, 23.39),
             'a3': (11.69, 16.54),
             'a4': (8.27, 11.69),
             'a5': (5.83, 8.27),
             'a6': (4.13, 5.83),
             'a7': (2.91, 4.13),
             'a8': (2.05, 2.91),
             'a9': (1.46, 2.05),
             'a10': (1.02, 1.46),
             'b0': (40.55, 57.32),
             'b1': (28.66, 40.55),
             'b2': (20.27, 28.66),
             'b3': (14.33, 20.27),
             'b4': (10.11, 14.33),
             'b5': (7.16, 10.11),
             'b6': (5.04, 7.16),
             'b7': (3.58, 5.04),
             'b8': (2.51, 3.58),
             'b9': (1.76, 2.51),
             'b10': (1.26, 1.76)}


def _nums_to_str(*args, sep=" "):
    return sep.join(f"{arg:1.3f}".rstrip("0").rstrip(".") for arg in args)


def _move_path_to_path_or_stream(src, dst):
    """
    Move the contents of file at *src* to path-or-filelike *dst*.

    If *dst* is a path, the metadata of *src* are *not* copied.
    """
    if is_writable_file_like(dst):
        fh = (open(src, encoding='latin-1')
              if file_requires_unicode(dst)
              else open(src, 'rb'))
        with fh:
            shutil.copyfileobj(fh, dst)
    else:
        shutil.move(src, dst, copy_function=shutil.copyfile)


def _font_to_ps_type3(font_path, chars):
    """
    Subset *chars* from the font at *font_path* into a Type 3 font.

    Parameters
    ----------
    font_path : path-like
        Path to the font to be subsetted.
    chars : str
        The characters to include in the subsetted font.

    Returns
    -------
    str
        The string representation of a Type 3 font, which can be included
        verbatim into a PostScript file.
    """
    font = get_font(font_path, hinting_factor=1)
    glyph_ids = [font.get_char_index(c) for c in chars]

    preamble = """\
%!PS-Adobe-3.0 Resource-Font
%%Creator: Converted from TrueType to Type 3 by Matplotlib.
10 dict begin
/FontName /{font_name} def
/PaintType 0 def
/FontMatrix [{inv_units_per_em} 0 0 {inv_units_per_em} 0 0] def
/FontBBox [{bbox}] def
/FontType 3 def
/Encoding [{encoding}] def
/CharStrings {num_glyphs} dict dup begin
/.notdef 0 def
""".format(font_name=font.postscript_name,
           inv_units_per_em=1 / font.units_per_EM,
           bbox=" ".join(map(str, font.bbox)),
           encoding=" ".join(f"/{font.get_glyph_name(glyph_id)}"
                             for glyph_id in glyph_ids),
           num_glyphs=len(glyph_ids) + 1)
    postamble = """
end readonly def

/BuildGlyph {
 exch begin
 CharStrings exch
 2 copy known not {pop /.notdef} if
 true 3 1 roll get exec
 end
} _d

/BuildChar {
 1 index /Encoding get exch get
 1 index /BuildGlyph get exec
} _d

FontName currentdict end definefont pop
"""

    entries = []
    for glyph_id in glyph_ids:
        g = font.load_glyph(glyph_id, LoadFlags.NO_SCALE)
        v, c = font.get_path()
        entries.append(
            "/%(name)s{%(bbox)s sc\n" % {
                "name": font.get_glyph_name(glyph_id),
                "bbox": " ".join(map(str, [g.horiAdvance, 0, *g.bbox])),
            }
            + _path.convert_to_string(
                # Convert back to TrueType's internal units (1/64's).
                # (Other dimensions are already in these units.)
                Path(v * 64, c), None, None, False, None, 0,
                # No code for quad Beziers triggers auto-conversion to cubics.
                # Drop intermediate closepolys (relying on the outline
                # decomposer always explicitly moving to the closing point
                # first).
                [b"m", b"l", b"", b"c", b""], True).decode("ascii")
            + "ce} _d"
        )

    return preamble + "\n".join(entries) + postamble


def _font_to_ps_type42(font_path, chars, fh):
    """
    Subset *chars* from the font at *font_path* into a Type 42 font at *fh*.

    Parameters
    ----------
    font_path : path-like
        Path to the font to be subsetted.
    chars : str
        The characters to include in the subsetted font.
    fh : file-like
        Where to write the font.
    """
    subset_str = ''.join(chr(c) for c in chars)
    _log.debug("SUBSET %s characters: %s", font_path, subset_str)
    try:
        kw = {}
        # fix this once we support loading more fonts from a collection
        # https://github.com/matplotlib/matplotlib/issues/3135#issuecomment-571085541
        if font_path.endswith('.ttc'):
            kw['fontNumber'] = 0
        with (fontTools.ttLib.TTFont(font_path, **kw) as font,
              _backend_pdf_ps.get_glyphs_subset(font_path, subset_str) as subset):
            fontdata = _backend_pdf_ps.font_as_file(subset).getvalue()
            _log.debug(
                "SUBSET %s %d -> %d", font_path, os.stat(font_path).st_size,
                len(fontdata)
            )
            fh.write(_serialize_type42(font, subset, fontdata))
    except RuntimeError:
        _log.warning(
            "The PostScript backend does not currently support the selected font (%s).",
            font_path)
        raise


def _serialize_type42(font, subset, fontdata):
    """
    Output a PostScript Type-42 format representation of font

    Parameters
    ----------
    font : fontTools.ttLib.ttFont.TTFont
        The original font object
    subset : fontTools.ttLib.ttFont.TTFont
        The subset font object
    fontdata : bytes
        The raw font data in TTF format

    Returns
    -------
    str
        The Type-42 formatted font
    """
    version, breakpoints = _version_and_breakpoints(font.get('loca'), fontdata)
    post = font['post']
    name = font['name']
    chars = _generate_charstrings(subset)
    sfnts = _generate_sfnts(fontdata, subset, breakpoints)
    return textwrap.dedent(f"""
        %%!PS-TrueTypeFont-{version[0]}.{version[1]}-{font['head'].fontRevision:.7f}
        10 dict begin
        /FontType 42 def
        /FontMatrix [1 0 0 1 0 0] def
        /FontName /{name.getDebugName(6)} def
        /FontInfo 7 dict dup begin
        /FullName ({name.getDebugName(4)}) def
        /FamilyName ({name.getDebugName(1)}) def
        /Version ({name.getDebugName(5)}) def
        /ItalicAngle {post.italicAngle} def
        /isFixedPitch {'true' if post.isFixedPitch else 'false'} def
        /UnderlinePosition {post.underlinePosition} def
        /UnderlineThickness {post.underlineThickness} def
        end readonly def
        /Encoding StandardEncoding def
        /FontBBox [{_nums_to_str(*_bounds(font))}] def
        /PaintType 0 def
        /CIDMap 0 def
        {chars}
        {sfnts}
        FontName currentdict end definefont pop
        """)


def _version_and_breakpoints(loca, fontdata):
    """
    Read the version number of the font and determine sfnts breakpoints.

    When a TrueType font file is written as a Type 42 font, it has to be
    broken into substrings of at most 65535 bytes. These substrings must
    begin at font table boundaries or glyph boundaries in the glyf table.
    This function determines all possible breakpoints and it is the caller's
    responsibility to do the splitting.

    Helper function for _font_to_ps_type42.

    Parameters
    ----------
    loca : fontTools.ttLib._l_o_c_a.table__l_o_c_a or None
        The loca table of the font if available
    fontdata : bytes
        The raw data of the font

    Returns
    -------
    version : tuple[int, int]
        A 2-tuple of the major version number and minor version number.
    breakpoints : list[int]
        The breakpoints is a sorted list of offsets into fontdata; if loca is not
        available, just the table boundaries.
    """
    v1, v2, numTables = struct.unpack('>3h', fontdata[:6])
    version = (v1, v2)

    tables = {}
    for i in range(numTables):
        tag, _, offset, _ = struct.unpack('>4sIII', fontdata[12 + i*16:12 + (i+1)*16])
        tables[tag.decode('ascii')] = offset
    if loca is not None:
        glyf_breakpoints = {tables['glyf'] + offset for offset in loca.locations[:-1]}
    else:
        glyf_breakpoints = set()
    breakpoints = sorted({*tables.values(), *glyf_breakpoints, len(fontdata)})

    return version, breakpoints


def _bounds(font):
    """
    Compute the font bounding box, as if all glyphs were written
    at the same start position.

    Helper function for _font_to_ps_type42.

    Parameters
    ----------
    font : fontTools.ttLib.ttFont.TTFont
        The font

    Returns
    -------
    tuple
        (xMin, yMin, xMax, yMax) of the combined bounding box
        of all the glyphs in the font
    """
    gs = font.getGlyphSet(False)
    pen = fontTools.pens.boundsPen.BoundsPen(gs)
    for name in gs.keys():
        gs[name].draw(pen)
    return pen.bounds or (0, 0, 0, 0)


def _generate_charstrings(font):
    """
    Transform font glyphs into CharStrings

    Helper function for _font_to_ps_type42.

    Parameters
    ----------
    font : fontTools.ttLib.ttFont.TTFont
        The font

    Returns
    -------
    str
        A definition of the CharStrings dictionary in PostScript
    """
    go = font.getGlyphOrder()
    s = f'/CharStrings {len(go)} dict dup begin\n'
    for i, name in enumerate(go):
        s += f'/{name} {i} def\n'
    s += 'end readonly def'
    return s


def _generate_sfnts(fontdata, font, breakpoints):
    """
    Transform font data into PostScript sfnts format.

    Helper function for _font_to_ps_type42.

    Parameters
    ----------
    fontdata : bytes
        The raw data of the font
    font : fontTools.ttLib.ttFont.TTFont
        The fontTools font object
    breakpoints : list
        Sorted offsets of possible breakpoints

    Returns
    -------
    str
        The sfnts array for the font definition, consisting
        of hex-encoded strings in PostScript format
    """
    s = '/sfnts['
    pos = 0
    while pos < len(fontdata):
        i = bisect.bisect_left(breakpoints, pos + 65534)
        newpos = breakpoints[i-1]
        if newpos <= pos:
            # have to accept a larger string
            newpos = breakpoints[-1]
        s += f'<{fontdata[pos:newpos].hex()}00>'  # Always NUL terminate.
        pos = newpos
    s += ']def'
    return '\n'.join(s[i:i+100] for i in range(0, len(s), 100))


def _log_if_debug_on(meth):
    """
    Wrap `RendererPS` method *meth* to emit a PS comment with the method name,
    if the global flag `debugPS` is set.
    """
    @functools.wraps(meth)
    def wrapper(self, *args, **kwargs):
        if debugPS:
            self._pswriter.write(f"% {meth.__name__}\n")
        return meth(self, *args, **kwargs)

    return wrapper


class RendererPS(_backend_pdf_ps.RendererPDFPSBase):
    """
    The renderer handles all the drawing primitives using a graphics
    context instance that controls the colors/styles.
    """

    _afm_font_dir = cbook._get_data_path("fonts/afm")
    _use_afm_rc_name = "ps.useafm"

    def __init__(self, width, height, pswriter, imagedpi=72):
        # Although postscript itself is dpi independent, we need to inform the
        # image code about a requested dpi to generate high resolution images
        # and them scale them before embedding them.
        super().__init__(width, height)
        self._pswriter = pswriter
        if mpl.rcParams['text.usetex']:
            self.textcnt = 0
            self.psfrag = []
        self.imagedpi = imagedpi

        # current renderer state (None=uninitialised)
        self.color = None
        self.linewidth = None
        self.linejoin = None
        self.linecap = None
        self.linedash = None
        self.fontname = None
        self.fontsize = None
        self._hatches = {}
        self.image_magnification = imagedpi / 72
        self._clip_paths = {}
        self._path_collection_id = 0

        self._character_tracker = _backend_pdf_ps.CharacterTracker()
        self._logwarn_once = functools.cache(_log.warning)

    def _is_transparent(self, rgb_or_rgba):
        if rgb_or_rgba is None:
            return True  # Consistent with rgbFace semantics.
        elif len(rgb_or_rgba) == 4:
            if rgb_or_rgba[3] == 0:
                return True
            if rgb_or_rgba[3] != 1:
                self._logwarn_once(
                    "The PostScript backend does not support transparency; "
                    "partially transparent artists will be rendered opaque.")
            return False
        else:  # len() == 3.
            return False

    def set_color(self, r, g, b, store=True):
        if (r, g, b) != self.color:
            self._pswriter.write(f"{_nums_to_str(r)} setgray\n"
                                 if r == g == b else
                                 f"{_nums_to_str(r, g, b)} setrgbcolor\n")
            if store:
                self.color = (r, g, b)

    def set_linewidth(self, linewidth, store=True):
        linewidth = float(linewidth)
        if linewidth != self.linewidth:
            self._pswriter.write(f"{_nums_to_str(linewidth)} setlinewidth\n")
            if store:
                self.linewidth = linewidth

    @staticmethod
    def _linejoin_cmd(linejoin):
        # Support for directly passing integer values is for backcompat.
        linejoin = {'miter': 0, 'round': 1, 'bevel': 2, 0: 0, 1: 1, 2: 2}[
            linejoin]
        return f"{linejoin:d} setlinejoin\n"

    def set_linejoin(self, linejoin, store=True):
        if linejoin != self.linejoin:
            self._pswriter.write(self._linejoin_cmd(linejoin))
            if store:
                self.linejoin = linejoin

    @staticmethod
    def _linecap_cmd(linecap):
        # Support for directly passing integer values is for backcompat.
        linecap = {'butt': 0, 'round': 1, 'projecting': 2, 0: 0, 1: 1, 2: 2}[
            linecap]
        return f"{linecap:d} setlinecap\n"

    def set_linecap(self, linecap, store=True):
        if linecap != self.linecap:
            self._pswriter.write(self._linecap_cmd(linecap))
            if store:
                self.linecap = linecap

    def set_linedash(self, offset, seq, store=True):
        if self.linedash is not None:
            oldo, oldseq = self.linedash
            if np.array_equal(seq, oldseq) and oldo == offset:
                return

        self._pswriter.write(f"[{_nums_to_str(*seq)}] {_nums_to_str(offset)} setdash\n"
                             if seq is not None and len(seq) else
                             "[] 0 setdash\n")
        if store:
            self.linedash = (offset, seq)

    def set_font(self, fontname, fontsize, store=True):
        if (fontname, fontsize) != (self.fontname, self.fontsize):
            self._pswriter.write(f"/{fontname} {fontsize:1.3f} selectfont\n")
            if store:
                self.fontname = fontname
                self.fontsize = fontsize

    def create_hatch(self, hatch, linewidth):
        sidelen = 72
        if hatch in self._hatches:
            return self._hatches[hatch]
        name = 'H%d' % len(self._hatches)
        pageheight = self.height * 72
        self._pswriter.write(f"""\
  << /PatternType 1
     /PaintType 2
     /TilingType 2
     /BBox[0 0 {sidelen:d} {sidelen:d}]
     /XStep {sidelen:d}
     /YStep {sidelen:d}

     /PaintProc {{
        pop
        {linewidth:g} setlinewidth
{self._convert_path(Path.hatch(hatch), Affine2D().scale(sidelen), simplify=False)}
        gsave
        fill
        grestore
        stroke
     }} bind
   >>
   matrix
   0 {pageheight:g} translate
   makepattern
   /{name} exch def
""")
        self._hatches[hatch] = name
        return name

    def get_image_magnification(self):
        """
        Get the factor by which to magnify images passed to draw_image.
        Allows a backend to have images at a different resolution to other
        artists.
        """
        return self.image_magnification

    def _convert_path(self, path, transform, clip=False, simplify=None):
        if clip:
            clip = (0.0, 0.0, self.width * 72.0, self.height * 72.0)
        else:
            clip = None
        return _path.convert_to_string(
            path, transform, clip, simplify, None,
            6, [b"m", b"l", b"", b"c", b"cl"], True).decode("ascii")

    def _get_clip_cmd(self, gc):
        clip = []
        rect = gc.get_clip_rectangle()
        if rect is not None:
            clip.append(f"{_nums_to_str(*rect.p0, *rect.size)} rectclip\n")
        path, trf = gc.get_clip_path()
        if path is not None:
            key = (path, id(trf))
            custom_clip_cmd = self._clip_paths.get(key)
            if custom_clip_cmd is None:
                custom_clip_cmd = "c%d" % len(self._clip_paths)
                self._pswriter.write(f"""\
/{custom_clip_cmd} {{
{self._convert_path(path, trf, simplify=False)}
clip
newpath
}} bind def
""")
                self._clip_paths[key] = custom_clip_cmd
            clip.append(f"{custom_clip_cmd}\n")
        return "".join(clip)

    @_log_if_debug_on
    def draw_image(self, gc, x, y, im, transform=None):
        # docstring inherited

        h, w = im.shape[:2]
        imagecmd = "false 3 colorimage"
        data = im[::-1, :, :3]  # Vertically flipped rgb values.
        hexdata = data.tobytes().hex("\n", -64)  # Linewrap to 128 chars.

        if transform is None:
            matrix = "1 0 0 1 0 0"
            xscale = w / self.image_magnification
            yscale = h / self.image_magnification
        else:
            matrix = " ".join(map(str, transform.frozen().to_values()))
            xscale = 1.0
            yscale = 1.0

        self._pswriter.write(f"""\
gsave
{self._get_clip_cmd(gc)}
{x:g} {y:g} translate
[{matrix}] concat
{xscale:g} {yscale:g} scale
/DataString {w:d} string def
{w:d} {h:d} 8 [ {w:d} 0 0 -{h:d} 0 {h:d} ]
{{
currentfile DataString readhexstring pop
}} bind {imagecmd}
{hexdata}
grestore
""")

    @_log_if_debug_on
    def draw_path(self, gc, path, transform, rgbFace=None):
        # docstring inherited
        clip = rgbFace is None and gc.get_hatch_path() is None
        simplify = path.should_simplify and clip
        ps = self._convert_path(path, transform, clip=clip, simplify=simplify)
        self._draw_ps(ps, gc, rgbFace)

    @_log_if_debug_on
    def draw_markers(
            self, gc, marker_path, marker_trans, path, trans, rgbFace=None):
        # docstring inherited

        ps_color = (
            None
            if self._is_transparent(rgbFace)
            else f'{_nums_to_str(rgbFace[0])} setgray'
            if rgbFace[0] == rgbFace[1] == rgbFace[2]
            else f'{_nums_to_str(*rgbFace[:3])} setrgbcolor')

        # construct the generic marker command:

        # don't want the translate to be global
        ps_cmd = ['/o {', 'gsave', 'newpath', 'translate']

        lw = gc.get_linewidth()
        alpha = (gc.get_alpha()
                 if gc.get_forced_alpha() or len(gc.get_rgb()) == 3
                 else gc.get_rgb()[3])
        stroke = lw > 0 and alpha > 0
        if stroke:
            ps_cmd.append('%.1f setlinewidth' % lw)
            ps_cmd.append(self._linejoin_cmd(gc.get_joinstyle()))
            ps_cmd.append(self._linecap_cmd(gc.get_capstyle()))

        ps_cmd.append(self._convert_path(marker_path, marker_trans,
                                         simplify=False))

        if rgbFace:
            if stroke:
                ps_cmd.append('gsave')
            if ps_color:
                ps_cmd.extend([ps_color, 'fill'])
            if stroke:
                ps_cmd.append('grestore')

        if stroke:
            ps_cmd.append('stroke')
        ps_cmd.extend(['grestore', '} bind def'])

        for vertices, code in path.iter_segments(
                trans,
                clip=(0, 0, self.width*72, self.height*72),
                simplify=False):
            if len(vertices):
                x, y = vertices[-2:]
                ps_cmd.append(f"{x:g} {y:g} o")

        ps = '\n'.join(ps_cmd)
        self._draw_ps(ps, gc, rgbFace, fill=False, stroke=False)

    @_log_if_debug_on
    def draw_path_collection(self, gc, master_transform, paths, all_transforms,
                             offsets, offset_trans, facecolors, edgecolors,
                             linewidths, linestyles, antialiaseds, urls,
                             offset_position):
        # Is the optimization worth it? Rough calculation:
        # cost of emitting a path in-line is
        #     (len_path + 2) * uses_per_path
        # cost of definition+use is
        #     (len_path + 3) + 3 * uses_per_path
        len_path = len(paths[0].vertices) if len(paths) > 0 else 0
        uses_per_path = self._iter_collection_uses_per_path(
            paths, all_transforms, offsets, facecolors, edgecolors)
        should_do_optimization = \
            len_path + 3 * uses_per_path + 3 < (len_path + 2) * uses_per_path
        if not should_do_optimization:
            return RendererBase.draw_path_collection(
                self, gc, master_transform, paths, all_transforms,
                offsets, offset_trans, facecolors, edgecolors,
                linewidths, linestyles, antialiaseds, urls,
                offset_position)

        path_codes = []
        for i, (path, transform) in enumerate(self._iter_collection_raw_paths(
                master_transform, paths, all_transforms)):
            name = 'p%d_%d' % (self._path_collection_id, i)
            path_bytes = self._convert_path(path, transform, simplify=False)
            self._pswriter.write(f"""\
/{name} {{
newpath
translate
{path_bytes}
}} bind def
""")
            path_codes.append(name)

        for xo, yo, path_id, gc0, rgbFace in self._iter_collection(
                gc, path_codes, offsets, offset_trans,
                facecolors, edgecolors, linewidths, linestyles,
                antialiaseds, urls, offset_position):
            ps = f"{xo:g} {yo:g} {path_id}"
            self._draw_ps(ps, gc0, rgbFace)

        self._path_collection_id += 1

    @_log_if_debug_on
    def draw_tex(self, gc, x, y, s, prop, angle, *, mtext=None):
        # docstring inherited
        if self._is_transparent(gc.get_rgb()):
            return  # Special handling for fully transparent.

        if not hasattr(self, "psfrag"):
            self._logwarn_once(
                "The PS backend determines usetex status solely based on "
                "rcParams['text.usetex'] and does not support having "
                "usetex=True only for some elements; this element will thus "
                "be rendered as if usetex=False.")
            self.draw_text(gc, x, y, s, prop, angle, False, mtext)
            return

        w, h, bl = self.get_text_width_height_descent(s, prop, ismath="TeX")
        fontsize = prop.get_size_in_points()
        thetext = 'psmarker%d' % self.textcnt
        color = _nums_to_str(*gc.get_rgb()[:3], sep=',')
        fontcmd = {'sans-serif': r'{\sffamily %s}',
                   'monospace': r'{\ttfamily %s}'}.get(
                       mpl.rcParams['font.family'][0], r'{\rmfamily %s}')
        s = fontcmd % s
        tex = r'\color[rgb]{%s} %s' % (color, s)

        # Stick to bottom-left alignment, so subtract descent from the text-normal
        # direction since text is normally positioned by its baseline.
        rangle = np.radians(angle + 90)
        pos = _nums_to_str(x - bl * np.cos(rangle), y - bl * np.sin(rangle))
        self.psfrag.append(
            r'\psfrag{%s}[bl][bl][1][%f]{\fontsize{%f}{%f}%s}' % (
                thetext, angle, fontsize, fontsize*1.25, tex))

        self._pswriter.write(f"""\
gsave
{pos} moveto
({thetext})
show
grestore
""")
        self.textcnt += 1

    @_log_if_debug_on
    def draw_text(self, gc, x, y, s, prop, angle, ismath=False, mtext=None):
        # docstring inherited

        if self._is_transparent(gc.get_rgb()):
            return  # Special handling for fully transparent.

        if ismath == 'TeX':
            return self.draw_tex(gc, x, y, s, prop, angle)

        if ismath:
            return self.draw_mathtext(gc, x, y, s, prop, angle)

        stream = []  # list of (ps_name, x, char_name)

        if mpl.rcParams['ps.useafm']:
            font = self._get_font_afm(prop)
            ps_name = (font.postscript_name.encode("ascii", "replace")
                        .decode("ascii"))
            scale = 0.001 * prop.get_size_in_points()
            thisx = 0
            last_name = None  # kerns returns 0 for None.
            for c in s:
                name = uni2type1.get(ord(c), f"uni{ord(c):04X}")
                try:
                    width = font.get_width_from_char_name(name)
                except KeyError:
                    name = 'question'
                    width = font.get_width_char('?')
                kern = font.get_kern_dist_from_name(last_name, name)
                last_name = name
                thisx += kern * scale
                stream.append((ps_name, thisx, name))
                thisx += width * scale

        else:
            font = self._get_font_ttf(prop)
            self._character_tracker.track(font, s)
            for item in _text_helpers.layout(s, font):
                ps_name = (item.ft_object.postscript_name
                           .encode("ascii", "replace").decode("ascii"))
                glyph_name = item.ft_object.get_glyph_name(item.glyph_idx)
                stream.append((ps_name, item.x, glyph_name))
        self.set_color(*gc.get_rgb())

        for ps_name, group in itertools. \
                groupby(stream, lambda entry: entry[0]):
            self.set_font(ps_name, prop.get_size_in_points(), False)
            thetext = "\n".join(f"{x:g} 0 m /{name:s} glyphshow"
                                for _, x, name in group)
            self._pswriter.write(f"""\
gsave
{self._get_clip_cmd(gc)}
{x:g} {y:g} translate
{angle:g} rotate
{thetext}
grestore
""")

    @_log_if_debug_on
    def draw_mathtext(self, gc, x, y, s, prop, angle):
        """Draw the math text using matplotlib.mathtext."""
        width, height, descent, glyphs, rects = \
            self._text2path.mathtext_parser.parse(s, 72, prop)
        self.set_color(*gc.get_rgb())
        self._pswriter.write(
            f"gsave\n"
            f"{x:g} {y:g} translate\n"
            f"{angle:g} rotate\n")
        lastfont = None
        for font, fontsize, num, ox, oy in glyphs:
            self._character_tracker.track_glyph(font, num)
            if (font.postscript_name, fontsize) != lastfont:
                lastfont = font.postscript_name, fontsize
                self._pswriter.write(
                    f"/{font.postscript_name} {fontsize} selectfont\n")
            glyph_name = (
                font.get_name_char(chr(num)) if isinstance(font, AFM) else
                font.get_glyph_name(font.get_char_index(num)))
            self._pswriter.write(
                f"{ox:g} {oy:g} moveto\n"
                f"/{glyph_name} glyphshow\n")
        for ox, oy, w, h in rects:
            self._pswriter.write(f"{ox} {oy} {w} {h} rectfill\n")
        self._pswriter.write("grestore\n")

    @_log_if_debug_on
    def draw_gouraud_triangles(self, gc, points, colors, trans):
        assert len(points) == len(colors)
        if len(points) == 0:
            return
        assert points.ndim == 3
        assert points.shape[1] == 3
        assert points.shape[2] == 2
        assert colors.ndim == 3
        assert colors.shape[1] == 3
        assert colors.shape[2] == 4

        shape = points.shape
        flat_points = points.reshape((shape[0] * shape[1], 2))
        flat_points = trans.transform(flat_points)
        flat_colors = colors.reshape((shape[0] * shape[1], 4))
        points_min = np.min(flat_points, axis=0) - (1 << 12)
        points_max = np.max(flat_points, axis=0) + (1 << 12)
        factor = np.ceil((2 ** 32 - 1) / (points_max - points_min))

        xmin, ymin = points_min
        xmax, ymax = points_max

        data = np.empty(
            shape[0] * shape[1],
            dtype=[('flags', 'u1'), ('points', '2>u4'), ('colors', '3u1')])
        data['flags'] = 0
        data['points'] = (flat_points - points_min) * factor
        data['colors'] = flat_colors[:, :3] * 255.0
        hexdata = data.tobytes().hex("\n", -64)  # Linewrap to 128 chars.

        self._pswriter.write(f"""\
gsave
<< /ShadingType 4
   /ColorSpace [/DeviceRGB]
   /BitsPerCoordinate 32
   /BitsPerComponent 8
   /BitsPerFlag 8
   /AntiAlias true
   /Decode [ {xmin:g} {xmax:g} {ymin:g} {ymax:g} 0 1 0 1 0 1 ]
   /DataSource <
{hexdata}
>
>>
shfill
grestore
""")

    def _draw_ps(self, ps, gc, rgbFace, *, fill=True, stroke=True):
        """
        Emit the PostScript snippet *ps* with all the attributes from *gc*
        applied.  *ps* must consist of PostScript commands to construct a path.

        The *fill* and/or *stroke* kwargs can be set to False if the *ps*
        string already includes filling and/or stroking, in which case
        `_draw_ps` is just supplying properties and clipping.
        """
        write = self._pswriter.write
        mightstroke = (gc.get_linewidth() > 0
                       and not self._is_transparent(gc.get_rgb()))
        if not mightstroke:
            stroke = False
        if self._is_transparent(rgbFace):
            fill = False
        hatch = gc.get_hatch()

        if mightstroke:
            self.set_linewidth(gc.get_linewidth())
            self.set_linejoin(gc.get_joinstyle())
            self.set_linecap(gc.get_capstyle())
            self.set_linedash(*gc.get_dashes())
        if mightstroke or hatch:
            self.set_color(*gc.get_rgb()[:3])
        write('gsave\n')

        write(self._get_clip_cmd(gc))

        write(ps.strip())
        write("\n")

        if fill:
            if stroke or hatch:
                write("gsave\n")
            self.set_color(*rgbFace[:3], store=False)
            write("fill\n")
            if stroke or hatch:
                write("grestore\n")

        if hatch:
            hatch_name = self.create_hatch(hatch, gc.get_hatch_linewidth())
            write("gsave\n")
            write(_nums_to_str(*gc.get_hatch_color()[:3]))
            write(f" {hatch_name} setpattern fill grestore\n")

        if stroke:
            write("stroke\n")

        write("grestore\n")


class _Orientation(Enum):
    portrait, landscape = range(2)

    def swap_if_landscape(self, shape):
        return shape[::-1] if self.name == "landscape" else shape


class FigureCanvasPS(FigureCanvasBase):
    fixed_dpi = 72
    filetypes = {'ps': 'Postscript',
                 'eps': 'Encapsulated Postscript'}

    def get_default_filetype(self):
        return 'ps'

    def _print_ps(
            self, fmt, outfile, *,
            metadata=None, papertype=None, orientation='portrait',
            bbox_inches_restore=None, **kwargs):

        dpi = self.figure.dpi
        self.figure.dpi = 72  # Override the dpi kwarg

        dsc_comments = {}
        if isinstance(outfile, (str, os.PathLike)):
            filename = pathlib.Path(outfile).name
            dsc_comments["Title"] = \
                filename.encode("ascii", "replace").decode("ascii")
        dsc_comments["Creator"] = (metadata or {}).get(
            "Creator",
            f"Matplotlib v{mpl.__version__}, https://matplotlib.org/")
        # See https://reproducible-builds.org/specs/source-date-epoch/
        source_date_epoch = os.getenv("SOURCE_DATE_EPOCH")
        dsc_comments["CreationDate"] = (
            datetime.datetime.fromtimestamp(
                int(source_date_epoch),
                datetime.timezone.utc).strftime("%a %b %d %H:%M:%S %Y")
            if source_date_epoch
            else time.ctime())
        dsc_comments = "\n".join(
            f"%%{k}: {v}" for k, v in dsc_comments.items())

        if papertype is None:
            papertype = mpl.rcParams['ps.papersize']
        papertype = papertype.lower()
        _api.check_in_list(['figure', *papersize], papertype=papertype)

        orientation = _api.check_getitem(
            _Orientation, orientation=orientation.lower())

        printer = (self._print_figure_tex
                   if mpl.rcParams['text.usetex'] else
                   self._print_figure)
        printer(fmt, outfile, dpi=dpi, dsc_comments=dsc_comments,
                orientation=orientation, papertype=papertype,
                bbox_inches_restore=bbox_inches_restore, **kwargs)

    def _print_figure(
            self, fmt, outfile, *,
            dpi, dsc_comments, orientation, papertype,
            bbox_inches_restore=None):
        """
        Render the figure to a filesystem path or a file-like object.

        Parameters are as for `.print_figure`, except that *dsc_comments* is a
        string containing Document Structuring Convention comments,
        generated from the *metadata* parameter to `.print_figure`.
        """
        is_eps = fmt == 'eps'
        if not (isinstance(outfile, (str, os.PathLike))
                or is_writable_file_like(outfile)):
            raise ValueError("outfile must be a path or a file-like object")

        # find the appropriate papertype
        width, height = self.figure.get_size_inches()
        if is_eps or papertype == 'figure':
            paper_width, paper_height = width, height
        else:
            paper_width, paper_height = orientation.swap_if_landscape(
                papersize[papertype])

        # center the figure on the paper
        xo = 72 * 0.5 * (paper_width - width)
        yo = 72 * 0.5 * (paper_height - height)

        llx = xo
        lly = yo
        urx = llx + self.figure.bbox.width
        ury = lly + self.figure.bbox.height
        rotation = 0
        if orientation is _Orientation.landscape:
            llx, lly, urx, ury = lly, llx, ury, urx
            xo, yo = 72 * paper_height - yo, xo
            rotation = 90
        bbox = (llx, lly, urx, ury)

        self._pswriter = StringIO()

        # mixed mode rendering
        ps_renderer = RendererPS(width, height, self._pswriter, imagedpi=dpi)
        renderer = MixedModeRenderer(
            self.figure, width, height, dpi, ps_renderer,
            bbox_inches_restore=bbox_inches_restore)

        self.figure.draw(renderer)

        def print_figure_impl(fh):
            # write the PostScript headers
            if is_eps:
                print("%!PS-Adobe-3.0 EPSF-3.0", file=fh)
            else:
                print("%!PS-Adobe-3.0", file=fh)
                if papertype != 'figure':
                    print(f"%%DocumentPaperSizes: {papertype}", file=fh)
                print("%%Pages: 1", file=fh)
            print(f"%%LanguageLevel: 3\n"
                  f"{dsc_comments}\n"
                  f"%%Orientation: {orientation.name}\n"
                  f"{_get_bbox_header(bbox)}\n"
                  f"%%EndComments\n",
                  end="", file=fh)

            Ndict = len(_psDefs)
            print("%%BeginProlog", file=fh)
            if not mpl.rcParams['ps.useafm']:
                Ndict += len(ps_renderer._character_tracker.used)
            print("/mpldict %d dict def" % Ndict, file=fh)
            print("mpldict begin", file=fh)
            print("\n".join(_psDefs), file=fh)
            if not mpl.rcParams['ps.useafm']:
                for font_path, chars \
                        in ps_renderer._character_tracker.used.items():
                    if not chars:
                        continue
                    fonttype = mpl.rcParams['ps.fonttype']
                    # Can't use more than 255 chars from a single Type 3 font.
                    if len(chars) > 255:
                        fonttype = 42
                    fh.flush()
                    if fonttype == 3:
                        fh.write(_font_to_ps_type3(font_path, chars))
                    else:  # Type 42 only.
                        _font_to_ps_type42(font_path, chars, fh)
            print("end", file=fh)
            print("%%EndProlog", file=fh)

            if not is_eps:
                print("%%Page: 1 1", file=fh)
            print("mpldict begin", file=fh)

            print("%s translate" % _nums_to_str(xo, yo), file=fh)
            if rotation:
                print("%d rotate" % rotation, file=fh)
            print(f"0 0 {_nums_to_str(width*72, height*72)} rectclip", file=fh)

            # write the figure
            print(self._pswriter.getvalue(), file=fh)

            # write the trailer
            print("end", file=fh)
            print("showpage", file=fh)
            if not is_eps:
                print("%%EOF", file=fh)
            fh.flush()

        if mpl.rcParams['ps.usedistiller']:
            # We are going to use an external program to process the output.
            # Write to a temporary file.
            with TemporaryDirectory() as tmpdir:
                tmpfile = os.path.join(tmpdir, "tmp.ps")
                with open(tmpfile, 'w', encoding='latin-1') as fh:
                    print_figure_impl(fh)
                if mpl.rcParams['ps.usedistiller'] == 'ghostscript':
                    _try_distill(gs_distill,
                                 tmpfile, is_eps, ptype=papertype, bbox=bbox)
                elif mpl.rcParams['ps.usedistiller'] == 'xpdf':
                    _try_distill(xpdf_distill,
                                 tmpfile, is_eps, ptype=papertype, bbox=bbox)
                _move_path_to_path_or_stream(tmpfile, outfile)

        else:  # Write directly to outfile.
            with cbook.open_file_cm(outfile, "w", encoding="latin-1") as file:
                if not file_requires_unicode(file):
                    file = codecs.getwriter("latin-1")(file)
                print_figure_impl(file)

    def _print_figure_tex(
            self, fmt, outfile, *,
            dpi, dsc_comments, orientation, papertype,
            bbox_inches_restore=None):
        """
        If :rc:`text.usetex` is True, a temporary pair of tex/eps files
        are created to allow tex to manage the text layout via the PSFrags
        package. These files are processed to yield the final ps or eps file.

        The rest of the behavior is as for `._print_figure`.
        """
        is_eps = fmt == 'eps'

        width, height = self.figure.get_size_inches()
        xo = 0
        yo = 0

        llx = xo
        lly = yo
        urx = llx + self.figure.bbox.width
        ury = lly + self.figure.bbox.height
        bbox = (llx, lly, urx, ury)

        self._pswriter = StringIO()

        # mixed mode rendering
        ps_renderer = RendererPS(width, height, self._pswriter, imagedpi=dpi)
        renderer = MixedModeRenderer(self.figure,
                                     width, height, dpi, ps_renderer,
                                     bbox_inches_restore=bbox_inches_restore)

        self.figure.draw(renderer)

        # write to a temp file, we'll move it to outfile when done
        with TemporaryDirectory() as tmpdir:
            tmppath = pathlib.Path(tmpdir, "tmp.ps")
            tmppath.write_text(
                f"""\
%!PS-Adobe-3.0 EPSF-3.0
%%LanguageLevel: 3
{dsc_comments}
{_get_bbox_header(bbox)}
%%EndComments
%%BeginProlog
/mpldict {len(_psDefs)} dict def
mpldict begin
{"".join(_psDefs)}
end
%%EndProlog
mpldict begin
{_nums_to_str(xo, yo)} translate
0 0 {_nums_to_str(width*72, height*72)} rectclip
{self._pswriter.getvalue()}
end
showpage
""",
                encoding="latin-1")

            if orientation is _Orientation.landscape:  # now, ready to rotate
                width, height = height, width
                bbox = (lly, llx, ury, urx)

            # set the paper size to the figure size if is_eps. The
            # resulting ps file has the given size with correct bounding
            # box so that there is no need to call 'pstoeps'
            if is_eps or papertype == 'figure':
                paper_width, paper_height = orientation.swap_if_landscape(
                    self.figure.get_size_inches())
            else:
                paper_width, paper_height = papersize[papertype]

            psfrag_rotated = _convert_psfrags(
                tmppath, ps_renderer.psfrag, paper_width, paper_height,
                orientation.name)

            if (mpl.rcParams['ps.usedistiller'] == 'ghostscript'
                    or mpl.rcParams['text.usetex']):
                _try_distill(gs_distill,
                             tmppath, is_eps, ptype=papertype, bbox=bbox,
                             rotated=psfrag_rotated)
            elif mpl.rcParams['ps.usedistiller'] == 'xpdf':
                _try_distill(xpdf_distill,
                             tmppath, is_eps, ptype=papertype, bbox=bbox,
                             rotated=psfrag_rotated)

            _move_path_to_path_or_stream(tmppath, outfile)

    print_ps = functools.partialmethod(_print_ps, "ps")
    print_eps = functools.partialmethod(_print_ps, "eps")

    def draw(self):
        self.figure.draw_without_rendering()
        return super().draw()


def _convert_psfrags(tmppath, psfrags, paper_width, paper_height, orientation):
    """
    When we want to use the LaTeX backend with postscript, we write PSFrag tags
    to a temporary postscript file, each one marking a position for LaTeX to
    render some text. convert_psfrags generates a LaTeX document containing the
    commands to convert those tags to text. LaTeX/dvips produces the postscript
    file that includes the actual text.
    """
    with mpl.rc_context({
            "text.latex.preamble":
            mpl.rcParams["text.latex.preamble"] +
            mpl.texmanager._usepackage_if_not_loaded("color") +
            mpl.texmanager._usepackage_if_not_loaded("graphicx") +
            mpl.texmanager._usepackage_if_not_loaded("psfrag") +
            r"\geometry{papersize={%(width)sin,%(height)sin},margin=0in}"
            % {"width": paper_width, "height": paper_height}
    }):
        dvifile = TexManager().make_dvi(
            "\n"
            r"\begin{figure}""\n"
            r"  \centering\leavevmode""\n"
            r"  %(psfrags)s""\n"
            r"  \includegraphics*[angle=%(angle)s]{%(epsfile)s}""\n"
            r"\end{figure}"
            % {
                "psfrags": "\n".join(psfrags),
                "angle": 90 if orientation == 'landscape' else 0,
                "epsfile": tmppath.resolve().as_posix(),
            },
            fontsize=10)  # tex's default fontsize.

    with TemporaryDirectory() as tmpdir:
        psfile = os.path.join(tmpdir, "tmp.ps")
        cbook._check_and_log_subprocess(
            ['dvips', '-q', '-R0', '-o', psfile, dvifile], _log)
        shutil.move(psfile, tmppath)

    # check if the dvips created a ps in landscape paper.  Somehow,
    # above latex+dvips results in a ps file in a landscape mode for a
    # certain figure sizes (e.g., 8.3in, 5.8in which is a5). And the
    # bounding box of the final output got messed up. We check see if
    # the generated ps file is in landscape and return this
    # information. The return value is used in pstoeps step to recover
    # the correct bounding box. 2010-06-05 JJL
    with open(tmppath) as fh:
        psfrag_rotated = "Landscape" in fh.read(1000)
    return psfrag_rotated


def _try_distill(func, tmppath, *args, **kwargs):
    try:
        func(str(tmppath), *args, **kwargs)
    except mpl.ExecutableNotFoundError as exc:
        _log.warning("%s.  Distillation step skipped.", exc)


def gs_distill(tmpfile, eps=False, ptype='letter', bbox=None, rotated=False):
    """
    Use ghostscript's pswrite or epswrite device to distill a file.
    This yields smaller files without illegal encapsulated postscript
    operators. The output is low-level, converting text to outlines.
    """

    if eps:
        paper_option = ["-dEPSCrop"]
    elif ptype == "figure":
        # The bbox will have its lower-left corner at (0, 0), so upper-right
        # corner corresponds with paper size.
        paper_option = [f"-dDEVICEWIDTHPOINTS={bbox[2]}",
                        f"-dDEVICEHEIGHTPOINTS={bbox[3]}"]
    else:
        paper_option = [f"-sPAPERSIZE={ptype}"]

    psfile = tmpfile + '.ps'
    dpi = mpl.rcParams['ps.distiller.res']

    cbook._check_and_log_subprocess(
        [mpl._get_executable_info("gs").executable,
         "-dBATCH", "-dNOPAUSE", "-r%d" % dpi, "-sDEVICE=ps2write",
         *paper_option, f"-sOutputFile={psfile}", tmpfile],
        _log)

    os.remove(tmpfile)
    shutil.move(psfile, tmpfile)

    # While it is best if above steps preserve the original bounding
    # box, there seem to be cases when it is not. For those cases,
    # the original bbox can be restored during the pstoeps step.

    if eps:
        # For some versions of gs, above steps result in a ps file where the
        # original bbox is no more correct. Do not adjust bbox for now.
        pstoeps(tmpfile, bbox, rotated=rotated)


def xpdf_distill(tmpfile, eps=False, ptype='letter', bbox=None, rotated=False):
    """
    Use ghostscript's ps2pdf and xpdf's/poppler's pdftops to distill a file.
    This yields smaller files without illegal encapsulated postscript
    operators. This distiller is preferred, generating high-level postscript
    output that treats text as text.
    """
    mpl._get_executable_info("gs")  # Effectively checks for ps2pdf.
    mpl._get_executable_info("pdftops")

    if eps:
        paper_option = ["-dEPSCrop"]
    elif ptype == "figure":
        # The bbox will have its lower-left corner at (0, 0), so upper-right
        # corner corresponds with paper size.
        paper_option = [f"-dDEVICEWIDTHPOINTS#{bbox[2]}",
                        f"-dDEVICEHEIGHTPOINTS#{bbox[3]}"]
    else:
        paper_option = [f"-sPAPERSIZE#{ptype}"]

    with TemporaryDirectory() as tmpdir:
        tmppdf = pathlib.Path(tmpdir, "tmp.pdf")
        tmpps = pathlib.Path(tmpdir, "tmp.ps")
        # Pass options as `-foo#bar` instead of `-foo=bar` to keep Windows
        # happy (https://ghostscript.com/doc/9.56.1/Use.htm#MS_Windows).
        cbook._check_and_log_subprocess(
            ["ps2pdf",
             "-dAutoFilterColorImages#false",
             "-dAutoFilterGrayImages#false",
             "-sAutoRotatePages#None",
             "-sGrayImageFilter#FlateEncode",
             "-sColorImageFilter#FlateEncode",
             *paper_option,
             tmpfile, tmppdf], _log)
        cbook._check_and_log_subprocess(
            ["pdftops", "-paper", "match", "-level3", tmppdf, tmpps], _log)
        shutil.move(tmpps, tmpfile)
    if eps:
        pstoeps(tmpfile)


@_api.deprecated("3.9")
def get_bbox_header(lbrt, rotated=False):
    """
    Return a postscript header string for the given bbox lbrt=(l, b, r, t).
    Optionally, return rotate command.
    """
    return _get_bbox_header(lbrt), (_get_rotate_command(lbrt) if rotated else "")


def _get_bbox_header(lbrt):
    """Return a PostScript header string for bounding box *lbrt*=(l, b, r, t)."""
    l, b, r, t = lbrt
    return (f"%%BoundingBox: {int(l)} {int(b)} {math.ceil(r)} {math.ceil(t)}\n"
            f"%%HiResBoundingBox: {l:.6f} {b:.6f} {r:.6f} {t:.6f}")


def _get_rotate_command(lbrt):
    """Return a PostScript 90° rotation command for bounding box *lbrt*=(l, b, r, t)."""
    l, b, r, t = lbrt
    return f"{l+r:.2f} {0:.2f} translate\n90 rotate"


def pstoeps(tmpfile, bbox=None, rotated=False):
    """
    Convert the postscript to encapsulated postscript.  The bbox of
    the eps file will be replaced with the given *bbox* argument. If
    None, original bbox will be used.
    """

    epsfile = tmpfile + '.eps'
    with open(epsfile, 'wb') as epsh, open(tmpfile, 'rb') as tmph:
        write = epsh.write
        # Modify the header:
        for line in tmph:
            if line.startswith(b'%!PS'):
                write(b"%!PS-Adobe-3.0 EPSF-3.0\n")
                if bbox:
                    write(_get_bbox_header(bbox).encode('ascii') + b'\n')
            elif line.startswith(b'%%EndComments'):
                write(line)
                write(b'%%BeginProlog\n'
                      b'save\n'
                      b'countdictstack\n'
                      b'mark\n'
                      b'newpath\n'
                      b'/showpage {} def\n'
                      b'/setpagedevice {pop} def\n'
                      b'%%EndProlog\n'
                      b'%%Page 1 1\n')
                if rotated:  # The output eps file need to be rotated.
                    write(_get_rotate_command(bbox).encode('ascii') + b'\n')
                break
            elif bbox and line.startswith((b'%%Bound', b'%%HiResBound',
                                           b'%%DocumentMedia', b'%%Pages')):
                pass
            else:
                write(line)
        # Now rewrite the rest of the file, and modify the trailer.
        # This is done in a second loop such that the header of the embedded
        # eps file is not modified.
        for line in tmph:
            if line.startswith(b'%%EOF'):
                write(b'cleartomark\n'
                      b'countdictstack\n'
                      b'exch sub { end } repeat\n'
                      b'restore\n'
                      b'showpage\n'
                      b'%%EOF\n')
            elif line.startswith(b'%%PageBoundingBox'):
                pass
            else:
                write(line)

    os.remove(tmpfile)
    shutil.move(epsfile, tmpfile)


FigureManagerPS = FigureManagerBase


# The following Python dictionary psDefs contains the entries for the
# PostScript dictionary mpldict.  This dictionary implements most of
# the matplotlib primitives and some abbreviations.
#
# References:
# https://www.adobe.com/content/dam/acom/en/devnet/actionscript/articles/PLRM.pdf
# http://preserve.mactech.com/articles/mactech/Vol.09/09.04/PostscriptTutorial
# http://www.math.ubc.ca/people/faculty/cass/graphics/text/www/
#

# The usage comments use the notation of the operator summary
# in the PostScript Language reference manual.
_psDefs = [
    # name proc  *_d*  -
    # Note that this cannot be bound to /d, because when embedding a Type3 font
    # we may want to define a "d" glyph using "/d{...} d" which would locally
    # overwrite the definition.
    "/_d { bind def } bind def",
    # x y  *m*  -
    "/m { moveto } _d",
    # x y  *l*  -
    "/l { lineto } _d",
    # x y  *r*  -
    "/r { rlineto } _d",
    # x1 y1 x2 y2 x y *c*  -
    "/c { curveto } _d",
    # *cl*  -
    "/cl { closepath } _d",
    # *ce*  -
    "/ce { closepath eofill } _d",
    # wx wy llx lly urx ury  *setcachedevice*  -
    "/sc { setcachedevice } _d",
]


@_Backend.export
class _BackendPS(_Backend):
    backend_version = 'Level II'
    FigureCanvas = FigureCanvasPS
