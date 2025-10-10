import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import weakref

import numpy as np
import pytest

import matplotlib as mpl
from matplotlib import pyplot as plt
from matplotlib import animation
from matplotlib.animation import PillowWriter
from matplotlib.testing.decorators import check_figures_equal


@pytest.fixture()
def anim(request):
    """Create a simple animation (with options)."""
    fig, ax = plt.subplots()
    line, = ax.plot([], [])

    ax.set_xlim(0, 10)
    ax.set_ylim(-1, 1)

    def init():
        line.set_data([], [])
        return line,

    def animate(i):
        x = np.linspace(0, 10, 100)
        y = np.sin(x + i)
        line.set_data(x, y)
        return line,

    # "klass" can be passed to determine the class returned by the fixture
    kwargs = dict(getattr(request, 'param', {}))  # make a copy
    klass = kwargs.pop('klass', animation.FuncAnimation)
    if 'frames' not in kwargs:
        kwargs['frames'] = 5
    return klass(fig=fig, func=animate, init_func=init, **kwargs)


class NullMovieWriter(animation.AbstractMovieWriter):
    """
    A minimal MovieWriter.  It doesn't actually write anything.
    It just saves the arguments that were given to the setup() and
    grab_frame() methods as attributes, and counts how many times
    grab_frame() is called.

    This class doesn't have an __init__ method with the appropriate
    signature, and it doesn't define an isAvailable() method, so
    it cannot be added to the 'writers' registry.
    """

    def setup(self, fig, outfile, dpi, *args):
        self.fig = fig
        self.outfile = outfile
        self.dpi = dpi
        self.args = args
        self._count = 0

    def grab_frame(self, **savefig_kwargs):
        from matplotlib.animation import _validate_grabframe_kwargs
        _validate_grabframe_kwargs(savefig_kwargs)
        self.savefig_kwargs = savefig_kwargs
        self._count += 1

    def finish(self):
        pass


def test_null_movie_writer(anim):
    # Test running an animation with NullMovieWriter.
    plt.rcParams["savefig.facecolor"] = "auto"
    filename = "unused.null"
    dpi = 50
    savefig_kwargs = dict(foo=0)
    writer = NullMovieWriter()

    anim.save(filename, dpi=dpi, writer=writer,
              savefig_kwargs=savefig_kwargs)

    assert writer.fig == plt.figure(1)  # The figure used by anim fixture
    assert writer.outfile == filename
    assert writer.dpi == dpi
    assert writer.args == ()
    # we enrich the savefig kwargs to ensure we composite transparent
    # output to an opaque background
    for k, v in savefig_kwargs.items():
        assert writer.savefig_kwargs[k] == v
    assert writer._count == anim._save_count


@pytest.mark.parametrize('anim', [dict(klass=dict)], indirect=['anim'])
def test_animation_delete(anim):
    if platform.python_implementation() == 'PyPy':
        # Something in the test setup fixture lingers around into the test and
        # breaks pytest.warns on PyPy. This garbage collection fixes it.
        # https://foss.heptapod.net/pypy/pypy/-/issues/3536
        np.testing.break_cycles()
    anim = animation.FuncAnimation(**anim)
    with pytest.warns(Warning, match='Animation was deleted'):
        del anim
        np.testing.break_cycles()


def test_movie_writer_dpi_default():
    class DummyMovieWriter(animation.MovieWriter):
        def _run(self):
            pass

    # Test setting up movie writer with figure.dpi default.
    fig = plt.figure()

    filename = "unused.null"
    fps = 5
    codec = "unused"
    bitrate = 1
    extra_args = ["unused"]

    writer = DummyMovieWriter(fps, codec, bitrate, extra_args)
    writer.setup(fig, filename)
    assert writer.dpi == fig.dpi


@animation.writers.register('null')
class RegisteredNullMovieWriter(NullMovieWriter):

    # To be able to add NullMovieWriter to the 'writers' registry,
    # we must define an __init__ method with a specific signature,
    # and we must define the class method isAvailable().
    # (These methods are not actually required to use an instance
    # of this class as the 'writer' argument of Animation.save().)

    def __init__(self, fps=None, codec=None, bitrate=None,
                 extra_args=None, metadata=None):
        pass

    @classmethod
    def isAvailable(cls):
        return True


WRITER_OUTPUT = [
    ('ffmpeg', 'movie.mp4'),
    ('ffmpeg_file', 'movie.mp4'),
    ('imagemagick', 'movie.gif'),
    ('imagemagick_file', 'movie.gif'),
    ('pillow', 'movie.gif'),
    ('html', 'movie.html'),
    ('null', 'movie.null')
]


