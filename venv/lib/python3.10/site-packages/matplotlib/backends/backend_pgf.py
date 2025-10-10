import codecs
import datetime
import functools
from io import BytesIO
import logging
import math
import os
import pathlib
import shutil
import subprocess
from tempfile import TemporaryDirectory
import weakref

from PIL import Image

import matplotlib as mpl
from matplotlib import cbook, font_manager as fm
from matplotlib.backend_bases import (
    _Backend, FigureCanvasBase, FigureManagerBase, RendererBase
)
from matplotlib.backends.backend_mixed import MixedModeRenderer
from matplotlib.backends.backend_pdf import (
    _create_pdf_info_dict, _datetime_to_pdf)
from matplotlib.path import Path
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib._pylab_helpers import Gcf

_log = logging.getLogger(__name__)


_DOCUMENTCLASS = r"\documentclass{article}"


# Note: When formatting floating point values, it is important to use the
# %f/{:f} format rather than %s/{} to avoid triggering scientific notation,
# which is not recognized by TeX.

def _get_preamble():
    """Prepare a LaTeX preamble based on the rcParams configuration."""
    font_size_pt = FontProperties(
        size=mpl.rcParams["font.size"]
    ).get_size_in_points()
    return "\n".join([
        # Remove Matplotlib's custom command \mathdefault.  (Not using
        # \mathnormal instead since this looks odd with Computer Modern.)
        r"\def\mathdefault#1{#1}",
        # Use displaystyle for all math.
        r"\everymath=\expandafter{\the\everymath\displaystyle}",
        # Set up font sizes to match font.size setting.
        # If present, use the KOMA package scrextend to adjust the standard
        # LaTeX font commands (\tiny, ..., \normalsize, ..., \Huge) accordingly.
        # Otherwise, only set \normalsize, manually.
        r"\IfFileExists{scrextend.sty}{",
        r"  \usepackage[fontsize=%fpt]{scrextend}" % font_size_pt,
        r"}{",
        r"  \renewcommand{\normalsize}{\fontsize{%f}{%f}\selectfont}"
        % (font_size_pt, 1.2 * font_size_pt),
        r"  \normalsize",
        r"}",
        # Allow pgf.preamble to override the above definitions.
        mpl.rcParams["pgf.preamble"],
        *([
            r"\ifdefined\pdftexversion\else  % non-pdftex case.",
            r"  \usepackage{fontspec}",
        ] + [
            r"  \%s{%s}[Path=\detokenize{%s/}]"
            % (command, path.name, path.parent.as_posix())
            for command, path in zip(
                ["setmainfont", "setsansfont", "setmonofont"],
                [pathlib.Path(fm.findfont(family))
                 for family in ["serif", "sans\\-serif", "monospace"]]
            )
        ] + [r"\fi"] if mpl.rcParams["pgf.rcfonts"] else []),
        # Documented as "must come last".
        mpl.texmanager._usepackage_if_not_loaded("underscore", option="strings"),
    ])


# It's better to use only one unit for all coordinates, since the
# arithmetic in latex seems to produce inaccurate conversions.
latex_pt_to_in = 1. / 72.27
latex_in_to_pt = 1. / latex_pt_to_in
mpl_pt_to_in = 1. / 72.
mpl_in_to_pt = 1. / mpl_pt_to_in


def _tex_escape(text):
    r"""
    Do some necessary and/or useful substitutions for texts to be included in
    LaTeX documents.
    """
    return text.replace("\N{MINUS SIGN}", r"\ensuremath{-}")


def _writeln(fh, line):
    # Ending lines with a % prevents TeX from inserting spurious spaces
    # (https://tex.stackexchange.com/questions/7453).
    fh.write(line)
    fh.write("%\n")


def _escape_and_apply_props(s, prop):
    """
    Generate a TeX string that renders string *s* with font properties *prop*,
    also applying any required escapes to *s*.
    """
    commands = []

    families = {"serif": r"\rmfamily", "sans": r"\sffamily",
                "sans-serif": r"\sffamily", "monospace": r"\ttfamily"}
    family = prop.get_family()[0]
    if family in families:
        commands.append(families[family])
    elif not mpl.rcParams["pgf.rcfonts"]:
        commands.append(r"\fontfamily{\familydefault}")
    elif any(font.name == family for font in fm.fontManager.ttflist):
        commands.append(
            r"\ifdefined\pdftexversion\else\setmainfont{%s}\rmfamily\fi" % family)
    else:
        _log.warning("Ignoring unknown font: %s", family)

    size = prop.get_size_in_points()
    commands.append(r"\fontsize{%f}{%f}" % (size, size * 1.2))

    styles = {"normal": r"", "italic": r"\itshape", "oblique": r"\slshape"}
    commands.append(styles[prop.get_style()])

    boldstyles = ["semibold", "demibold", "demi", "bold", "heavy",
                  "extra bold", "black"]
    if prop.get_weight() in boldstyles:
        commands.append(r"\bfseries")

    commands.append(r"\selectfont")
    return (
        "{"
        + "".join(commands)
        + r"\catcode`\^=\active\def^{\ifmmode\sp\else\^{}\fi}"
        # It should normally be enough to set the catcode of % to 12 ("normal
        # character"); this works on TeXLive 2021 but not on 2018, so we just
        # make it active too.
        + r"\catcode`\%=\active\def%{\%}"
        + _tex_escape(s)
        + "}"
    )


