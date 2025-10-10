import abc
import base64
import contextlib
from io import BytesIO, TextIOWrapper
import itertools
import logging
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import uuid
import warnings

import numpy as np
from PIL import Image

import matplotlib as mpl
from matplotlib._animation_data import (
    DISPLAY_TEMPLATE, INCLUDED_FRAMES, JS_INCLUDE, STYLE_INCLUDE)
from matplotlib import _api, cbook
import matplotlib.colors as mcolors

_log = logging.getLogger(__name__)

# Process creation flag for subprocess to prevent it raising a terminal
# window. See for example https://stackoverflow.com/q/24130623/
subprocess_creation_flags = (
    subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)


def adjusted_figsize(w, h, dpi, n):
    """
    Compute figure size so that pixels are a multiple of n.

    Parameters
    ----------
    w, h : float
        Size in inches.

    dpi : float
        The dpi.

    n : int
        The target multiple.

    Returns
    -------
    wnew, hnew : float
        The new figure size in inches.
    """

    # this maybe simplified if / when we adopt consistent rounding for
    # pixel size across the whole library
    def correct_roundoff(x, dpi, n):
        if int(x*dpi) % n != 0:
            if int(np.nextafter(x, np.inf)*dpi) % n == 0:
                x = np.nextafter(x, np.inf)
            elif int(np.nextafter(x, -np.inf)*dpi) % n == 0:
                x = np.nextafter(x, -np.inf)
        return x

    wnew = int(w * dpi / n) * n / dpi
    hnew = int(h * dpi / n) * n / dpi
    return correct_roundoff(wnew, dpi, n), correct_roundoff(hnew, dpi, n)


class MovieWriterRegistry:
    """Registry of available writer classes by human readable name."""

    def __init__(self):
        self._registered = dict()

    def register(self, name):
        """
        Decorator for registering a class under a name.

        Example use::

            @registry.register(name)
            class Foo:
                pass
        """
        def wrapper(writer_cls):
            self._registered[name] = writer_cls
            return writer_cls
        return wrapper

    def is_available(self, name):
        """
        Check if given writer is available by name.

        Parameters
        ----------
        name : str

        Returns
        -------
        bool
        """
        try:
            cls = self._registered[name]
        except KeyError:
            return False
        return cls.isAvailable()

    def __iter__(self):
        """Iterate over names of available writer class."""
        for name in self._registered:
            if self.is_available(name):
                yield name

    def list(self):
        """Get a list of available MovieWriters."""
        return [*self]

    def __getitem__(self, name):
        """Get an available writer class from its name."""
        if self.is_available(name):
            return self._registered[name]
        raise RuntimeError(f"Requested MovieWriter ({name}) not available")


writers = MovieWriterRegistry()


class AbstractMovieWriter(abc.ABC):
    """
    Abstract base class for writing movies, providing a way to grab frames by
    calling `~AbstractMovieWriter.grab_frame`.

    `setup` is called to start the process and `finish` is called afterwards.
    `saving` is provided as a context manager to facilitate this process as ::

        with moviewriter.saving(fig, outfile='myfile.mp4', dpi=100):
            # Iterate over frames
            moviewriter.grab_frame(**savefig_kwargs)

    The use of the context manager ensures that `setup` and `finish` are
    performed as necessary.

    An instance of a concrete subclass of this class can be given as the
    ``writer`` argument of `Animation.save()`.
    """

    def __init__(self, fps=5, metadata=None, codec=None, bitrate=None):
        self.fps = fps
        self.metadata = metadata if metadata is not None else {}
        self.codec = mpl._val_or_rc(codec, 'animation.codec')
        self.bitrate = mpl._val_or_rc(bitrate, 'animation.bitrate')

    @abc.abstractmethod
    def setup(self, fig, outfile, dpi=None):
        """
        Setup for writing the movie file.

        Parameters
        ----------
        fig : `~matplotlib.figure.Figure`
            The figure object that contains the information for frames.
        outfile : str
            The filename of the resulting movie file.
        dpi : float, default: ``fig.dpi``
            The DPI (or resolution) for the file.  This controls the size
            in pixels of the resulting movie file.
        """
        # Check that path is valid
        Path(outfile).parent.resolve(strict=True)
        self.outfile = outfile
        self.fig = fig
        if dpi is None:
            dpi = self.fig.dpi
        self.dpi = dpi

    @property
    def frame_size(self):
        """A tuple ``(width, height)`` in pixels of a movie frame."""
        w, h = self.fig.get_size_inches()
        return int(w * self.dpi), int(h * self.dpi)

    def _supports_transparency(self):
        """
        Whether this writer supports transparency.

        Writers may consult output file type and codec to determine this at runtime.
        """
        return False

    @abc.abstractmethod
    def grab_frame(self, **savefig_kwargs):
        """
        Grab the image information from the figure and save as a movie frame.

        All keyword arguments in *savefig_kwargs* are passed on to the
        `~.Figure.savefig` call that saves the figure.  However, several
        keyword arguments that are supported by `~.Figure.savefig` may not be
        passed as they are controlled by the MovieWriter:

        - *dpi*, *bbox_inches*:  These may not be passed because each frame of the
           animation much be exactly the same size in pixels.
        - *format*: This is controlled by the MovieWriter.
        """

    @abc.abstractmethod
    def finish(self):
        """Finish any processing for writing the movie."""

    @contextlib.contextmanager
    def saving(self, fig, outfile, dpi, *args, **kwargs):
        """
        Context manager to facilitate writing the movie file.

        ``*args, **kw`` are any parameters that should be passed to `setup`.
        """
        if mpl.rcParams['savefig.bbox'] == 'tight':
            _log.info("Disabling savefig.bbox = 'tight', as it may cause "
                      "frame size to vary, which is inappropriate for "
                      "animation.")

        # This particular sequence is what contextlib.contextmanager wants
        self.setup(fig, outfile, dpi, *args, **kwargs)
        with mpl.rc_context({'savefig.bbox': None}):
            try:
                yield self
            finally:
                self.finish()