def gen_writers():
    for writer, output in WRITER_OUTPUT:
        if not animation.writers.is_available(writer):
            mark = pytest.mark.skip(
                f"writer '{writer}' not available on this system")
            yield pytest.param(writer, None, output, marks=[mark])
            yield pytest.param(writer, None, Path(output), marks=[mark])
            continue

        writer_class = animation.writers[writer]
        for frame_format in getattr(writer_class, 'supported_formats', [None]):
            yield writer, frame_format, output
            yield writer, frame_format, Path(output)


# Smoke test for saving animations.  In the future, we should probably
# design more sophisticated tests which compare resulting frames a-la
# matplotlib.testing.image_comparison
@pytest.mark.parametrize('writer, frame_format, output', gen_writers())
@pytest.mark.parametrize('anim', [dict(klass=dict)], indirect=['anim'])
def test_save_animation_smoketest(tmpdir, writer, frame_format, output, anim):
    if frame_format is not None:
        plt.rcParams["animation.frame_format"] = frame_format
    anim = animation.FuncAnimation(**anim)
    dpi = None
    codec = None
    if writer == 'ffmpeg':
        # Issue #8253
        anim._fig.set_size_inches((10.85, 9.21))
        dpi = 100.
        codec = 'h264'

    # Use temporary directory for the file-based writers, which produce a file
    # per frame with known names.
    with tmpdir.as_cwd():
        anim.save(output, fps=30, writer=writer, bitrate=500, dpi=dpi,
                  codec=codec)

    del anim


@pytest.mark.parametrize('writer, frame_format, output', gen_writers())
def test_grabframe(tmpdir, writer, frame_format, output):
    WriterClass = animation.writers[writer]

    if frame_format is not None:
        plt.rcParams["animation.frame_format"] = frame_format

    fig, ax = plt.subplots()

    dpi = None
    codec = None
    if writer == 'ffmpeg':
        # Issue #8253
        fig.set_size_inches((10.85, 9.21))
        dpi = 100.
        codec = 'h264'

    test_writer = WriterClass()
    # Use temporary directory for the file-based writers, which produce a file
    # per frame with known names.
    with tmpdir.as_cwd():
        with test_writer.saving(fig, output, dpi):
            # smoke test it works
            test_writer.grab_frame()
            for k in {'dpi', 'bbox_inches', 'format'}:
                with pytest.raises(
                        TypeError,
                        match=f"grab_frame got an unexpected keyword argument {k!r}"
                ):
                    test_writer.grab_frame(**{k: object()})


@pytest.mark.parametrize('writer', [
    pytest.param(
        'ffmpeg', marks=pytest.mark.skipif(
            not animation.FFMpegWriter.isAvailable(),
            reason='Requires FFMpeg')),
    pytest.param(
        'imagemagick', marks=pytest.mark.skipif(
            not animation.ImageMagickWriter.isAvailable(),
            reason='Requires ImageMagick')),
])
@pytest.mark.parametrize('html, want', [
    ('none', None),
    ('html5', '<video width'),
    ('jshtml', '<script ')
])
@pytest.mark.parametrize('anim', [dict(klass=dict)], indirect=['anim'])
def test_animation_repr_html(writer, html, want, anim):
    if platform.python_implementation() == 'PyPy':
        # Something in the test setup fixture lingers around into the test and
        # breaks pytest.warns on PyPy. This garbage collection fixes it.
        # https://foss.heptapod.net/pypy/pypy/-/issues/3536
        np.testing.break_cycles()
    if (writer == 'imagemagick' and html == 'html5'
            # ImageMagick delegates to ffmpeg for this format.
            and not animation.FFMpegWriter.isAvailable()):
        pytest.skip('Requires FFMpeg')
    # create here rather than in the fixture otherwise we get __del__ warnings
    # about producing no output
    anim = animation.FuncAnimation(**anim)
    with plt.rc_context({'animation.writer': writer,
                         'animation.html': html}):
        html = anim._repr_html_()
    if want is None:
        assert html is None
        with pytest.warns(UserWarning):
            del anim  # Animation was never run, so will warn on cleanup.
            np.testing.break_cycles()
    else:
        assert want in html


@pytest.mark.parametrize(
    'anim',
    [{'save_count': 10, 'frames': iter(range(5))}],
    indirect=['anim']
)
def test_no_length_frames(anim):
    anim.save('unused.null', writer=NullMovieWriter())


def test_movie_writer_registry():
    assert len(animation.writers._registered) > 0
    mpl.rcParams['animation.ffmpeg_path'] = "not_available_ever_xxxx"
    assert not animation.writers.is_available("ffmpeg")
    # something guaranteed to be available in path and exits immediately
    bin = "true" if sys.platform != 'win32' else "where"
    mpl.rcParams['animation.ffmpeg_path'] = bin
    assert animation.writers.is_available("ffmpeg")