def _metadata_to_str(key, value):
    """Convert metadata key/value to a form that hyperref accepts."""
    if isinstance(value, datetime.datetime):
        value = _datetime_to_pdf(value)
    elif key == 'Trapped':
        value = value.name.decode('ascii')
    else:
        value = str(value)
    return f'{key}={{{value}}}'


def make_pdf_to_png_converter():
    """Return a function that converts a pdf file to a png file."""
    try:
        mpl._get_executable_info("pdftocairo")
    except mpl.ExecutableNotFoundError:
        pass
    else:
        return lambda pdffile, pngfile, dpi: subprocess.check_output(
            ["pdftocairo", "-singlefile", "-transp", "-png", "-r", "%d" % dpi,
             pdffile, os.path.splitext(pngfile)[0]],
            stderr=subprocess.STDOUT)
    try:
        gs_info = mpl._get_executable_info("gs")
    except mpl.ExecutableNotFoundError:
        pass
    else:
        return lambda pdffile, pngfile, dpi: subprocess.check_output(
            [gs_info.executable,
             '-dQUIET', '-dSAFER', '-dBATCH', '-dNOPAUSE', '-dNOPROMPT',
             '-dUseCIEColor', '-dTextAlphaBits=4',
             '-dGraphicsAlphaBits=4', '-dDOINTERPOLATE',
             '-sDEVICE=pngalpha', '-sOutputFile=%s' % pngfile,
             '-r%d' % dpi, pdffile],
            stderr=subprocess.STDOUT)
    raise RuntimeError("No suitable pdf to png renderer found.")


class LatexError(Exception):
    def __init__(self, message, latex_output=""):
        super().__init__(message)
        self.latex_output = latex_output

    def __str__(self):
        s, = self.args
        if self.latex_output:
            s += "\n" + self.latex_output
        return s


