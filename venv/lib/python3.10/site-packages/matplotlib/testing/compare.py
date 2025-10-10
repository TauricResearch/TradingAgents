"""
Utilities for comparing image results.
"""

import atexit
import functools
import hashlib
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory, TemporaryFile
import weakref
import re

import numpy as np
from PIL import Image

import matplotlib as mpl
from matplotlib import cbook
from matplotlib.testing.exceptions import ImageComparisonFailure

_log = logging.getLogger(__name__)

__all__ = ['calculate_rms', 'comparable_formats', 'compare_images']


def make_test_filename(fname, purpose):
    """
    Make a new filename by inserting *purpose* before the file's extension.
    """
    base, ext = os.path.splitext(fname)
    return f'{base}-{purpose}{ext}'


def _get_cache_path():
    cache_dir = Path(mpl.get_cachedir(), 'test_cache')
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_cache_dir():
    return str(_get_cache_path())


def get_file_hash(path, block_size=2 ** 20):
    sha256 = hashlib.sha256(usedforsecurity=False)
    with open(path, 'rb') as fd:
        while True:
            data = fd.read(block_size)
            if not data:
                break
            sha256.update(data)

    if Path(path).suffix == '.pdf':
        sha256.update(str(mpl._get_executable_info("gs").version).encode('utf-8'))
    elif Path(path).suffix == '.svg':
        sha256.update(str(mpl._get_executable_info("inkscape").version).encode('utf-8'))

    return sha256.hexdigest()


class _ConverterError(Exception):
    pass


class _Converter:
    def __init__(self):
        self._proc = None
        # Explicitly register deletion from an atexit handler because if we
        # wait until the object is GC'd (which occurs later), then some module
        # globals (e.g. signal.SIGKILL) has already been set to None, and
        # kill() doesn't work anymore...
        atexit.register(self.__del__)

    def __del__(self):
        if self._proc:
            self._proc.kill()
            self._proc.wait()
            for stream in filter(None, [self._proc.stdin,
                                        self._proc.stdout,
                                        self._proc.stderr]):
                stream.close()
            self._proc = None

    def _read_until(self, terminator):
        """Read until the prompt is reached."""
        buf = bytearray()
        while True:
            c = self._proc.stdout.read(1)
            if not c:
                raise _ConverterError(os.fsdecode(bytes(buf)))
            buf.extend(c)
            if buf.endswith(terminator):
                return bytes(buf)