@pytest.mark.parametrize(
    "method_name",
    [pytest.param("to_html5_video", marks=pytest.mark.skipif(
        not animation.writers.is_available(mpl.rcParams["animation.writer"]),
        reason="animation writer not installed")),
     "to_jshtml"])
@pytest.mark.parametrize('anim', [dict(frames=1)], indirect=['anim'])
def test_embed_limit(method_name, caplog, tmpdir, anim):
    caplog.set_level("WARNING")
    with tmpdir.as_cwd():
        with mpl.rc_context({"animation.embed_limit": 1e-6}):  # ~1 byte.
            getattr(anim, method_name)()
    assert len(caplog.records) == 1
    record, = caplog.records
    assert (record.name == "matplotlib.animation"
            and record.levelname == "WARNING")


@pytest.mark.parametrize(
    "method_name",
    [pytest.param("to_html5_video", marks=pytest.mark.skipif(
        not animation.writers.is_available(mpl.rcParams["animation.writer"]),
        reason="animation writer not installed")),
     "to_jshtml"])
@pytest.mark.parametrize('anim', [dict(frames=1)], indirect=['anim'])
def test_cleanup_temporaries(method_name, tmpdir, anim):
    with tmpdir.as_cwd():
        getattr(anim, method_name)()
        assert list(Path(str(tmpdir)).iterdir()) == []


@pytest.mark.skipif(shutil.which("/bin/sh") is None, reason="requires a POSIX OS")
def test_failing_ffmpeg(tmpdir, monkeypatch, anim):
    """
    Test that we correctly raise a CalledProcessError when ffmpeg fails.

    To do so, mock ffmpeg using a simple executable shell script that
    succeeds when called with no arguments (so that it gets registered by
    `isAvailable`), but fails otherwise, and add it to the $PATH.
    """
    with tmpdir.as_cwd():
        monkeypatch.setenv("PATH", ".:" + os.environ["PATH"])
        exe_path = Path(str(tmpdir), "ffmpeg")
        exe_path.write_bytes(b"#!/bin/sh\n[[ $@ -eq 0 ]]\n")
        os.chmod(exe_path, 0o755)
        with pytest.raises(subprocess.CalledProcessError):
            anim.save("test.mpeg")


@pytest.mark.parametrize("cache_frame_data", [False, True])
def test_funcanimation_cache_frame_data(cache_frame_data):
    fig, ax = plt.subplots()
    line, = ax.plot([], [])

    class Frame(dict):
        # this subclassing enables to use weakref.ref()
        pass

    def init():
        line.set_data([], [])
        return line,

    def animate(frame):
        line.set_data(frame['x'], frame['y'])
        return line,

    frames_generated = []

    def frames_generator():
        for _ in range(5):
            x = np.linspace(0, 10, 100)
            y = np.random.rand(100)

            frame = Frame(x=x, y=y)

            # collect weak references to frames
            # to validate their references later
            frames_generated.append(weakref.ref(frame))

            yield frame

    MAX_FRAMES = 100
    anim = animation.FuncAnimation(fig, animate, init_func=init,
                                   frames=frames_generator,
                                   cache_frame_data=cache_frame_data,
                                   save_count=MAX_FRAMES)

    writer = NullMovieWriter()
    anim.save('unused.null', writer=writer)
    assert len(frames_generated) == 5
    np.testing.break_cycles()
    for f in frames_generated:
        # If cache_frame_data is True, then the weakref should be alive;
        # if cache_frame_data is False, then the weakref should be dead (None).
        assert (f() is None) != cache_frame_data


@pytest.mark.parametrize('return_value', [
    # User forgot to return (returns None).
    None,
    # User returned a string.
    'string',
    # User returned an int.
    1,
    # User returns a sequence of other objects, e.g., string instead of Artist.
    ('string', ),
    # User forgot to return a sequence (handled in `animate` below.)
    'artist',
])
def test_draw_frame(return_value):
    # test _draw_frame method

    fig, ax = plt.subplots()
    line, = ax.plot([])

    def animate(i):
        # general update func
        line.set_data([0, 1], [0, i])
        if return_value == 'artist':
            # *not* a sequence
            return line
        else:
            return return_value

    with pytest.raises(RuntimeError):
        animation.FuncAnimation(
            fig, animate, blit=True, cache_frame_data=False
        )