class LatexManager:
    """
    The LatexManager opens an instance of the LaTeX application for
    determining the metrics of text elements. The LaTeX environment can be
    modified by setting fonts and/or a custom preamble in `.rcParams`.
    """

    @staticmethod
    def _build_latex_header():
        latex_header = [
            _DOCUMENTCLASS,
            # Include TeX program name as a comment for cache invalidation.
            # TeX does not allow this to be the first line.
            rf"% !TeX program = {mpl.rcParams['pgf.texsystem']}",
            # Test whether \includegraphics supports interpolate option.
            r"\usepackage{graphicx}",
            _get_preamble(),
            r"\begin{document}",
            r"\typeout{pgf_backend_query_start}",
        ]
        return "\n".join(latex_header)

    @classmethod
    def _get_cached_or_new(cls):
        """
        Return the previous LatexManager if the header and tex system did not
        change, or a new instance otherwise.
        """
        return cls._get_cached_or_new_impl(cls._build_latex_header())

    @classmethod
    @functools.lru_cache(1)
    def _get_cached_or_new_impl(cls, header):  # Helper for _get_cached_or_new.
        return cls()

    def _stdin_writeln(self, s):
        if self.latex is None:
            self._setup_latex_process()
        self.latex.stdin.write(s)
        self.latex.stdin.write("\n")
        self.latex.stdin.flush()

    def _expect(self, s):
        s = list(s)
        chars = []
        while True:
            c = self.latex.stdout.read(1)
            chars.append(c)
            if chars[-len(s):] == s:
                break
            if not c:
                self.latex.kill()
                self.latex = None
                raise LatexError("LaTeX process halted", "".join(chars))
        return "".join(chars)

    def _expect_prompt(self):
        return self._expect("\n*")

    def __init__(self):
        # create a tmp directory for running latex, register it for deletion
        self._tmpdir = TemporaryDirectory()
        self.tmpdir = self._tmpdir.name
        self._finalize_tmpdir = weakref.finalize(self, self._tmpdir.cleanup)

        # test the LaTeX setup to ensure a clean startup of the subprocess
        self._setup_latex_process(expect_reply=False)
        stdout, stderr = self.latex.communicate("\n\\makeatletter\\@@end\n")
        if self.latex.returncode != 0:
            raise LatexError(
                f"LaTeX errored (probably missing font or error in preamble) "
                f"while processing the following input:\n"
                f"{self._build_latex_header()}",
                stdout)
        self.latex = None  # Will be set up on first use.
        # Per-instance cache.
        self._get_box_metrics = functools.lru_cache(self._get_box_metrics)

    def _setup_latex_process(self, *, expect_reply=True):
        # Open LaTeX process for real work; register it for deletion.  On
        # Windows, we must ensure that the subprocess has quit before being
        # able to delete the tmpdir in which it runs; in order to do so, we
        # must first `kill()` it, and then `communicate()` with or `wait()` on
        # it.
        try:
            self.latex = subprocess.Popen(
                [mpl.rcParams["pgf.texsystem"], "-halt-on-error"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                encoding="utf-8", cwd=self.tmpdir)
        except FileNotFoundError as err:
            raise RuntimeError(
                f"{mpl.rcParams['pgf.texsystem']!r} not found; install it or change "
                f"rcParams['pgf.texsystem'] to an available TeX implementation"
            ) from err
        except OSError as err:
            raise RuntimeError(
                f"Error starting {mpl.rcParams['pgf.texsystem']!r}") from err

        def finalize_latex(latex):
            latex.kill()
            try:
                latex.communicate()
            except RuntimeError:
                latex.wait()

        self._finalize_latex = weakref.finalize(
            self, finalize_latex, self.latex)
        # write header with 'pgf_backend_query_start' token
        self._stdin_writeln(self._build_latex_header())
        if expect_reply:  # read until 'pgf_backend_query_start' token appears
            self._expect("*pgf_backend_query_start")
            self._expect_prompt()

    def get_width_height_descent(self, text, prop):
        """
        Get the width, total height, and descent (in TeX points) for a text
        typeset by the current LaTeX environment.
        """
        return self._get_box_metrics(_escape_and_apply_props(text, prop))

    def _get_box_metrics(self, tex):
        """
        Get the width, total height and descent (in TeX points) for a TeX
        command's output in the current LaTeX environment.
        """
        # This method gets wrapped in __init__ for per-instance caching.
        self._stdin_writeln(  # Send textbox to TeX & request metrics typeout.
            # \sbox doesn't handle catcode assignments inside its argument,
            # so repeat the assignment of the catcode of "^" and "%" outside.
            r"{\catcode`\^=\active\catcode`\%%=\active\sbox0{%s}"
            r"\typeout{\the\wd0,\the\ht0,\the\dp0}}"
            % tex)
        try:
            answer = self._expect_prompt()
        except LatexError as err:
            # Here and below, use '{}' instead of {!r} to avoid doubling all
            # backslashes.
            raise ValueError("Error measuring {}\nLaTeX Output:\n{}"
                             .format(tex, err.latex_output)) from err
        try:
            # Parse metrics from the answer string.  Last line is prompt, and
            # next-to-last-line is blank line from \typeout.
            width, height, offset = answer.splitlines()[-3].split(",")
        except Exception as err:
            raise ValueError("Error measuring {}\nLaTeX Output:\n{}"
                             .format(tex, answer)) from err
        w, h, o = float(width[:-2]), float(height[:-2]), float(offset[:-2])
        # The height returned from LaTeX goes from base to top;
        # the height Matplotlib expects goes from bottom to top.
        return w, h + o, o


@functools.lru_cache(1)
def _get_image_inclusion_command():
    man = LatexManager._get_cached_or_new()
    man._stdin_writeln(
        r"\includegraphics[interpolate=true]{%s}"
        # Don't mess with backslashes on Windows.
        % cbook._get_data_path("images/matplotlib.png").as_posix())
    try:
        man._expect_prompt()
        return r"\includegraphics"
    except LatexError:
        # Discard the broken manager.
        LatexManager._get_cached_or_new_impl.cache_clear()
        return r"\pgfimage"


class RendererPgf(RendererBase):

    def __init__(self, figure, fh):
        """
        Create a new PGF renderer that translates any drawing instruction
        into text commands to be interpreted in a latex pgfpicture environment.

        Attributes
        ----------
        figure : `~matplotlib.figure.Figure`
            Matplotlib figure to initialize height, width and dpi from.
        fh : file-like
            File handle for the output of the drawing commands.
        """

        super().__init__()
        self.dpi = figure.dpi
        self.fh = fh
        self.figure = figure
        self.image_counter = 0

    def draw_markers(self, gc, marker_path, marker_trans, path, trans,
                     rgbFace=None):
        # docstring inherited

        _writeln(self.fh, r"\begin{pgfscope}")

        # convert from display units to in
        f = 1. / self.dpi

        # set style and clip
        self._print_pgf_clip(gc)
        self._print_pgf_path_styles(gc, rgbFace)

        # build marker definition
        bl, tr = marker_path.get_extents(marker_trans).get_points()
        coords = bl[0] * f, bl[1] * f, tr[0] * f, tr[1] * f
        _writeln(self.fh,
                 r"\pgfsys@defobject{currentmarker}"
                 r"{\pgfqpoint{%fin}{%fin}}{\pgfqpoint{%fin}{%fin}}{" % coords)
        self._print_pgf_path(None, marker_path, marker_trans)
        self._pgf_path_draw(stroke=gc.get_linewidth() != 0.0,
                            fill=rgbFace is not None)
        _writeln(self.fh, r"}")

        maxcoord = 16383 / 72.27 * self.dpi  # Max dimensions in LaTeX.
        clip = (-maxcoord, -maxcoord, maxcoord, maxcoord)

        # draw marker for each vertex
        for point, code in path.iter_segments(trans, simplify=False,
                                              clip=clip):
            x, y = point[0] * f, point[1] * f
            _writeln(self.fh, r"\begin{pgfscope}")
            _writeln(self.fh, r"\pgfsys@transformshift{%fin}{%fin}" % (x, y))
            _writeln(self.fh, r"\pgfsys@useobject{currentmarker}{}")
            _writeln(self.fh, r"\end{pgfscope}")

        _writeln(self.fh, r"\end{pgfscope}")

    def draw_path(self, gc, path, transform, rgbFace=None):
        # docstring inherited
        _writeln(self.fh, r"\begin{pgfscope}")
        # draw the path
        self._print_pgf_clip(gc)
        self._print_pgf_path_styles(gc, rgbFace)
        self._print_pgf_path(gc, path, transform, rgbFace)
        self._pgf_path_draw(stroke=gc.get_linewidth() != 0.0,
                            fill=rgbFace is not None)
        _writeln(self.fh, r"\end{pgfscope}")

        # if present, draw pattern on top
        if gc.get_hatch():
            _writeln(self.fh, r"\begin{pgfscope}")
            self._print_pgf_path_styles(gc, rgbFace)

            # combine clip and path for clipping
            self._print_pgf_clip(gc)
            self._print_pgf_path(gc, path, transform, rgbFace)
            _writeln(self.fh, r"\pgfusepath{clip}")

            # build pattern definition
            _writeln(self.fh,
                     r"\pgfsys@defobject{currentpattern}"
                     r"{\pgfqpoint{0in}{0in}}{\pgfqpoint{1in}{1in}}{")
            _writeln(self.fh, r"\begin{pgfscope}")
            _writeln(self.fh,
                     r"\pgfpathrectangle"
                     r"{\pgfqpoint{0in}{0in}}{\pgfqpoint{1in}{1in}}")
            _writeln(self.fh, r"\pgfusepath{clip}")
            scale = mpl.transforms.Affine2D().scale(self.dpi)
            self._print_pgf_path(None, gc.get_hatch_path(), scale)
            self._pgf_path_draw(stroke=True)
            _writeln(self.fh, r"\end{pgfscope}")
            _writeln(self.fh, r"}")
            # repeat pattern, filling the bounding rect of the path
            f = 1. / self.dpi
            (xmin, ymin), (xmax, ymax) = \
                path.get_extents(transform).get_points()
            xmin, xmax = f * xmin, f * xmax
            ymin, ymax = f * ymin, f * ymax
            repx, repy = math.ceil(xmax - xmin), math.ceil(ymax - ymin)
            _writeln(self.fh,
                     r"\pgfsys@transformshift{%fin}{%fin}" % (xmin, ymin))
            for iy in range(repy):
                for ix in range(repx):
                    _writeln(self.fh, r"\pgfsys@useobject{currentpattern}{}")
                    _writeln(self.fh, r"\pgfsys@transformshift{1in}{0in}")
                _writeln(self.fh, r"\pgfsys@transformshift{-%din}{0in}" % repx)
                _writeln(self.fh, r"\pgfsys@transformshift{0in}{1in}")

            _writeln(self.fh, r"\end{pgfscope}")

    def _print_pgf_clip(self, gc):
        f = 1. / self.dpi
        # check for clip box
        bbox = gc.get_clip_rectangle()
        if bbox:
            p1, p2 = bbox.get_points()
            w, h = p2 - p1
            coords = p1[0] * f, p1[1] * f, w * f, h * f
            _writeln(self.fh,
                     r"\pgfpathrectangle"
                     r"{\pgfqpoint{%fin}{%fin}}{\pgfqpoint{%fin}{%fin}}"
                     % coords)
            _writeln(self.fh, r"\pgfusepath{clip}")

        # check for clip path
        clippath, clippath_trans = gc.get_clip_path()
        if clippath is not None:
            self._print_pgf_path(gc, clippath, clippath_trans)
            _writeln(self.fh, r"\pgfusepath{clip}")

    def _print_pgf_path_styles(self, gc, rgbFace):
        # cap style
        capstyles = {"butt": r"\pgfsetbuttcap",
                     "round": r"\pgfsetroundcap",
                     "projecting": r"\pgfsetrectcap"}
        _writeln(self.fh, capstyles[gc.get_capstyle()])

        # join style
        joinstyles = {"miter": r"\pgfsetmiterjoin",
                      "round": r"\pgfsetroundjoin",
                      "bevel": r"\pgfsetbeveljoin"}
        _writeln(self.fh, joinstyles[gc.get_joinstyle()])

        # filling
        has_fill = rgbFace is not None

        if gc.get_forced_alpha():
            fillopacity = strokeopacity = gc.get_alpha()
        else:
            strokeopacity = gc.get_rgb()[3]
            fillopacity = rgbFace[3] if has_fill and len(rgbFace) > 3 else 1.0

        if has_fill:
            _writeln(self.fh,
                     r"\definecolor{currentfill}{rgb}{%f,%f,%f}"
                     % tuple(rgbFace[:3]))
            _writeln(self.fh, r"\pgfsetfillcolor{currentfill}")
        if has_fill and fillopacity != 1.0:
            _writeln(self.fh, r"\pgfsetfillopacity{%f}" % fillopacity)

        # linewidth and color
        lw = gc.get_linewidth() * mpl_pt_to_in * latex_in_to_pt
        stroke_rgba = gc.get_rgb()
        _writeln(self.fh, r"\pgfsetlinewidth{%fpt}" % lw)
        _writeln(self.fh,
                 r"\definecolor{currentstroke}{rgb}{%f,%f,%f}"
                 % stroke_rgba[:3])
        _writeln(self.fh, r"\pgfsetstrokecolor{currentstroke}")
        if strokeopacity != 1.0:
            _writeln(self.fh, r"\pgfsetstrokeopacity{%f}" % strokeopacity)

        # line style
        dash_offset, dash_list = gc.get_dashes()
        if dash_list is None:
            _writeln(self.fh, r"\pgfsetdash{}{0pt}")
        else:
            _writeln(self.fh,
                     r"\pgfsetdash{%s}{%fpt}"
                     % ("".join(r"{%fpt}" % dash for dash in dash_list),
                        dash_offset))

    def _print_pgf_path(self, gc, path, transform, rgbFace=None):
        f = 1. / self.dpi
        # check for clip box / ignore clip for filled paths
        bbox = gc.get_clip_rectangle() if gc else None
        maxcoord = 16383 / 72.27 * self.dpi  # Max dimensions in LaTeX.
        if bbox and (rgbFace is None):
            p1, p2 = bbox.get_points()
            clip = (max(p1[0], -maxcoord), max(p1[1], -maxcoord),
                    min(p2[0], maxcoord), min(p2[1], maxcoord))
        else:
            clip = (-maxcoord, -maxcoord, maxcoord, maxcoord)
        # build path
        for points, code in path.iter_segments(transform, clip=clip):
            if code == Path.MOVETO:
                x, y = tuple(points)
                _writeln(self.fh,
                         r"\pgfpathmoveto{\pgfqpoint{%fin}{%fin}}" %
                         (f * x, f * y))
            elif code == Path.CLOSEPOLY:
                _writeln(self.fh, r"\pgfpathclose")
            elif code == Path.LINETO:
                x, y = tuple(points)
                _writeln(self.fh,
                         r"\pgfpathlineto{\pgfqpoint{%fin}{%fin}}" %
                         (f * x, f * y))
            elif code == Path.CURVE3:
                cx, cy, px, py = tuple(points)
                coords = cx * f, cy * f, px * f, py * f
                _writeln(self.fh,
                         r"\pgfpathquadraticcurveto"
                         r"{\pgfqpoint{%fin}{%fin}}{\pgfqpoint{%fin}{%fin}}"
                         % coords)
            elif code == Path.CURVE4:
                c1x, c1y, c2x, c2y, px, py = tuple(points)
                coords = c1x * f, c1y * f, c2x * f, c2y * f, px * f, py * f
                _writeln(self.fh,
                         r"\pgfpathcurveto"
                         r"{\pgfqpoint{%fin}{%fin}}"
                         r"{\pgfqpoint{%fin}{%fin}}"
                         r"{\pgfqpoint{%fin}{%fin}}"
                         % coords)

        # apply pgf decorators
        sketch_params = gc.get_sketch_params() if gc else None
        if sketch_params is not None:
            # Only "length" directly maps to "segment length" in PGF's API.
            # PGF uses "amplitude" to pass the combined deviation in both x-
            # and y-direction, while matplotlib only varies the length of the
            # wiggle along the line ("randomness" and "length" parameters)
            # and has a separate "scale" argument for the amplitude.
            # -> Use "randomness" as PRNG seed to allow the user to force the
            # same shape on multiple sketched lines
            scale, length, randomness = sketch_params
            if scale is not None:
                # make matplotlib and PGF rendering visually similar
                length *= 0.5
                scale *= 2
                # PGF guarantees that repeated loading is a no-op
                _writeln(self.fh, r"\usepgfmodule{decorations}")
                _writeln(self.fh, r"\usepgflibrary{decorations.pathmorphing}")
                _writeln(self.fh, r"\pgfkeys{/pgf/decoration/.cd, "
                         f"segment length = {(length * f):f}in, "
                         f"amplitude = {(scale * f):f}in}}")
                _writeln(self.fh, f"\\pgfmathsetseed{{{int(randomness)}}}")
                _writeln(self.fh, r"\pgfdecoratecurrentpath{random steps}")

    def _pgf_path_draw(self, stroke=True, fill=False):
        actions = []
        if stroke:
            actions.append("stroke")
        if fill:
            actions.append("fill")
        _writeln(self.fh, r"\pgfusepath{%s}" % ",".join(actions))

    def option_scale_image(self):
        # docstring inherited
        return True

    def option_image_nocomposite(self):
        # docstring inherited
        return not mpl.rcParams['image.composite_image']

    def draw_image(self, gc, x, y, im, transform=None):
        # docstring inherited

        h, w = im.shape[:2]
        if w == 0 or h == 0:
            return

        if not os.path.exists(getattr(self.fh, "name", "")):
            raise ValueError(
                "streamed pgf-code does not support raster graphics, consider "
                "using the pgf-to-pdf option")

        # save the images to png files
        path = pathlib.Path(self.fh.name)
        fname_img = "%s-img%d.png" % (path.stem, self.image_counter)
        Image.fromarray(im[::-1]).save(path.parent / fname_img)
        self.image_counter += 1

        # reference the image in the pgf picture
        _writeln(self.fh, r"\begin{pgfscope}")
        self._print_pgf_clip(gc)
        f = 1. / self.dpi  # from display coords to inch
        if transform is None:
            _writeln(self.fh,
                     r"\pgfsys@transformshift{%fin}{%fin}" % (x * f, y * f))
            w, h = w * f, h * f
        else:
            tr1, tr2, tr3, tr4, tr5, tr6 = transform.frozen().to_values()
            _writeln(self.fh,
                     r"\pgfsys@transformcm{%f}{%f}{%f}{%f}{%fin}{%fin}" %
                     (tr1 * f, tr2 * f, tr3 * f, tr4 * f,
                      (tr5 + x) * f, (tr6 + y) * f))
            w = h = 1  # scale is already included in the transform
        interp = str(transform is None).lower()  # interpolation in PDF reader
        _writeln(self.fh,
                 r"\pgftext[left,bottom]"
                 r"{%s[interpolate=%s,width=%fin,height=%fin]{%s}}" %
                 (_get_image_inclusion_command(),
                  interp, w, h, fname_img))
        _writeln(self.fh, r"\end{pgfscope}")

    def draw_tex(self, gc, x, y, s, prop, angle, *, mtext=None):
        # docstring inherited
        self.draw_text(gc, x, y, s, prop, angle, ismath="TeX", mtext=mtext)

    def draw_text(self, gc, x, y, s, prop, angle, ismath=False, mtext=None):
        # docstring inherited

        # prepare string for tex
        s = _escape_and_apply_props(s, prop)

        _writeln(self.fh, r"\begin{pgfscope}")
        self._print_pgf_clip(gc)

        alpha = gc.get_alpha()
        if alpha != 1.0:
            _writeln(self.fh, r"\pgfsetfillopacity{%f}" % alpha)
            _writeln(self.fh, r"\pgfsetstrokeopacity{%f}" % alpha)
        rgb = tuple(gc.get_rgb())[:3]
        _writeln(self.fh, r"\definecolor{textcolor}{rgb}{%f,%f,%f}" % rgb)
        _writeln(self.fh, r"\pgfsetstrokecolor{textcolor}")
        _writeln(self.fh, r"\pgfsetfillcolor{textcolor}")
        s = r"\color{textcolor}" + s

        dpi = self.figure.dpi
        text_args = []
        if mtext and (
                (angle == 0 or
                 mtext.get_rotation_mode() == "anchor") and
                mtext.get_verticalalignment() != "center_baseline"):
            # if text anchoring can be supported, get the original coordinates
            # and add alignment information
            pos = mtext.get_unitless_position()
            x, y = mtext.get_transform().transform(pos)
            halign = {"left": "left", "right": "right", "center": ""}
            valign = {"top": "top", "bottom": "bottom",
                      "baseline": "base", "center": ""}
            text_args.extend([
                f"x={x/dpi:f}in",
                f"y={y/dpi:f}in",
                halign[mtext.get_horizontalalignment()],
                valign[mtext.get_verticalalignment()],
            ])
        else:
            # if not, use the text layout provided by Matplotlib.
            text_args.append(f"x={x/dpi:f}in, y={y/dpi:f}in, left, base")

        if angle != 0:
            text_args.append("rotate=%f" % angle)

        _writeln(self.fh, r"\pgftext[%s]{%s}" % (",".join(text_args), s))
        _writeln(self.fh, r"\end{pgfscope}")

    def get_text_width_height_descent(self, s, prop, ismath):
        # docstring inherited
        # get text metrics in units of latex pt, convert to display units
        w, h, d = (LatexManager._get_cached_or_new()
                   .get_width_height_descent(s, prop))
        # TODO: this should be latex_pt_to_in instead of mpl_pt_to_in
        # but having a little bit more space around the text looks better,
        # plus the bounding box reported by LaTeX is VERY narrow
        f = mpl_pt_to_in * self.dpi
        return w * f, h * f, d * f

    def flipy(self):
        # docstring inherited
        return False

    def get_canvas_width_height(self):
        # docstring inherited
        return (self.figure.get_figwidth() * self.dpi,
                self.figure.get_figheight() * self.dpi)

    def points_to_pixels(self, points):
        # docstring inherited
        return points * mpl_pt_to_in * self.dpi


class FigureCanvasPgf(FigureCanvasBase):
    filetypes = {"pgf": "LaTeX PGF picture",
                 "pdf": "LaTeX compiled PGF picture",
                 "png": "Portable Network Graphics", }

    def get_default_filetype(self):
        return 'pdf'

    def _print_pgf_to_fh(self, fh, *, bbox_inches_restore=None):

        header_text = """%% Creator: Matplotlib, PGF backend
%%
%% To include the figure in your LaTeX document, write
%%   \\input{<filename>.pgf}
%%
%% Make sure the required packages are loaded in your preamble
%%   \\usepackage{pgf}
%%
%% Also ensure that all the required font packages are loaded; for instance,
%% the lmodern package is sometimes necessary when using math font.
%%   \\usepackage{lmodern}
%%
%% Figures using additional raster images can only be included by \\input if
%% they are in the same directory as the main LaTeX file. For loading figures
%% from other directories you can use the `import` package
%%   \\usepackage{import}
%%
%% and then include the figures with
%%   \\import{<path to file>}{<filename>.pgf}
%%
"""

        # append the preamble used by the backend as a comment for debugging
        header_info_preamble = ["%% Matplotlib used the following preamble"]
        for line in _get_preamble().splitlines():
            header_info_preamble.append("%%   " + line)
        header_info_preamble.append("%%")
        header_info_preamble = "\n".join(header_info_preamble)

        # get figure size in inch
        w, h = self.figure.get_figwidth(), self.figure.get_figheight()
        dpi = self.figure.dpi

        # create pgfpicture environment and write the pgf code
        fh.write(header_text)
        fh.write(header_info_preamble)
        fh.write("\n")
        _writeln(fh, r"\begingroup")
        _writeln(fh, r"\makeatletter")
        _writeln(fh, r"\begin{pgfpicture}")
        _writeln(fh,
                 r"\pgfpathrectangle{\pgfpointorigin}{\pgfqpoint{%fin}{%fin}}"
                 % (w, h))
        _writeln(fh, r"\pgfusepath{use as bounding box, clip}")
        renderer = MixedModeRenderer(self.figure, w, h, dpi,
                                     RendererPgf(self.figure, fh),
                                     bbox_inches_restore=bbox_inches_restore)
        self.figure.draw(renderer)

        # end the pgfpicture environment
        _writeln(fh, r"\end{pgfpicture}")
        _writeln(fh, r"\makeatother")
        _writeln(fh, r"\endgroup")

    def print_pgf(self, fname_or_fh, **kwargs):
        """
        Output pgf macros for drawing the figure so it can be included and
        rendered in latex documents.
        """
        with cbook.open_file_cm(fname_or_fh, "w", encoding="utf-8") as file:
            if not cbook.file_requires_unicode(file):
                file = codecs.getwriter("utf-8")(file)
            self._print_pgf_to_fh(file, **kwargs)

    def print_pdf(self, fname_or_fh, *, metadata=None, **kwargs):
        """Use LaTeX to compile a pgf generated figure to pdf."""
        w, h = self.figure.get_size_inches()

        info_dict = _create_pdf_info_dict('pgf', metadata or {})
        pdfinfo = ','.join(
            _metadata_to_str(k, v) for k, v in info_dict.items())

        # print figure to pgf and compile it with latex
        with TemporaryDirectory() as tmpdir:
            tmppath = pathlib.Path(tmpdir)
            self.print_pgf(tmppath / "figure.pgf", **kwargs)
            (tmppath / "figure.tex").write_text(
                "\n".join([
                    _DOCUMENTCLASS,
                    r"\usepackage[pdfinfo={%s}]{hyperref}" % pdfinfo,
                    r"\usepackage[papersize={%fin,%fin}, margin=0in]{geometry}"
                    % (w, h),
                    r"\usepackage{pgf}",
                    _get_preamble(),
                    r"\begin{document}",
                    r"\centering",
                    r"\input{figure.pgf}",
                    r"\end{document}",
                ]), encoding="utf-8")
            texcommand = mpl.rcParams["pgf.texsystem"]
            cbook._check_and_log_subprocess(
                [texcommand, "-interaction=nonstopmode", "-halt-on-error",
                 "figure.tex"], _log, cwd=tmpdir)
            with ((tmppath / "figure.pdf").open("rb") as orig,
                  cbook.open_file_cm(fname_or_fh, "wb") as dest):
                shutil.copyfileobj(orig, dest)  # copy file contents to target

    def print_png(self, fname_or_fh, **kwargs):
        """Use LaTeX to compile a pgf figure to pdf and convert it to png."""
        converter = make_pdf_to_png_converter()
        with TemporaryDirectory() as tmpdir:
            tmppath = pathlib.Path(tmpdir)
            pdf_path = tmppath / "figure.pdf"
            png_path = tmppath / "figure.png"
            self.print_pdf(pdf_path, **kwargs)
            converter(pdf_path, png_path, dpi=self.figure.dpi)
            with (png_path.open("rb") as orig,
                  cbook.open_file_cm(fname_or_fh, "wb") as dest):
                shutil.copyfileobj(orig, dest)  # copy file contents to target

    def get_renderer(self):
        return RendererPgf(self.figure, None)

    def draw(self):
        self.figure.draw_without_rendering()
        return super().draw()


FigureManagerPgf = FigureManagerBase


@_Backend.export
class _BackendPgf(_Backend):
    FigureCanvas = FigureCanvasPgf


class PdfPages:
    """
    A multi-page PDF file using the pgf backend

    Examples
    --------
    >>> import matplotlib.pyplot as plt
    >>> # Initialize:
    >>> with PdfPages('foo.pdf') as pdf:
    ...     # As many times as you like, create a figure fig and save it:
    ...     fig = plt.figure()
    ...     pdf.savefig(fig)
    ...     # When no figure is specified the current figure is saved
    ...     pdf.savefig()
    """

    def __init__(self, filename, *, metadata=None):
        """
        Create a new PdfPages object.

        Parameters
        ----------
        filename : str or path-like
            Plots using `PdfPages.savefig` will be written to a file at this
            location. Any older file with the same name is overwritten.

        metadata : dict, optional
            Information dictionary object (see PDF reference section 10.2.1
            'Document Information Dictionary'), e.g.:
            ``{'Creator': 'My software', 'Author': 'Me', 'Title': 'Awesome'}``.

            The standard keys are 'Title', 'Author', 'Subject', 'Keywords',
            'Creator', 'Producer', 'CreationDate', 'ModDate', and
            'Trapped'. Values have been predefined for 'Creator', 'Producer'
            and 'CreationDate'. They can be removed by setting them to `None`.

            Note that some versions of LaTeX engines may ignore the 'Producer'
            key and set it to themselves.
        """
        self._output_name = filename
        self._n_figures = 0
        self._metadata = (metadata or {}).copy()
        self._info_dict = _create_pdf_info_dict('pgf', self._metadata)
        self._file = BytesIO()

    def _write_header(self, width_inches, height_inches):
        pdfinfo = ','.join(
            _metadata_to_str(k, v) for k, v in self._info_dict.items())
        latex_header = "\n".join([
            _DOCUMENTCLASS,
            r"\usepackage[pdfinfo={%s}]{hyperref}" % pdfinfo,
            r"\usepackage[papersize={%fin,%fin}, margin=0in]{geometry}"
            % (width_inches, height_inches),
            r"\usepackage{pgf}",
            _get_preamble(),
            r"\setlength{\parindent}{0pt}",
            r"\begin{document}%",
        ])
        self._file.write(latex_header.encode('utf-8'))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """
        Finalize this object, running LaTeX in a temporary directory
        and moving the final pdf file to *filename*.
        """
        self._file.write(rb'\end{document}\n')
        if self._n_figures > 0:
            self._run_latex()
        self._file.close()

    def _run_latex(self):
        texcommand = mpl.rcParams["pgf.texsystem"]
        with TemporaryDirectory() as tmpdir:
            tex_source = pathlib.Path(tmpdir, "pdf_pages.tex")
            tex_source.write_bytes(self._file.getvalue())
            cbook._check_and_log_subprocess(
                [texcommand, "-interaction=nonstopmode", "-halt-on-error",
                 tex_source],
                _log, cwd=tmpdir)
            shutil.move(tex_source.with_suffix(".pdf"), self._output_name)

    def savefig(self, figure=None, **kwargs):
        """
        Save a `.Figure` to this file as a new page.

        Any other keyword arguments are passed to `~.Figure.savefig`.

        Parameters
        ----------
        figure : `.Figure` or int, default: the active figure
            The figure, or index of the figure, that is saved to the file.
        """
        if not isinstance(figure, Figure):
            if figure is None:
                manager = Gcf.get_active()
            else:
                manager = Gcf.get_fig_manager(figure)
            if manager is None:
                raise ValueError(f"No figure {figure}")
            figure = manager.canvas.figure

        width, height = figure.get_size_inches()
        if self._n_figures == 0:
            self._write_header(width, height)
        else:
            # \pdfpagewidth and \pdfpageheight exist on pdftex, xetex, and
            # luatex<0.85; they were renamed to \pagewidth and \pageheight
            # on luatex>=0.85.
            self._file.write(
                rb'\newpage'
                rb'\ifdefined\pdfpagewidth\pdfpagewidth\else\pagewidth\fi=%fin'
                rb'\ifdefined\pdfpageheight\pdfpageheight\else\pageheight\fi=%fin'
                b'%%\n' % (width, height)
            )
        figure.savefig(self._file, format="pgf", backend="pgf", **kwargs)
        self._n_figures += 1

    def get_pagecount(self):
        """Return the current number of pages in the multipage pdf file."""
        return self._n_figures