class MovieWriter(AbstractMovieWriter):
    """
    Base class for writing movies.

    This is a base class for MovieWriter subclasses that write a movie frame
    data to a pipe. You cannot instantiate this class directly.
    See examples for how to use its subclasses.

    Attributes
    ----------
    frame_format : str
        The format used in writing frame data, defaults to 'rgba'.
    fig : `~matplotlib.figure.Figure`
        The figure to capture data from.
        This must be provided by the subclasses.
    """

    # Builtin writer subclasses additionally define the _exec_key and _args_key
    # attributes, which indicate the rcParams entries where the path to the
    # executable and additional command-line arguments to the executable are
    # stored.  Third-party writers cannot meaningfully set these as they cannot
    # extend rcParams with new keys.

    # Pipe-based writers only support RGBA, but file-based ones support more
    # formats.
    supported_formats = ["rgba"]

    def __init__(self, fps=5, codec=None, bitrate=None, extra_args=None,
                 metadata=None):
        """
        Parameters
        ----------
        fps : int, default: 5
            Movie frame rate (per second).
        codec : str or None, default: :rc:`animation.codec`
            The codec to use.
        bitrate : int, default: :rc:`animation.bitrate`
            The bitrate of the movie, in kilobits per second.  Higher values
            means higher quality movies, but increase the file size.  A value
            of -1 lets the underlying movie encoder select the bitrate.
        extra_args : list of str or None, optional
            Extra command-line arguments passed to the underlying movie encoder. These
            arguments are passed last to the encoder, just before the filename. The
            default, None, means to use :rc:`animation.[name-of-encoder]_args` for the
            builtin writers.
        metadata : dict[str, str], default: {}
            A dictionary of keys and values for metadata to include in the
            output file. Some keys that may be of use include:
            title, artist, genre, subject, copyright, srcform, comment.
        """
        if type(self) is MovieWriter:
            # TODO MovieWriter is still an abstract class and needs to be
            #      extended with a mixin. This should be clearer in naming
            #      and description. For now, just give a reasonable error
            #      message to users.
            raise TypeError(
                'MovieWriter cannot be instantiated directly. Please use one '
                'of its subclasses.')

        super().__init__(fps=fps, metadata=metadata, codec=codec,
                         bitrate=bitrate)
        self.frame_format = self.supported_formats[0]
        self.extra_args = extra_args

    def _adjust_frame_size(self):
        if self.codec == 'h264':
            wo, ho = self.fig.get_size_inches()
            w, h = adjusted_figsize(wo, ho, self.dpi, 2)
            if (wo, ho) != (w, h):
                self.fig.set_size_inches(w, h, forward=True)
                _log.info('figure size in inches has been adjusted '
                          'from %s x %s to %s x %s', wo, ho, w, h)
        else:
            w, h = self.fig.get_size_inches()
        _log.debug('frame size in pixels is %s x %s', *self.frame_size)
        return w, h

    def setup(self, fig, outfile, dpi=None):
        # docstring inherited
        super().setup(fig, outfile, dpi=dpi)
        self._w, self._h = self._adjust_frame_size()
        # Run here so that grab_frame() can write the data to a pipe. This
        # eliminates the need for temp files.
        self._run()

    def _run(self):
        # Uses subprocess to call the program for assembling frames into a
        # movie file.  *args* returns the sequence of command line arguments
        # from a few configuration options.
        command = self._args()
        _log.info('MovieWriter._run: running command: %s',
                  cbook._pformat_subprocess(command))
        PIPE = subprocess.PIPE
        self._proc = subprocess.Popen(
            command, stdin=PIPE, stdout=PIPE, stderr=PIPE,
            creationflags=subprocess_creation_flags)

    def finish(self):
        """Finish any processing for writing the movie."""
        out, err = self._proc.communicate()
        # Use the encoding/errors that universal_newlines would use.
        out = TextIOWrapper(BytesIO(out)).read()
        err = TextIOWrapper(BytesIO(err)).read()
        if out:
            _log.log(
                logging.WARNING if self._proc.returncode else logging.DEBUG,
                "MovieWriter stdout:\n%s", out)
        if err:
            _log.log(
                logging.WARNING if self._proc.returncode else logging.DEBUG,
                "MovieWriter stderr:\n%s", err)
        if self._proc.returncode:
            raise subprocess.CalledProcessError(
                self._proc.returncode, self._proc.args, out, err)

    def grab_frame(self, **savefig_kwargs):
        # docstring inherited
        _validate_grabframe_kwargs(savefig_kwargs)
        _log.debug('MovieWriter.grab_frame: Grabbing frame.')
        # Readjust the figure size in case it has been changed by the user.
        # All frames must have the same size to save the movie correctly.
        self.fig.set_size_inches(self._w, self._h)
        # Save the figure data to the sink, using the frame format and dpi.
        self.fig.savefig(self._proc.stdin, format=self.frame_format,
                         dpi=self.dpi, **savefig_kwargs)

    def _args(self):
        """Assemble list of encoder-specific command-line arguments."""
        return NotImplementedError("args needs to be implemented by subclass.")

    @classmethod
    def bin_path(cls):
        """
        Return the binary path to the commandline tool used by a specific
        subclass. This is a class method so that the tool can be looked for
        before making a particular MovieWriter subclass available.
        """
        return str(mpl.rcParams[cls._exec_key])

    @classmethod
    def isAvailable(cls):
        """Return whether a MovieWriter subclass is actually available."""
        return shutil.which(cls.bin_path()) is not None