def test_exhausted_animation(tmpdir):
    fig, ax = plt.subplots()

    def update(frame):
        return []

    anim = animation.FuncAnimation(
        fig, update, frames=iter(range(10)), repeat=False,
        cache_frame_data=False
    )

    with tmpdir.as_cwd():
        anim.save("test.gif", writer='pillow')

    with pytest.warns(UserWarning, match="exhausted"):
        anim._start()


def test_no_frame_warning(tmpdir):
    fig, ax = plt.subplots()

    def update(frame):
        return []

    anim = animation.FuncAnimation(
        fig, update, frames=[], repeat=False,
        cache_frame_data=False
    )

    with pytest.warns(UserWarning, match="exhausted"):
        anim._start()


@check_figures_equal(extensions=["png"])
def test_animation_frame(tmpdir, fig_test, fig_ref):
    # Test the expected image after iterating through a few frames
    # we save the animation to get the iteration because we are not
    # in an interactive framework.
    ax = fig_test.add_subplot()
    ax.set_xlim(0, 2 * np.pi)
    ax.set_ylim(-1, 1)
    x = np.linspace(0, 2 * np.pi, 100)
    line, = ax.plot([], [])

    def init():
        line.set_data([], [])
        return line,

    def animate(i):
        line.set_data(x, np.sin(x + i / 100))
        return line,

    anim = animation.FuncAnimation(
        fig_test, animate, init_func=init, frames=5,
        blit=True, repeat=False)
    with tmpdir.as_cwd():
        anim.save("test.gif")

    # Reference figure without animation
    ax = fig_ref.add_subplot()
    ax.set_xlim(0, 2 * np.pi)
    ax.set_ylim(-1, 1)

    # 5th frame's data
    ax.plot(x, np.sin(x + 4 / 100))


@pytest.mark.parametrize('anim', [dict(klass=dict)], indirect=['anim'])
def test_save_count_override_warnings_has_length(anim):

    save_count = 5
    frames = list(range(2))
    match_target = (
        f'You passed in an explicit {save_count=} '
        "which is being ignored in favor of "
        f"{len(frames)=}."
    )

    with pytest.warns(UserWarning, match=re.escape(match_target)):
        anim = animation.FuncAnimation(
            **{**anim, 'frames': frames, 'save_count': save_count}
        )
    assert anim._save_count == len(frames)
    anim._init_draw()


@pytest.mark.parametrize('anim', [dict(klass=dict)], indirect=['anim'])
def test_save_count_override_warnings_scaler(anim):
    save_count = 5
    frames = 7
    match_target = (
        f'You passed in an explicit {save_count=} ' +
        "which is being ignored in favor of " +
        f"{frames=}."
    )

    with pytest.warns(UserWarning, match=re.escape(match_target)):
        anim = animation.FuncAnimation(
            **{**anim, 'frames': frames, 'save_count': save_count}
        )

    assert anim._save_count == frames
    anim._init_draw()


@pytest.mark.parametrize('anim', [dict(klass=dict)], indirect=['anim'])
def test_disable_cache_warning(anim):
    cache_frame_data = True
    frames = iter(range(5))
    match_target = (
        f"{frames=!r} which we can infer the length of, "
        "did not pass an explicit *save_count* "
        f"and passed {cache_frame_data=}.  To avoid a possibly "
        "unbounded cache, frame data caching has been disabled. "
        "To suppress this warning either pass "
        "`cache_frame_data=False` or `save_count=MAX_FRAMES`."
    )
    with pytest.warns(UserWarning, match=re.escape(match_target)):
        anim = animation.FuncAnimation(
            **{**anim, 'cache_frame_data': cache_frame_data, 'frames': frames}
        )
    assert anim._cache_frame_data is False
    anim._init_draw()


def test_movie_writer_invalid_path(anim):
    if sys.platform == "win32":
        match_str = r"\[WinError 3] .*'\\\\foo\\\\bar\\\\aardvark'"
    else:
        match_str = r"\[Errno 2] .*'/foo"
    with pytest.raises(FileNotFoundError, match=match_str):
        anim.save("/foo/bar/aardvark/thiscannotreallyexist.mp4",
                  writer=animation.FFMpegFileWriter())


def test_animation_with_transparency():
    """Test animation exhaustion with transparency using PillowWriter directly"""
    fig, ax = plt.subplots()
    rect = plt.Rectangle((0, 0), 1, 1, color='red', alpha=0.5)
    ax.add_patch(rect)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    writer = PillowWriter(fps=30)
    writer.setup(fig, 'unused.gif', dpi=100)
    writer.grab_frame(transparent=True)
    frame = writer._frames[-1]
    # Check that the alpha channel is not 255, so frame has transparency
    assert frame.getextrema()[3][0] < 255
    plt.close(fig)