class _GSConverter(_Converter):
    def __call__(self, orig, dest):
        if not self._proc:
            self._proc = subprocess.Popen(
                [mpl._get_executable_info("gs").executable,
                 "-dNOSAFER", "-dNOPAUSE", "-dEPSCrop", "-sDEVICE=png16m"],
                # As far as I can see, ghostscript never outputs to stderr.
                stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            try:
                self._read_until(b"\nGS")
            except _ConverterError as e:
                raise OSError(f"Failed to start Ghostscript:\n\n{e.args[0]}") from None

        def encode_and_escape(name):
            return (os.fsencode(name)
                    .replace(b"\\", b"\\\\")
                    .replace(b"(", br"\(")
                    .replace(b")", br"\)"))

        self._proc.stdin.write(
            b"<< /OutputFile ("
            + encode_and_escape(dest)
            + b") >> setpagedevice ("
            + encode_and_escape(orig)
            + b") run flush\n")
        self._proc.stdin.flush()
        # GS> if nothing left on the stack; GS<n> if n items left on the stack.
        err = self._read_until((b"GS<", b"GS>"))
        stack = self._read_until(b">") if err.endswith(b"GS<") else b""
        if stack or not os.path.exists(dest):
            stack_size = int(stack[:-1]) if stack else 0
            self._proc.stdin.write(b"pop\n" * stack_size)
            # Using the systemencoding should at least get the filenames right.
            raise ImageComparisonFailure(
                (err + stack).decode(sys.getfilesystemencoding(), "replace"))


class _SVGConverter(_Converter):
    def __call__(self, orig, dest):
        old_inkscape = mpl._get_executable_info("inkscape").version.major < 1
        terminator = b"\n>" if old_inkscape else b"> "
        if not hasattr(self, "_tmpdir"):
            self._tmpdir = TemporaryDirectory()
            # On Windows, we must make sure that self._proc has terminated
            # (which __del__ does) before clearing _tmpdir.
            weakref.finalize(self._tmpdir, self.__del__)
        if (not self._proc  # First run.
                or self._proc.poll() is not None):  # Inkscape terminated.
            if self._proc is not None and self._proc.poll() is not None:
                for stream in filter(None, [self._proc.stdin,
                                            self._proc.stdout,
                                            self._proc.stderr]):
                    stream.close()
            env = {
                **os.environ,
                # If one passes e.g. a png file to Inkscape, it will try to
                # query the user for conversion options via a GUI (even with
                # `--without-gui`).  Unsetting `DISPLAY` prevents this (and
                # causes GTK to crash and Inkscape to terminate, but that'll
                # just be reported as a regular exception below).
                "DISPLAY": "",
                # Do not load any user options.
                "INKSCAPE_PROFILE_DIR": self._tmpdir.name,
            }
            # Old versions of Inkscape (e.g. 0.48.3.1) seem to sometimes
            # deadlock when stderr is redirected to a pipe, so we redirect it
            # to a temporary file instead.  This is not necessary anymore as of
            # Inkscape 0.92.1.
            stderr = TemporaryFile()
            self._proc = subprocess.Popen(
                ["inkscape", "--without-gui", "--shell"] if old_inkscape else
                ["inkscape", "--shell"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
                env=env, cwd=self._tmpdir.name)
            # Slight abuse, but makes shutdown handling easier.
            self._proc.stderr = stderr
            try:
                self._read_until(terminator)
            except _ConverterError as err:
                raise OSError(
                    "Failed to start Inkscape in interactive mode:\n\n"
                    + err.args[0]) from err

        # Inkscape's shell mode does not support escaping metacharacters in the
        # filename ("\n", and ":;" for inkscape>=1).  Avoid any problems by
        # running from a temporary directory and using fixed filenames.
        inkscape_orig = Path(self._tmpdir.name, os.fsdecode(b"f.svg"))
        inkscape_dest = Path(self._tmpdir.name, os.fsdecode(b"f.png"))
        try:
            inkscape_orig.symlink_to(Path(orig).resolve())
        except OSError:
            shutil.copyfile(orig, inkscape_orig)
        self._proc.stdin.write(
            b"f.svg --export-png=f.png\n" if old_inkscape else
            b"file-open:f.svg;export-filename:f.png;export-do;file-close\n")
        self._proc.stdin.flush()
        try:
            self._read_until(terminator)
        except _ConverterError as err:
            # Inkscape's output is not localized but gtk's is, so the output
            # stream probably has a mixed encoding.  Using the filesystem
            # encoding should at least get the filenames right...
            self._proc.stderr.seek(0)
            raise ImageComparisonFailure(
                self._proc.stderr.read().decode(
                    sys.getfilesystemencoding(), "replace")) from err
        os.remove(inkscape_orig)
        shutil.move(inkscape_dest, dest)

    def __del__(self):
        super().__del__()
        if hasattr(self, "_tmpdir"):
            self._tmpdir.cleanup()


class _SVGWithMatplotlibFontsConverter(_SVGConverter):
    """
    A SVG converter which explicitly adds the fonts shipped by Matplotlib to
    Inkspace's font search path, to better support `svg.fonttype = "none"`
    (which is in particular used by certain mathtext tests).
    """

    def __call__(self, orig, dest):
        if not hasattr(self, "_tmpdir"):
            self._tmpdir = TemporaryDirectory()
            shutil.copytree(cbook._get_data_path("fonts/ttf"),
                            Path(self._tmpdir.name, "fonts"))
        return super().__call__(orig, dest)


def _update_converter():
    try:
        mpl._get_executable_info("gs")
    except mpl.ExecutableNotFoundError:
        pass
    else:
        converter['pdf'] = converter['eps'] = _GSConverter()
    try:
        mpl._get_executable_info("inkscape")
    except mpl.ExecutableNotFoundError:
        pass
    else:
        converter['svg'] = _SVGConverter()


#: A dictionary that maps filename extensions to functions which themselves
#: convert between arguments `old` and `new` (filenames).
converter = {}
_update_converter()
_svg_with_matplotlib_fonts_converter = _SVGWithMatplotlibFontsConverter()


def comparable_formats():
    """
    Return the list of file formats that `.compare_images` can compare
    on this system.

    Returns
    -------
    list of str
        E.g. ``['png', 'pdf', 'svg', 'eps']``.

    """
    return ['png', *converter]


def convert(filename, cache):
    """
    Convert the named file to png; return the name of the created file.

    If *cache* is True, the result of the conversion is cached in
    `matplotlib.get_cachedir() + '/test_cache/'`.  The caching is based on a
    hash of the exact contents of the input file.  Old cache entries are
    automatically deleted as needed to keep the size of the cache capped to
    twice the size of all baseline images.
    """
    path = Path(filename)
    if not path.exists():
        raise OSError(f"{path} does not exist")
    if path.suffix[1:] not in converter:
        import pytest
        pytest.skip(f"Don't know how to convert {path.suffix} files to png")
    newpath = path.parent / f"{path.stem}_{path.suffix[1:]}.png"

    # Only convert the file if the destination doesn't already exist or
    # is out of date.
    if not newpath.exists() or newpath.stat().st_mtime < path.stat().st_mtime:
        cache_dir = _get_cache_path() if cache else None

        if cache_dir is not None:
            _register_conversion_cache_cleaner_once()
            hash_value = get_file_hash(path)
            cached_path = cache_dir / (hash_value + newpath.suffix)
            if cached_path.exists():
                _log.debug("For %s: reusing cached conversion.", filename)
                shutil.copyfile(cached_path, newpath)
                return str(newpath)

        _log.debug("For %s: converting to png.", filename)
        convert = converter[path.suffix[1:]]
        if path.suffix == ".svg":
            contents = path.read_text()
            # NOTE: This check should be kept in sync with font styling in
            # `lib/matplotlib/backends/backend_svg.py`. If it changes, then be sure to
            # re-generate any SVG test files using this mode, or else such tests will
            # fail to use the converter for the expected images (but will for the
            # results), and the tests will fail strangely.
            if re.search(
                # searches for attributes :
                #   style=[font|font-size|font-weight|
                #          font-family|font-variant|font-style]
                # taking care of the possibility of multiple style attributes
                # before the font styling (i.e. opacity)
                r'style="[^"]*font(|-size|-weight|-family|-variant|-style):',
                contents  # raw contents of the svg file
                    ):
                # for svg.fonttype = none, we explicitly patch the font search
                # path so that fonts shipped by Matplotlib are found.
                convert = _svg_with_matplotlib_fonts_converter
        convert(path, newpath)

        if cache_dir is not None:
            _log.debug("For %s: caching conversion result.", filename)
            shutil.copyfile(newpath, cached_path)

    return str(newpath)


def _clean_conversion_cache():
    # This will actually ignore mpl_toolkits baseline images, but they're
    # relatively small.
    baseline_images_size = sum(
        path.stat().st_size
        for path in Path(mpl.__file__).parent.glob("**/baseline_images/**/*"))
    # 2x: one full copy of baselines, and one full copy of test results
    # (actually an overestimate: we don't convert png baselines and results).
    max_cache_size = 2 * baseline_images_size
    # Reduce cache until it fits.
    with cbook._lock_path(_get_cache_path()):
        cache_stat = {
            path: path.stat() for path in _get_cache_path().glob("*")}
        cache_size = sum(stat.st_size for stat in cache_stat.values())
        paths_by_atime = sorted(  # Oldest at the end.
            cache_stat, key=lambda path: cache_stat[path].st_atime,
            reverse=True)
        while cache_size > max_cache_size:
            path = paths_by_atime.pop()
            cache_size -= cache_stat[path].st_size
            path.unlink()


@functools.cache  # Ensure this is only registered once.
def _register_conversion_cache_cleaner_once():
    atexit.register(_clean_conversion_cache)


def crop_to_same(actual_path, actual_image, expected_path, expected_image):
    # clip the images to the same size -- this is useful only when
    # comparing eps to pdf
    if actual_path[-7:-4] == 'eps' and expected_path[-7:-4] == 'pdf':
        aw, ah, ad = actual_image.shape
        ew, eh, ed = expected_image.shape
        actual_image = actual_image[int(aw / 2 - ew / 2):int(
            aw / 2 + ew / 2), int(ah / 2 - eh / 2):int(ah / 2 + eh / 2)]
    return actual_image, expected_image


def calculate_rms(expected_image, actual_image):
    """
    Calculate the per-pixel errors, then compute the root mean square error.
    """
    if expected_image.shape != actual_image.shape:
        raise ImageComparisonFailure(
            f"Image sizes do not match expected size: {expected_image.shape} "
            f"actual size {actual_image.shape}")
    # Convert to float to avoid overflowing finite integer types.
    return np.sqrt(((expected_image - actual_image).astype(float) ** 2).mean())


# NOTE: compare_image and save_diff_image assume that the image does not have
# 16-bit depth, as Pillow converts these to RGB incorrectly.


def _load_image(path):
    img = Image.open(path)
    # In an RGBA image, if the smallest value in the alpha channel is 255, all
    # values in it must be 255, meaning that the image is opaque. If so,
    # discard the alpha channel so that it may compare equal to an RGB image.
    if img.mode != "RGBA" or img.getextrema()[3][0] == 255:
        img = img.convert("RGB")
    return np.asarray(img)


def compare_images(expected, actual, tol, in_decorator=False):
    """
    Compare two "image" files checking differences within a tolerance.

    The two given filenames may point to files which are convertible to
    PNG via the `.converter` dictionary. The underlying RMS is calculated
    with the `.calculate_rms` function.

    Parameters
    ----------
    expected : str
        The filename of the expected image.
    actual : str
        The filename of the actual image.
    tol : float
        The tolerance (a color value difference, where 255 is the
        maximal difference).  The test fails if the average pixel
        difference is greater than this value.
    in_decorator : bool
        Determines the output format. If called from image_comparison
        decorator, this should be True. (default=False)

    Returns
    -------
    None or dict or str
        Return *None* if the images are equal within the given tolerance.

        If the images differ, the return value depends on  *in_decorator*.
        If *in_decorator* is true, a dict with the following entries is
        returned:

        - *rms*: The RMS of the image difference.
        - *expected*: The filename of the expected image.
        - *actual*: The filename of the actual image.
        - *diff_image*: The filename of the difference image.
        - *tol*: The comparison tolerance.

        Otherwise, a human-readable multi-line string representation of this
        information is returned.

    Examples
    --------
    ::

        img1 = "./baseline/plot.png"
        img2 = "./output/plot.png"
        compare_images(img1, img2, 0.001)

    """
    actual = os.fspath(actual)
    if not os.path.exists(actual):
        raise Exception(f"Output image {actual} does not exist.")
    if os.stat(actual).st_size == 0:
        raise Exception(f"Output image file {actual} is empty.")

    # Convert the image to png
    expected = os.fspath(expected)
    if not os.path.exists(expected):
        raise OSError(f'Baseline image {expected!r} does not exist.')
    extension = expected.split('.')[-1]
    if extension != 'png':
        actual = convert(actual, cache=True)
        expected = convert(expected, cache=True)

    # open the image files
    expected_image = _load_image(expected)
    actual_image = _load_image(actual)

    actual_image, expected_image = crop_to_same(
        actual, actual_image, expected, expected_image)

    diff_image = make_test_filename(actual, 'failed-diff')

    if tol <= 0:
        if np.array_equal(expected_image, actual_image):
            return None

    # convert to signed integers, so that the images can be subtracted without
    # overflow
    expected_image = expected_image.astype(np.int16)
    actual_image = actual_image.astype(np.int16)

    rms = calculate_rms(expected_image, actual_image)

    if rms <= tol:
        return None

    save_diff_image(expected, actual, diff_image)

    results = dict(rms=rms, expected=str(expected),
                   actual=str(actual), diff=str(diff_image), tol=tol)

    if not in_decorator:
        # Then the results should be a string suitable for stdout.
        template = ['Error: Image files did not match.',
                    'RMS Value: {rms}',
                    'Expected:  \n    {expected}',
                    'Actual:    \n    {actual}',
                    'Difference:\n    {diff}',
                    'Tolerance: \n    {tol}', ]
        results = '\n  '.join([line.format(**results) for line in template])
    return results


def save_diff_image(expected, actual, output):
    """
    Parameters
    ----------
    expected : str
        File path of expected image.
    actual : str
        File path of actual image.
    output : str
        File path to save difference image to.
    """
    expected_image = _load_image(expected)
    actual_image = _load_image(actual)
    actual_image, expected_image = crop_to_same(
        actual, actual_image, expected, expected_image)
    expected_image = np.array(expected_image, float)
    actual_image = np.array(actual_image, float)
    if expected_image.shape != actual_image.shape:
        raise ImageComparisonFailure(
            f"Image sizes do not match expected size: {expected_image.shape} "
            f"actual size {actual_image.shape}")
    abs_diff = np.abs(expected_image - actual_image)

    # expand differences in luminance domain
    abs_diff *= 10
    abs_diff = np.clip(abs_diff, 0, 255).astype(np.uint8)

    if abs_diff.shape[2] == 4:  # Hard-code the alpha channel to fully solid
        abs_diff[:, :, 3] = 255

    Image.fromarray(abs_diff).save(output, format="png")