class FileMovieWriter(MovieWriter):
    """
    `MovieWriter` for writing to individual files and stitching at the end.

    This must be sub-classed to be useful.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.frame_format = mpl.rcParams['animation.frame_format']

    def setup(self, fig, outfile, dpi=None, frame_prefix=None):
        """
        Setup for writing the movie file.

        Parameters
        ----------
        fig : `~matplotlib.figure.Figure`
            The figure to grab the rendered frames from.
        outfile : str
            The filename of the resulting movie file.
        dpi : float, default: ``fig.dpi``
            The dpi of the output file. This, with the figure size,
            controls the size in pixels of the resulting movie file.
        frame_prefix : str, optional
            The filename prefix to use for temporary files.  If *None* (the
            default), files are written to a temporary directory which is
            deleted by `finish`; if not *None*, no temporary files are
            deleted.
        """
        # Check that path is valid
        Path(outfile).parent.resolve(strict=True)
        self.fig = fig
        self.outfile = outfile
        if dpi is None:
            dpi = self.fig.dpi
        self.dpi = dpi
        self._adjust_frame_size()

        if frame_prefix is None:
            self._tmpdir = TemporaryDirectory()
            self.temp_prefix = str(Path(self._tmpdir.name, 'tmp'))
        else:
            self._tmpdir = None
            self.temp_prefix = frame_prefix
        self._frame_counter = 0  # used for generating sequential file names
        self._temp_paths = list()
        self.fname_format_str = '%s%%07d.%s'

    def __del__(self):
        if hasattr(self, '_tmpdir') and self._tmpdir:
            self._tmpdir.cleanup()

    @property
    def frame_format(self):
        """
        Format (png, jpeg, etc.) to use for saving the frames, which can be
        decided by the individual subclasses.
        """
        return self._frame_format

    @frame_format.setter
    def frame_format(self, frame_format):
        if frame_format in self.supported_formats:
            self._frame_format = frame_format
        else:
            _api.warn_external(
                f"Ignoring file format {frame_format!r} which is not "
                f"supported by {type(self).__name__}; using "
                f"{self.supported_formats[0]} instead.")
            self._frame_format = self.supported_formats[0]

    def _base_temp_name(self):
        # Generates a template name (without number) given the frame format
        # for extension and the prefix.
        return self.fname_format_str % (self.temp_prefix, self.frame_format)

    def grab_frame(self, **savefig_kwargs):
        # docstring inherited
        # Creates a filename for saving using basename and counter.
        _validate_grabframe_kwargs(savefig_kwargs)
        path = Path(self._base_temp_name() % self._frame_counter)
        self._temp_paths.append(path)  # Record the filename for later use.
        self._frame_counter += 1  # Ensures each created name is unique.
        _log.debug('FileMovieWriter.grab_frame: Grabbing frame %d to path=%s',
                   self._frame_counter, path)
        with open(path, 'wb') as sink:  # Save figure to the sink.
            self.fig.savefig(sink, format=self.frame_format, dpi=self.dpi,
                             **savefig_kwargs)

    def finish(self):
        # Call run here now that all frame grabbing is done. All temp files
        # are available to be assembled.
        try:
            self._run()
            super().finish()
        finally:
            if self._tmpdir:
                _log.debug(
                    'MovieWriter: clearing temporary path=%s', self._tmpdir
                )
                self._tmpdir.cleanup()


@writers.register('pillow')
class PillowWriter(AbstractMovieWriter):
    def _supports_transparency(self):
        return True

    @classmethod
    def isAvailable(cls):
        return True

    def setup(self, fig, outfile, dpi=None):
        super().setup(fig, outfile, dpi=dpi)
        self._frames = []

    def grab_frame(self, **savefig_kwargs):
        _validate_grabframe_kwargs(savefig_kwargs)
        buf = BytesIO()
        self.fig.savefig(
            buf, **{**savefig_kwargs, "format": "rgba", "dpi": self.dpi})
        im = Image.frombuffer(
            "RGBA", self.frame_size, buf.getbuffer(), "raw", "RGBA", 0, 1)
        if im.getextrema()[3][0] < 255:
            # This frame has transparency, so we'll just add it as is.
            self._frames.append(im)
        else:
            # Without transparency, we switch to RGB mode, which converts to P mode a
            # little better if needed (specifically, this helps with GIF output.)
            self._frames.append(im.convert("RGB"))

    def finish(self):
        self._frames[0].save(
            self.outfile, save_all=True, append_images=self._frames[1:],
            duration=int(1000 / self.fps), loop=0)


# Base class of ffmpeg information. Has the config keys and the common set
# of arguments that controls the *output* side of things.
class FFMpegBase:
    """
    Mixin class for FFMpeg output.

    This is a base class for the concrete `FFMpegWriter` and `FFMpegFileWriter`
    classes.
    """

    _exec_key = 'animation.ffmpeg_path'
    _args_key = 'animation.ffmpeg_args'

    def _supports_transparency(self):
        suffix = Path(self.outfile).suffix
        if suffix in {'.apng', '.avif', '.gif', '.webm', '.webp'}:
            return True
        # This list was found by going through `ffmpeg -codecs` for video encoders,
        # running them with _support_transparency() forced to True, and checking that
        # the "Pixel format" in Kdenlive included alpha. Note this is not a guarantee
        # that transparency will work; you may also need to pass `-pix_fmt`, but we
        # trust the user has done so if they are asking for these formats.
        return self.codec in {
            'apng', 'avrp', 'bmp', 'cfhd', 'dpx', 'ffv1', 'ffvhuff', 'gif', 'huffyuv',
            'jpeg2000', 'ljpeg', 'png', 'prores', 'prores_aw', 'prores_ks', 'qtrle',
            'rawvideo', 'targa', 'tiff', 'utvideo', 'v408', }

    @property
    def output_args(self):
        args = []
        suffix = Path(self.outfile).suffix
        if suffix in {'.apng', '.avif', '.gif', '.webm', '.webp'}:
            self.codec = suffix[1:]
        else:
            args.extend(['-vcodec', self.codec])
        extra_args = (self.extra_args if self.extra_args is not None
                      else mpl.rcParams[self._args_key])
        # For h264, the default format is yuv444p, which is not compatible
        # with quicktime (and others). Specifying yuv420p fixes playback on
        # iOS, as well as HTML5 video in firefox and safari (on both Windows and
        # macOS). Also fixes internet explorer. This is as of 2015/10/29.
        if self.codec == 'h264' and '-pix_fmt' not in extra_args:
            args.extend(['-pix_fmt', 'yuv420p'])
        # For GIF, we're telling FFmpeg to split the video stream, to generate
        # a palette, and then use it for encoding.
        elif self.codec == 'gif' and '-filter_complex' not in extra_args:
            args.extend(['-filter_complex',
                         'split [a][b];[a] palettegen [p];[b][p] paletteuse'])
        # For AVIF, we're telling FFmpeg to split the video stream, extract the alpha,
        # in order to place it in a secondary stream, as needed by AVIF-in-FFmpeg.
        elif self.codec == 'avif' and '-filter_complex' not in extra_args:
            args.extend(['-filter_complex',
                         'split [rgb][rgba]; [rgba] alphaextract [alpha]',
                         '-map', '[rgb]', '-map', '[alpha]'])
        if self.bitrate > 0:
            args.extend(['-b', '%dk' % self.bitrate])  # %dk: bitrate in kbps.
        for k, v in self.metadata.items():
            args.extend(['-metadata', f'{k}={v}'])
        args.extend(extra_args)

        return args + ['-y', self.outfile]


# Combine FFMpeg options with pipe-based writing
@writers.register('ffmpeg')
class FFMpegWriter(FFMpegBase, MovieWriter):
    """
    Pipe-based ffmpeg writer.

    Frames are streamed directly to ffmpeg via a pipe and written in a single pass.

    This effectively works as a slideshow input to ffmpeg with the fps passed as
    ``-framerate``, so see also `their notes on frame rates`_ for further details.

    .. _their notes on frame rates: https://trac.ffmpeg.org/wiki/Slideshow#Framerates
    """
    def _args(self):
        # Returns the command line parameters for subprocess to use
        # ffmpeg to create a movie using a pipe.
        args = [self.bin_path(), '-f', 'rawvideo', '-vcodec', 'rawvideo',
                '-s', '%dx%d' % self.frame_size, '-pix_fmt', self.frame_format,
                '-framerate', str(self.fps)]
        # Logging is quieted because subprocess.PIPE has limited buffer size.
        # If you have a lot of frames in your animation and set logging to
        # DEBUG, you will have a buffer overrun.
        if _log.getEffectiveLevel() > logging.DEBUG:
            args += ['-loglevel', 'error']
        args += ['-i', 'pipe:'] + self.output_args
        return args


# Combine FFMpeg options with temp file-based writing
@writers.register('ffmpeg_file')
class FFMpegFileWriter(FFMpegBase, FileMovieWriter):
    """
    File-based ffmpeg writer.

    Frames are written to temporary files on disk and then stitched together at the end.

    This effectively works as a slideshow input to ffmpeg with the fps passed as
    ``-framerate``, so see also `their notes on frame rates`_ for further details.

    .. _their notes on frame rates: https://trac.ffmpeg.org/wiki/Slideshow#Framerates
    """
    supported_formats = ['png', 'jpeg', 'tiff', 'raw', 'rgba']

    def _args(self):
        # Returns the command line parameters for subprocess to use
        # ffmpeg to create a movie using a collection of temp images
        args = []
        # For raw frames, we need to explicitly tell ffmpeg the metadata.
        if self.frame_format in {'raw', 'rgba'}:
            args += [
                '-f', 'image2', '-vcodec', 'rawvideo',
                '-video_size', '%dx%d' % self.frame_size,
                '-pixel_format', 'rgba',
            ]
        args += ['-framerate', str(self.fps), '-i', self._base_temp_name()]
        if not self._tmpdir:
            args += ['-frames:v', str(self._frame_counter)]
        # Logging is quieted because subprocess.PIPE has limited buffer size.
        # If you have a lot of frames in your animation and set logging to
        # DEBUG, you will have a buffer overrun.
        if _log.getEffectiveLevel() > logging.DEBUG:
            args += ['-loglevel', 'error']
        return [self.bin_path(), *args, *self.output_args]


# Base class for animated GIFs with ImageMagick
class ImageMagickBase:
    """
    Mixin class for ImageMagick output.

    This is a base class for the concrete `ImageMagickWriter` and
    `ImageMagickFileWriter` classes, which define an ``input_names`` attribute
    (or property) specifying the input names passed to ImageMagick.
    """

    _exec_key = 'animation.convert_path'
    _args_key = 'animation.convert_args'

    def _supports_transparency(self):
        suffix = Path(self.outfile).suffix
        return suffix in {'.apng', '.avif', '.gif', '.webm', '.webp'}

    def _args(self):
        # ImageMagick does not recognize "raw".
        fmt = "rgba" if self.frame_format == "raw" else self.frame_format
        extra_args = (self.extra_args if self.extra_args is not None
                      else mpl.rcParams[self._args_key])
        return [
            self.bin_path(),
            "-size", "%ix%i" % self.frame_size,
            "-depth", "8",
            "-delay", str(100 / self.fps),
            "-loop", "0",
            f"{fmt}:{self.input_names}",
            *extra_args,
            self.outfile,
        ]

    @classmethod
    def bin_path(cls):
        binpath = super().bin_path()
        if binpath == 'convert':
            binpath = mpl._get_executable_info('magick').executable
        return binpath

    @classmethod
    def isAvailable(cls):
        try:
            return super().isAvailable()
        except mpl.ExecutableNotFoundError as _enf:
            # May be raised by get_executable_info.
            _log.debug('ImageMagick unavailable due to: %s', _enf)
            return False


# Combine ImageMagick options with pipe-based writing
@writers.register('imagemagick')
class ImageMagickWriter(ImageMagickBase, MovieWriter):
    """
    Pipe-based animated gif writer.

    Frames are streamed directly to ImageMagick via a pipe and written
    in a single pass.
    """

    input_names = "-"  # stdin


# Combine ImageMagick options with temp file-based writing
@writers.register('imagemagick_file')
class ImageMagickFileWriter(ImageMagickBase, FileMovieWriter):
    """
    File-based animated gif writer.

    Frames are written to temporary files on disk and then stitched
    together at the end.
    """

    supported_formats = ['png', 'jpeg', 'tiff', 'raw', 'rgba']
    input_names = property(
        lambda self: f'{self.temp_prefix}*.{self.frame_format}')


# Taken directly from jakevdp's JSAnimation package at
# http://github.com/jakevdp/JSAnimation
def _included_frames(frame_count, frame_format, frame_dir):
    return INCLUDED_FRAMES.format(Nframes=frame_count,
                                  frame_dir=frame_dir,
                                  frame_format=frame_format)


def _embedded_frames(frame_list, frame_format):
    """frame_list should be a list of base64-encoded png files"""
    if frame_format == 'svg':
        # Fix MIME type for svg
        frame_format = 'svg+xml'
    template = '  frames[{0}] = "data:image/{1};base64,{2}"\n'
    return "\n" + "".join(
        template.format(i, frame_format, frame_data.replace('\n', '\\\n'))
        for i, frame_data in enumerate(frame_list))


@writers.register('html')
class HTMLWriter(FileMovieWriter):
    """Writer for JavaScript-based HTML movies."""

    supported_formats = ['png', 'jpeg', 'tiff', 'svg']

    @classmethod
    def isAvailable(cls):
        return True

    def __init__(self, fps=30, codec=None, bitrate=None, extra_args=None,
                 metadata=None, embed_frames=False, default_mode='loop',
                 embed_limit=None):

        if extra_args:
            _log.warning("HTMLWriter ignores 'extra_args'")
        extra_args = ()  # Don't lookup nonexistent rcParam[args_key].
        self.embed_frames = embed_frames
        self.default_mode = default_mode.lower()
        _api.check_in_list(['loop', 'once', 'reflect'],
                           default_mode=self.default_mode)

        # Save embed limit, which is given in MB
        self._bytes_limit = mpl._val_or_rc(embed_limit, 'animation.embed_limit')
        # Convert from MB to bytes
        self._bytes_limit *= 1024 * 1024

        super().__init__(fps, codec, bitrate, extra_args, metadata)

    def setup(self, fig, outfile, dpi=None, frame_dir=None):
        outfile = Path(outfile)
        _api.check_in_list(['.html', '.htm'], outfile_extension=outfile.suffix)

        self._saved_frames = []
        self._total_bytes = 0
        self._hit_limit = False

        if not self.embed_frames:
            if frame_dir is None:
                frame_dir = outfile.with_name(outfile.stem + '_frames')
            frame_dir.mkdir(parents=True, exist_ok=True)
            frame_prefix = frame_dir / 'frame'
        else:
            frame_prefix = None

        super().setup(fig, outfile, dpi, frame_prefix)
        self._clear_temp = False

    def grab_frame(self, **savefig_kwargs):
        _validate_grabframe_kwargs(savefig_kwargs)
        if self.embed_frames:
            # Just stop processing if we hit the limit
            if self._hit_limit:
                return
            f = BytesIO()
            self.fig.savefig(f, format=self.frame_format,
                             dpi=self.dpi, **savefig_kwargs)
            imgdata64 = base64.encodebytes(f.getvalue()).decode('ascii')
            self._total_bytes += len(imgdata64)
            if self._total_bytes >= self._bytes_limit:
                _log.warning(
                    "Animation size has reached %s bytes, exceeding the limit "
                    "of %s. If you're sure you want a larger animation "
                    "embedded, set the animation.embed_limit rc parameter to "
                    "a larger value (in MB). This and further frames will be "
                    "dropped.", self._total_bytes, self._bytes_limit)
                self._hit_limit = True
            else:
                self._saved_frames.append(imgdata64)
        else:
            return super().grab_frame(**savefig_kwargs)

    def finish(self):
        # save the frames to an html file
        if self.embed_frames:
            fill_frames = _embedded_frames(self._saved_frames,
                                           self.frame_format)
            frame_count = len(self._saved_frames)
        else:
            # temp names is filled by FileMovieWriter
            frame_count = len(self._temp_paths)
            fill_frames = _included_frames(
                frame_count, self.frame_format,
                self._temp_paths[0].parent.relative_to(self.outfile.parent))
        mode_dict = dict(once_checked='',
                         loop_checked='',
                         reflect_checked='')
        mode_dict[self.default_mode + '_checked'] = 'checked'

        interval = 1000 // self.fps

        with open(self.outfile, 'w') as of:
            of.write(JS_INCLUDE + STYLE_INCLUDE)
            of.write(DISPLAY_TEMPLATE.format(id=uuid.uuid4().hex,
                                             Nframes=frame_count,
                                             fill_frames=fill_frames,
                                             interval=interval,
                                             **mode_dict))

        # Duplicate the temporary file clean up logic from
        # FileMovieWriter.finish.  We cannot call the inherited version of
        # finish because it assumes that there is a subprocess that we either
        # need to call to merge many frames together or that there is a
        # subprocess call that we need to clean up.
        if self._tmpdir:
            _log.debug('MovieWriter: clearing temporary path=%s', self._tmpdir)
            self._tmpdir.cleanup()


class Animation:
    """
    A base class for Animations.

    This class is not usable as is, and should be subclassed to provide needed
    behavior.

    .. note::

        You must store the created Animation in a variable that lives as long
        as the animation should run. Otherwise, the Animation object will be
        garbage-collected and the animation stops.

    Parameters
    ----------
    fig : `~matplotlib.figure.Figure`
        The figure object used to get needed events, such as draw or resize.

    event_source : object, optional
        A class that can run a callback when desired events
        are generated, as well as be stopped and started.

        Examples include timers (see `TimedAnimation`) and file
        system notifications.

    blit : bool, default: False
        Whether blitting is used to optimize drawing.  If the backend does not
        support blitting, then this parameter has no effect.

    See Also
    --------
    FuncAnimation,  ArtistAnimation
    """

    def __init__(self, fig, event_source=None, blit=False):
        self._draw_was_started = False

        self._fig = fig
        # Disables blitting for backends that don't support it.  This
        # allows users to request it if available, but still have a
        # fallback that works if it is not.
        self._blit = blit and fig.canvas.supports_blit

        # These are the basics of the animation.  The frame sequence represents
        # information for each frame of the animation and depends on how the
        # drawing is handled by the subclasses. The event source fires events
        # that cause the frame sequence to be iterated.
        self.frame_seq = self.new_frame_seq()
        self.event_source = event_source

        # Instead of starting the event source now, we connect to the figure's
        # draw_event, so that we only start once the figure has been drawn.
        self._first_draw_id = fig.canvas.mpl_connect('draw_event', self._start)

        # Connect to the figure's close_event so that we don't continue to
        # fire events and try to draw to a deleted figure.
        self._close_id = self._fig.canvas.mpl_connect('close_event',
                                                      self._stop)
        if self._blit:
            self._setup_blit()

    def __del__(self):
        if not getattr(self, '_draw_was_started', True):
            warnings.warn(
                'Animation was deleted without rendering anything. This is '
                'most likely not intended. To prevent deletion, assign the '
                'Animation to a variable, e.g. `anim`, that exists until you '
                'output the Animation using `plt.show()` or '
                '`anim.save()`.'
            )

    def _start(self, *args):
        """
        Starts interactive animation. Adds the draw frame command to the GUI
        handler, calls show to start the event loop.
        """
        # Do not start the event source if saving() it.
        if self._fig.canvas.is_saving():
            return
        # First disconnect our draw event handler
        self._fig.canvas.mpl_disconnect(self._first_draw_id)

        # Now do any initial draw
        self._init_draw()

        # Add our callback for stepping the animation and
        # actually start the event_source.
        self.event_source.add_callback(self._step)
        self.event_source.start()

    def _stop(self, *args):
        # On stop we disconnect all of our events.
        if self._blit:
            self._fig.canvas.mpl_disconnect(self._resize_id)
        self._fig.canvas.mpl_disconnect(self._close_id)
        self.event_source.remove_callback(self._step)
        self.event_source = None

    def save(self, filename, writer=None, fps=None, dpi=None, codec=None,
             bitrate=None, extra_args=None, metadata=None, extra_anim=None,
             savefig_kwargs=None, *, progress_callback=None):
        """
        Save the animation as a movie file by drawing every frame.

        Parameters
        ----------
        filename : str
            The output filename, e.g., :file:`mymovie.mp4`.

        writer : `MovieWriter` or str, default: :rc:`animation.writer`
            A `MovieWriter` instance to use or a key that identifies a
            class to use, such as 'ffmpeg'.

        fps : int, optional
            Movie frame rate (per second).  If not set, the frame rate from the
            animation's frame interval.

        dpi : float, default: :rc:`savefig.dpi`
            Controls the dots per inch for the movie frames.  Together with
            the figure's size in inches, this controls the size of the movie.

        codec : str, default: :rc:`animation.codec`.
            The video codec to use.  Not all codecs are supported by a given
            `MovieWriter`.

        bitrate : int, default: :rc:`animation.bitrate`
            The bitrate of the movie, in kilobits per second.  Higher values
            means higher quality movies, but increase the file size.  A value
            of -1 lets the underlying movie encoder select the bitrate.

        extra_args : list of str or None, optional
            Extra command-line arguments passed to the underlying movie encoder. These
            arguments are passed last to the encoder, just before the output filename.
            The default, None, means to use :rc:`animation.[name-of-encoder]_args` for
            the builtin writers.

        metadata : dict[str, str], default: {}
            Dictionary of keys and values for metadata to include in
            the output file. Some keys that may be of use include:
            title, artist, genre, subject, copyright, srcform, comment.

        extra_anim : list, default: []
            Additional `Animation` objects that should be included
            in the saved movie file. These need to be from the same
            `.Figure` instance. Also, animation frames will
            just be simply combined, so there should be a 1:1 correspondence
            between the frames from the different animations.

        savefig_kwargs : dict, default: {}
            Keyword arguments passed to each `~.Figure.savefig` call used to
            save the individual frames.

        progress_callback : function, optional
            A callback function that will be called for every frame to notify
            the saving progress. It must have the signature ::

                def func(current_frame: int, total_frames: int) -> Any

            where *current_frame* is the current frame number and *total_frames* is the
            total number of frames to be saved. *total_frames* is set to None, if the
            total number of frames cannot be determined. Return values may exist but are
            ignored.

            Example code to write the progress to stdout::

                progress_callback = lambda i, n: print(f'Saving frame {i}/{n}')

        Notes
        -----
        *fps*, *codec*, *bitrate*, *extra_args* and *metadata* are used to
        construct a `.MovieWriter` instance and can only be passed if
        *writer* is a string.  If they are passed as non-*None* and *writer*
        is a `.MovieWriter`, a `RuntimeError` will be raised.
        """

        all_anim = [self]
        if extra_anim is not None:
            all_anim.extend(anim for anim in extra_anim
                            if anim._fig is self._fig)

        # Disable "Animation was deleted without rendering" warning.
        for anim in all_anim:
            anim._draw_was_started = True

        if writer is None:
            writer = mpl.rcParams['animation.writer']
        elif (not isinstance(writer, str) and
              any(arg is not None
                  for arg in (fps, codec, bitrate, extra_args, metadata))):
            raise RuntimeError('Passing in values for arguments '
                               'fps, codec, bitrate, extra_args, or metadata '
                               'is not supported when writer is an existing '
                               'MovieWriter instance. These should instead be '
                               'passed as arguments when creating the '
                               'MovieWriter instance.')

        if savefig_kwargs is None:
            savefig_kwargs = {}
        else:
            # we are going to mutate this below
            savefig_kwargs = dict(savefig_kwargs)

        if fps is None and hasattr(self, '_interval'):
            # Convert interval in ms to frames per second
            fps = 1000. / self._interval

        # Reuse the savefig DPI for ours if none is given.
        dpi = mpl._val_or_rc(dpi, 'savefig.dpi')
        if dpi == 'figure':
            dpi = self._fig.dpi

        writer_kwargs = {}
        if codec is not None:
            writer_kwargs['codec'] = codec
        if bitrate is not None:
            writer_kwargs['bitrate'] = bitrate
        if extra_args is not None:
            writer_kwargs['extra_args'] = extra_args
        if metadata is not None:
            writer_kwargs['metadata'] = metadata

        # If we have the name of a writer, instantiate an instance of the
        # registered class.
        if isinstance(writer, str):
            try:
                writer_cls = writers[writer]
            except RuntimeError:  # Raised if not available.
                writer_cls = PillowWriter  # Always available.
                _log.warning("MovieWriter %s unavailable; using Pillow "
                             "instead.", writer)
            writer = writer_cls(fps, **writer_kwargs)
        _log.info('Animation.save using %s', type(writer))

        if 'bbox_inches' in savefig_kwargs:
            _log.warning("Warning: discarding the 'bbox_inches' argument in "
                         "'savefig_kwargs' as it may cause frame size "
                         "to vary, which is inappropriate for animation.")
            savefig_kwargs.pop('bbox_inches')

        # Create a new sequence of frames for saved data. This is different
        # from new_frame_seq() to give the ability to save 'live' generated
        # frame information to be saved later.
        # TODO: Right now, after closing the figure, saving a movie won't work
        # since GUI widgets are gone. Either need to remove extra code to
        # allow for this non-existent use case or find a way to make it work.

        def _pre_composite_to_white(color):
            r, g, b, a = mcolors.to_rgba(color)
            return a * np.array([r, g, b]) + 1 - a

        # canvas._is_saving = True makes the draw_event animation-starting
        # callback a no-op; canvas.manager = None prevents resizing the GUI
        # widget (both are likewise done in savefig()).
        with (writer.saving(self._fig, filename, dpi),
              cbook._setattr_cm(self._fig.canvas, _is_saving=True, manager=None)):
            if not writer._supports_transparency():
                facecolor = savefig_kwargs.get('facecolor',
                                               mpl.rcParams['savefig.facecolor'])
                if facecolor == 'auto':
                    facecolor = self._fig.get_facecolor()
                savefig_kwargs['facecolor'] = _pre_composite_to_white(facecolor)
                savefig_kwargs['transparent'] = False   # just to be safe!

            for anim in all_anim:
                anim._init_draw()  # Clear the initial frame
            frame_number = 0
            # TODO: Currently only FuncAnimation has a save_count
            #       attribute. Can we generalize this to all Animations?
            save_count_list = [getattr(a, '_save_count', None)
                               for a in all_anim]
            if None in save_count_list:
                total_frames = None
            else:
                total_frames = sum(save_count_list)
            for data in zip(*[a.new_saved_frame_seq() for a in all_anim]):
                for anim, d in zip(all_anim, data):
                    # TODO: See if turning off blit is really necessary
                    anim._draw_next_frame(d, blit=False)
                    if progress_callback is not None:
                        progress_callback(frame_number, total_frames)
                        frame_number += 1
                writer.grab_frame(**savefig_kwargs)

    def _step(self, *args):
        """
        Handler for getting events. By default, gets the next frame in the
        sequence and hands the data off to be drawn.
        """
        # Returns True to indicate that the event source should continue to
        # call _step, until the frame sequence reaches the end of iteration,
        # at which point False will be returned.
        try:
            framedata = next(self.frame_seq)
            self._draw_next_frame(framedata, self._blit)
            return True
        except StopIteration:
            return False

    def new_frame_seq(self):
        """Return a new sequence of frame information."""
        # Default implementation is just an iterator over self._framedata
        return iter(self._framedata)

    def new_saved_frame_seq(self):
        """Return a new sequence of saved/cached frame information."""
        # Default is the same as the regular frame sequence
        return self.new_frame_seq()

    def _draw_next_frame(self, framedata, blit):
        # Breaks down the drawing of the next frame into steps of pre- and
        # post- draw, as well as the drawing of the frame itself.
        self._pre_draw(framedata, blit)
        self._draw_frame(framedata)
        self._post_draw(framedata, blit)

    def _init_draw(self):
        # Initial draw to clear the frame. Also used by the blitting code
        # when a clean base is required.
        self._draw_was_started = True

    def _pre_draw(self, framedata, blit):
        # Perform any cleaning or whatnot before the drawing of the frame.
        # This default implementation allows blit to clear the frame.
        if blit:
            self._blit_clear(self._drawn_artists)

    def _draw_frame(self, framedata):
        # Performs actual drawing of the frame.
        raise NotImplementedError('Needs to be implemented by subclasses to'
                                  ' actually make an animation.')

    def _post_draw(self, framedata, blit):
        # After the frame is rendered, this handles the actual flushing of
        # the draw, which can be a direct draw_idle() or make use of the
        # blitting.
        if blit and self._drawn_artists:
            self._blit_draw(self._drawn_artists)
        else:
            self._fig.canvas.draw_idle()

    # The rest of the code in this class is to facilitate easy blitting
    def _blit_draw(self, artists):
        # Handles blitted drawing, which renders only the artists given instead
        # of the entire figure.
        updated_ax = {a.axes for a in artists}
        # Enumerate artists to cache Axes backgrounds. We do not draw
        # artists yet to not cache foreground from plots with shared Axes
        for ax in updated_ax:
            # If we haven't cached the background for the current view of this
            # Axes object, do so now. This might not always be reliable, but
            # it's an attempt to automate the process.
            cur_view = ax._get_view()
            view, bg = self._blit_cache.get(ax, (object(), None))
            if cur_view != view:
                self._blit_cache[ax] = (
                    cur_view, ax.figure.canvas.copy_from_bbox(ax.bbox))
        # Make a separate pass to draw foreground.
        for a in artists:
            a.axes.draw_artist(a)
        # After rendering all the needed artists, blit each Axes individually.
        for ax in updated_ax:
            ax.figure.canvas.blit(ax.bbox)

    def _blit_clear(self, artists):
        # Get a list of the Axes that need clearing from the artists that
        # have been drawn. Grab the appropriate saved background from the
        # cache and restore.
        axes = {a.axes for a in artists}
        for ax in axes:
            try:
                view, bg = self._blit_cache[ax]
            except KeyError:
                continue
            if ax._get_view() == view:
                ax.figure.canvas.restore_region(bg)
            else:
                self._blit_cache.pop(ax)

    def _setup_blit(self):
        # Setting up the blit requires: a cache of the background for the Axes
        self._blit_cache = dict()
        self._drawn_artists = []
        # _post_draw needs to be called first to initialize the renderer
        self._post_draw(None, self._blit)
        # Then we need to clear the Frame for the initial draw
        # This is typically handled in _on_resize because QT and Tk
        # emit a resize event on launch, but the macosx backend does not,
        # thus we force it here for everyone for consistency
        self._init_draw()
        # Connect to future resize events
        self._resize_id = self._fig.canvas.mpl_connect('resize_event',
                                                       self._on_resize)

    def _on_resize(self, event):
        # On resize, we need to disable the resize event handling so we don't
        # get too many events. Also stop the animation events, so that
        # we're paused. Reset the cache and re-init. Set up an event handler
        # to catch once the draw has actually taken place.
        self._fig.canvas.mpl_disconnect(self._resize_id)
        self.event_source.stop()
        self._blit_cache.clear()
        self._init_draw()
        self._resize_id = self._fig.canvas.mpl_connect('draw_event',
                                                       self._end_redraw)

    def _end_redraw(self, event):
        # Now that the redraw has happened, do the post draw flushing and
        # blit handling. Then re-enable all of the original events.
        self._post_draw(None, False)
        self.event_source.start()
        self._fig.canvas.mpl_disconnect(self._resize_id)
        self._resize_id = self._fig.canvas.mpl_connect('resize_event',
                                                       self._on_resize)

    def to_html5_video(self, embed_limit=None):
        """
        Convert the animation to an HTML5 ``<video>`` tag.

        This saves the animation as an h264 video, encoded in base64
        directly into the HTML5 video tag. This respects :rc:`animation.writer`
        and :rc:`animation.bitrate`. This also makes use of the
        *interval* to control the speed, and uses the *repeat*
        parameter to decide whether to loop.

        Parameters
        ----------
        embed_limit : float, optional
            Limit, in MB, of the returned animation. No animation is created
            if the limit is exceeded.
            Defaults to :rc:`animation.embed_limit` = 20.0.

        Returns
        -------
        str
            An HTML5 video tag with the animation embedded as base64 encoded
            h264 video.
            If the *embed_limit* is exceeded, this returns the string
            "Video too large to embed."
        """
        VIDEO_TAG = r'''<video {size} {options}>
  <source type="video/mp4" src="data:video/mp4;base64,{video}">
  Your browser does not support the video tag.
</video>'''
        # Cache the rendering of the video as HTML
        if not hasattr(self, '_base64_video'):
            # Save embed limit, which is given in MB
            embed_limit = mpl._val_or_rc(embed_limit, 'animation.embed_limit')

            # Convert from MB to bytes
            embed_limit *= 1024 * 1024

            # Can't open a NamedTemporaryFile twice on Windows, so use a
            # TemporaryDirectory instead.
            with TemporaryDirectory() as tmpdir:
                path = Path(tmpdir, "temp.m4v")
                # We create a writer manually so that we can get the
                # appropriate size for the tag
                Writer = writers[mpl.rcParams['animation.writer']]
                writer = Writer(codec='h264',
                                bitrate=mpl.rcParams['animation.bitrate'],
                                fps=1000. / self._interval)
                self.save(str(path), writer=writer)
                # Now open and base64 encode.
                vid64 = base64.encodebytes(path.read_bytes())

            vid_len = len(vid64)
            if vid_len >= embed_limit:
                _log.warning(
                    "Animation movie is %s bytes, exceeding the limit of %s. "
                    "If you're sure you want a large animation embedded, set "
                    "the animation.embed_limit rc parameter to a larger value "
                    "(in MB).", vid_len, embed_limit)
            else:
                self._base64_video = vid64.decode('ascii')
                self._video_size = 'width="{}" height="{}"'.format(
                        *writer.frame_size)

        # If we exceeded the size, this attribute won't exist
        if hasattr(self, '_base64_video'):
            # Default HTML5 options are to autoplay and display video controls
            options = ['controls', 'autoplay']

            # If we're set to repeat, make it loop
            if getattr(self, '_repeat', False):
                options.append('loop')

            return VIDEO_TAG.format(video=self._base64_video,
                                    size=self._video_size,
                                    options=' '.join(options))
        else:
            return 'Video too large to embed.'

    def to_jshtml(self, fps=None, embed_frames=True, default_mode=None):
        """
        Generate HTML representation of the animation.

        Parameters
        ----------
        fps : int, optional
            Movie frame rate (per second). If not set, the frame rate from
            the animation's frame interval.
        embed_frames : bool, optional
        default_mode : str, optional
            What to do when the animation ends. Must be one of ``{'loop',
            'once', 'reflect'}``. Defaults to ``'loop'`` if the *repeat*
            parameter is True, otherwise ``'once'``.

        Returns
        -------
        str
            An HTML representation of the animation embedded as a js object as
            produced with the `.HTMLWriter`.
        """
        if fps is None and hasattr(self, '_interval'):
            # Convert interval in ms to frames per second
            fps = 1000 / self._interval

        # If we're not given a default mode, choose one base on the value of
        # the _repeat attribute
        if default_mode is None:
            default_mode = 'loop' if getattr(self, '_repeat',
                                             False) else 'once'

        if not hasattr(self, "_html_representation"):
            # Can't open a NamedTemporaryFile twice on Windows, so use a
            # TemporaryDirectory instead.
            with TemporaryDirectory() as tmpdir:
                path = Path(tmpdir, "temp.html")
                writer = HTMLWriter(fps=fps,
                                    embed_frames=embed_frames,
                                    default_mode=default_mode)
                self.save(str(path), writer=writer)
                self._html_representation = path.read_text()

        return self._html_representation

    def _repr_html_(self):
        """IPython display hook for rendering."""
        fmt = mpl.rcParams['animation.html']
        if fmt == 'html5':
            return self.to_html5_video()
        elif fmt == 'jshtml':
            return self.to_jshtml()

    def pause(self):
        """Pause the animation."""
        self.event_source.stop()
        if self._blit:
            for artist in self._drawn_artists:
                artist.set_animated(False)

    def resume(self):
        """Resume the animation."""
        self.event_source.start()
        if self._blit:
            for artist in self._drawn_artists:
                artist.set_animated(True)


class TimedAnimation(Animation):
    """
    `Animation` subclass for time-based animation.

    A new frame is drawn every *interval* milliseconds.

    .. note::

        You must store the created Animation in a variable that lives as long
        as the animation should run. Otherwise, the Animation object will be
        garbage-collected and the animation stops.

    Parameters
    ----------
    fig : `~matplotlib.figure.Figure`
        The figure object used to get needed events, such as draw or resize.
    interval : int, default: 200
        Delay between frames in milliseconds.
    repeat_delay : int, default: 0
        The delay in milliseconds between consecutive animation runs, if
        *repeat* is True.
    repeat : bool, default: True
        Whether the animation repeats when the sequence of frames is completed.
    blit : bool, default: False
        Whether blitting is used to optimize drawing.
    """
    def __init__(self, fig, interval=200, repeat_delay=0, repeat=True,
                 event_source=None, *args, **kwargs):
        self._interval = interval
        # Undocumented support for repeat_delay = None as backcompat.
        self._repeat_delay = repeat_delay if repeat_delay is not None else 0
        self._repeat = repeat
        # If we're not given an event source, create a new timer. This permits
        # sharing timers between animation objects for syncing animations.
        if event_source is None:
            event_source = fig.canvas.new_timer(interval=self._interval)
        super().__init__(fig, event_source=event_source, *args, **kwargs)

    def _step(self, *args):
        """Handler for getting events."""
        # Extends the _step() method for the Animation class.  If
        # Animation._step signals that it reached the end and we want to
        # repeat, we refresh the frame sequence and return True. If
        # _repeat_delay is set, change the event_source's interval to our loop
        # delay and set the callback to one which will then set the interval
        # back.
        still_going = super()._step(*args)
        if not still_going:
            if self._repeat:
                # Restart the draw loop
                self._init_draw()
                self.frame_seq = self.new_frame_seq()
                self.event_source.interval = self._repeat_delay
                return True
            else:
                # We are done with the animation. Call pause to remove
                # animated flags from artists that were using blitting
                self.pause()
                if self._blit:
                    # Remove the resize callback if we were blitting
                    self._fig.canvas.mpl_disconnect(self._resize_id)
                self._fig.canvas.mpl_disconnect(self._close_id)
                self.event_source = None
                return False

        self.event_source.interval = self._interval
        return True


class ArtistAnimation(TimedAnimation):
    """
    `TimedAnimation` subclass that creates an animation by using a fixed
    set of `.Artist` objects.

    Before creating an instance, all plotting should have taken place
    and the relevant artists saved.

    .. note::

        You must store the created Animation in a variable that lives as long
        as the animation should run. Otherwise, the Animation object will be
        garbage-collected and the animation stops.

    Parameters
    ----------
    fig : `~matplotlib.figure.Figure`
        The figure object used to get needed events, such as draw or resize.
    artists : list
        Each list entry is a collection of `.Artist` objects that are made
        visible on the corresponding frame.  Other artists are made invisible.
    interval : int, default: 200
        Delay between frames in milliseconds.
    repeat_delay : int, default: 0
        The delay in milliseconds between consecutive animation runs, if
        *repeat* is True.
    repeat : bool, default: True
        Whether the animation repeats when the sequence of frames is completed.
    blit : bool, default: False
        Whether blitting is used to optimize drawing.
    """

    def __init__(self, fig, artists, *args, **kwargs):
        # Internal list of artists drawn in the most recent frame.
        self._drawn_artists = []

        # Use the list of artists as the framedata, which will be iterated
        # over by the machinery.
        self._framedata = artists
        super().__init__(fig, *args, **kwargs)

    def _init_draw(self):
        super()._init_draw()
        # Make all the artists involved in *any* frame invisible
        figs = set()
        for f in self.new_frame_seq():
            for artist in f:
                artist.set_visible(False)
                artist.set_animated(self._blit)
                # Assemble a list of unique figures that need flushing
                if artist.get_figure() not in figs:
                    figs.add(artist.get_figure())

        # Flush the needed figures
        for fig in figs:
            fig.canvas.draw_idle()

    def _pre_draw(self, framedata, blit):
        """Clears artists from the last frame."""
        if blit:
            # Let blit handle clearing
            self._blit_clear(self._drawn_artists)
        else:
            # Otherwise, make all the artists from the previous frame invisible
            for artist in self._drawn_artists:
                artist.set_visible(False)

    def _draw_frame(self, artists):
        # Save the artists that were passed in as framedata for the other
        # steps (esp. blitting) to use.
        self._drawn_artists = artists

        # Make all the artists from the current frame visible
        for artist in artists:
            artist.set_visible(True)


class FuncAnimation(TimedAnimation):
    """
    `TimedAnimation` subclass that makes an animation by repeatedly calling
    a function *func*.

    .. note::

        You must store the created Animation in a variable that lives as long
        as the animation should run. Otherwise, the Animation object will be
        garbage-collected and the animation stops.

    Parameters
    ----------
    fig : `~matplotlib.figure.Figure`
        The figure object used to get needed events, such as draw or resize.

    func : callable
        The function to call at each frame.  The first argument will
        be the next value in *frames*.   Any additional positional
        arguments can be supplied using `functools.partial` or via the *fargs*
        parameter.

        The required signature is::

            def func(frame, *fargs) -> iterable_of_artists

        It is often more convenient to provide the arguments using
        `functools.partial`. In this way it is also possible to pass keyword
        arguments. To pass a function with both positional and keyword
        arguments, set all arguments as keyword arguments, just leaving the
        *frame* argument unset::

            def func(frame, art, *, y=None):
                ...

            ani = FuncAnimation(fig, partial(func, art=ln, y='foo'))

        If ``blit == True``, *func* must return an iterable of all artists
        that were modified or created. This information is used by the blitting
        algorithm to determine which parts of the figure have to be updated.
        The return value is unused if ``blit == False`` and may be omitted in
        that case.

    frames : iterable, int, generator function, or None, optional
        Source of data to pass *func* and each frame of the animation

        - If an iterable, then simply use the values provided.  If the
          iterable has a length, it will override the *save_count* kwarg.

        - If an integer, then equivalent to passing ``range(frames)``

        - If a generator function, then must have the signature::

             def gen_function() -> obj

        - If *None*, then equivalent to passing ``itertools.count``.

        In all of these cases, the values in *frames* is simply passed through
        to the user-supplied *func* and thus can be of any type.

    init_func : callable, optional
        A function used to draw a clear frame. If not given, the results of
        drawing from the first item in the frames sequence will be used. This
        function will be called once before the first frame.

        The required signature is::

            def init_func() -> iterable_of_artists

        If ``blit == True``, *init_func* must return an iterable of artists
        to be re-drawn. This information is used by the blitting algorithm to
        determine which parts of the figure have to be updated.  The return
        value is unused if ``blit == False`` and may be omitted in that case.

    fargs : tuple or None, optional
        Additional arguments to pass to each call to *func*. Note: the use of
        `functools.partial` is preferred over *fargs*. See *func* for details.

    save_count : int, optional
        Fallback for the number of values from *frames* to cache. This is
        only used if the number of frames cannot be inferred from *frames*,
        i.e. when it's an iterator without length or a generator.

    interval : int, default: 200
        Delay between frames in milliseconds.

    repeat_delay : int, default: 0
        The delay in milliseconds between consecutive animation runs, if
        *repeat* is True.

    repeat : bool, default: True
        Whether the animation repeats when the sequence of frames is completed.

    blit : bool, default: False
        Whether blitting is used to optimize drawing.  Note: when using
        blitting, any animated artists will be drawn according to their zorder;
        however, they will be drawn on top of any previous artists, regardless
        of their zorder.

    cache_frame_data : bool, default: True
        Whether frame data is cached.  Disabling cache might be helpful when
        frames contain large objects.
    """
    def __init__(self, fig, func, frames=None, init_func=None, fargs=None,
                 save_count=None, *, cache_frame_data=True, **kwargs):
        if fargs:
            self._args = fargs
        else:
            self._args = ()
        self._func = func
        self._init_func = init_func

        # Amount of framedata to keep around for saving movies. This is only
        # used if we don't know how many frames there will be: in the case
        # of no generator or in the case of a callable.
        self._save_count = save_count
        # Set up a function that creates a new iterable when needed. If nothing
        # is passed in for frames, just use itertools.count, which will just
        # keep counting from 0. A callable passed in for frames is assumed to
        # be a generator. An iterable will be used as is, and anything else
        # will be treated as a number of frames.
        if frames is None:
            self._iter_gen = itertools.count
        elif callable(frames):
            self._iter_gen = frames
        elif np.iterable(frames):
            if kwargs.get('repeat', True):
                self._tee_from = frames
                def iter_frames(frames=frames):
                    this, self._tee_from = itertools.tee(self._tee_from, 2)
                    yield from this
                self._iter_gen = iter_frames
            else:
                self._iter_gen = lambda: iter(frames)
            if hasattr(frames, '__len__'):
                self._save_count = len(frames)
                if save_count is not None:
                    _api.warn_external(
                        f"You passed in an explicit {save_count=} "
                        "which is being ignored in favor of "
                        f"{len(frames)=}."
                    )
        else:
            self._iter_gen = lambda: iter(range(frames))
            self._save_count = frames
            if save_count is not None:
                _api.warn_external(
                    f"You passed in an explicit {save_count=} which is being "
                    f"ignored in favor of {frames=}."
                )
        if self._save_count is None and cache_frame_data:
            _api.warn_external(
                f"{frames=!r} which we can infer the length of, "
                "did not pass an explicit *save_count* "
                f"and passed {cache_frame_data=}.  To avoid a possibly "
                "unbounded cache, frame data caching has been disabled. "
                "To suppress this warning either pass "
                "`cache_frame_data=False` or `save_count=MAX_FRAMES`."
            )
            cache_frame_data = False

        self._cache_frame_data = cache_frame_data

        # Needs to be initialized so the draw functions work without checking
        self._save_seq = []

        super().__init__(fig, **kwargs)

        # Need to reset the saved seq, since right now it will contain data
        # for a single frame from init, which is not what we want.
        self._save_seq = []

    def new_frame_seq(self):
        # Use the generating function to generate a new frame sequence
        return self._iter_gen()

    def new_saved_frame_seq(self):
        # Generate an iterator for the sequence of saved data. If there are
        # no saved frames, generate a new frame sequence and take the first
        # save_count entries in it.
        if self._save_seq:
            # While iterating we are going to update _save_seq
            # so make a copy to safely iterate over
            self._old_saved_seq = list(self._save_seq)
            return iter(self._old_saved_seq)
        else:
            if self._save_count is None:
                frame_seq = self.new_frame_seq()

                def gen():
                    try:
                        while True:
                            yield next(frame_seq)
                    except StopIteration:
                        pass
                return gen()
            else:
                return itertools.islice(self.new_frame_seq(), self._save_count)

    def _init_draw(self):
        super()._init_draw()
        # Initialize the drawing either using the given init_func or by
        # calling the draw function with the first item of the frame sequence.
        # For blitting, the init_func should return a sequence of modified
        # artists.
        if self._init_func is None:
            try:
                frame_data = next(self.new_frame_seq())
            except StopIteration:
                # we can't start the iteration, it may have already been
                # exhausted by a previous save or just be 0 length.
                # warn and bail.
                warnings.warn(
                    "Can not start iterating the frames for the initial draw. "
                    "This can be caused by passing in a 0 length sequence "
                    "for *frames*.\n\n"
                    "If you passed *frames* as a generator "
                    "it may be exhausted due to a previous display or save."
                )
                return
            self._draw_frame(frame_data)
        else:
            self._drawn_artists = self._init_func()
            if self._blit:
                if self._drawn_artists is None:
                    raise RuntimeError('The init_func must return a '
                                       'sequence of Artist objects.')
                for a in self._drawn_artists:
                    a.set_animated(self._blit)
        self._save_seq = []

    def _draw_frame(self, framedata):
        if self._cache_frame_data:
            # Save the data for potential saving of movies.
            self._save_seq.append(framedata)
            self._save_seq = self._save_seq[-self._save_count:]

        # Call the func with framedata and args. If blitting is desired,
        # func needs to return a sequence of any artists that were modified.
        self._drawn_artists = self._func(framedata, *self._args)

        if self._blit:

            err = RuntimeError('The animation function must return a sequence '
                               'of Artist objects.')
            try:
                # check if a sequence
                iter(self._drawn_artists)
            except TypeError:
                raise err from None

            # check each item if it's artist
            for i in self._drawn_artists:
                if not isinstance(i, mpl.artist.Artist):
                    raise err

            self._drawn_artists = sorted(self._drawn_artists,
                                         key=lambda x: x.get_zorder())

            for a in self._drawn_artists:
                a.set_animated(self._blit)


def _validate_grabframe_kwargs(savefig_kwargs):
    if mpl.rcParams['savefig.bbox'] == 'tight':
        raise ValueError(
            f"{mpl.rcParams['savefig.bbox']=} must not be 'tight' as it "
            "may cause frame size to vary, which is inappropriate for animation."
        )
    for k in ('dpi', 'bbox_inches', 'format'):
        if k in savefig_kwargs:
            raise TypeError(
                f"grab_frame got an unexpected keyword argument {k!r}"
            )
