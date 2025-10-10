from io import BytesIO
import ast
import os
import sys
import pickle
import pickletools

import numpy as np
import pytest

import matplotlib as mpl
from matplotlib import cm
from matplotlib.testing import subprocess_run_helper, is_ci_environment
from matplotlib.testing.decorators import check_figures_equal
from matplotlib.dates import rrulewrapper
from matplotlib.lines import VertexSelector
import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
import matplotlib.figure as mfigure
from mpl_toolkits.axes_grid1 import axes_divider, parasite_axes  # type: ignore[import]


def test_simple():
    fig = plt.figure()
    pickle.dump(fig, BytesIO(), pickle.HIGHEST_PROTOCOL)

    ax = plt.subplot(121)
    pickle.dump(ax, BytesIO(), pickle.HIGHEST_PROTOCOL)

    ax = plt.axes(projection='polar')
    plt.plot(np.arange(10), label='foobar')
    plt.legend()

    pickle.dump(ax, BytesIO(), pickle.HIGHEST_PROTOCOL)

#    ax = plt.subplot(121, projection='hammer')
#    pickle.dump(ax, BytesIO(), pickle.HIGHEST_PROTOCOL)

    plt.figure()
    plt.bar(x=np.arange(10), height=np.arange(10))
    pickle.dump(plt.gca(), BytesIO(), pickle.HIGHEST_PROTOCOL)

    fig = plt.figure()
    ax = plt.axes()
    plt.plot(np.arange(10))
    ax.set_yscale('log')
    pickle.dump(fig, BytesIO(), pickle.HIGHEST_PROTOCOL)


def _generate_complete_test_figure(fig_ref):
    fig_ref.set_size_inches((10, 6))
    plt.figure(fig_ref)

    plt.suptitle('Can you fit any more in a figure?')

    # make some arbitrary data
    x, y = np.arange(8), np.arange(10)
    data = u = v = np.linspace(0, 10, 80).reshape(10, 8)
    v = np.sin(v * -0.6)

    # Ensure lists also pickle correctly.
    plt.subplot(3, 3, 1)
    plt.plot(list(range(10)))
    plt.ylabel("hello")

    plt.subplot(3, 3, 2)
    plt.contourf(data, hatches=['//', 'ooo'])
    plt.colorbar()

    plt.subplot(3, 3, 3)
    plt.pcolormesh(data)

    plt.subplot(3, 3, 4)
    plt.imshow(data)
    plt.ylabel("hello\nworld!")

    plt.subplot(3, 3, 5)
    plt.pcolor(data)

    ax = plt.subplot(3, 3, 6)
    ax.set_xlim(0, 7)
    ax.set_ylim(0, 9)
    plt.streamplot(x, y, u, v)

    ax = plt.subplot(3, 3, 7)
    ax.set_xlim(0, 7)
    ax.set_ylim(0, 9)
    plt.quiver(x, y, u, v)

    plt.subplot(3, 3, 8)
    plt.scatter(x, x ** 2, label='$x^2$')
    plt.legend(loc='upper left')

    plt.subplot(3, 3, 9)
    plt.errorbar(x, x * -0.5, xerr=0.2, yerr=0.4, label='$-.5 x$')
    plt.legend(draggable=True)

    # Ensure subfigure parenting works.
    subfigs = fig_ref.subfigures(2)
    subfigs[0].subplots(1, 2)
    subfigs[1].subplots(1, 2)

    fig_ref.align_ylabels()  # Test handling of _align_label_groups Groupers.


@mpl.style.context("default")
@check_figures_equal(extensions=["png"])
def test_complete(fig_test, fig_ref):
    _generate_complete_test_figure(fig_ref)
    # plotting is done, now test its pickle-ability
    pkl = pickle.dumps(fig_ref, pickle.HIGHEST_PROTOCOL)
    # FigureCanvasAgg is picklable and GUI canvases are generally not, but there should
    # be no reference to the canvas in the pickle stream in either case.  In order to
    # keep the test independent of GUI toolkits, run it with Agg and check that there's
    # no reference to FigureCanvasAgg in the pickle stream.
    assert "FigureCanvasAgg" not in [arg for op, arg, pos in pickletools.genops(pkl)]
    loaded = pickle.loads(pkl)
    loaded.canvas.draw()

    fig_test.set_size_inches(loaded.get_size_inches())
    fig_test.figimage(loaded.canvas.renderer.buffer_rgba())

    plt.close(loaded)


def _pickle_load_subprocess():
    import os
    import pickle

    path = os.environ['PICKLE_FILE_PATH']

    with open(path, 'rb') as blob:
        fig = pickle.load(blob)

    print(str(pickle.dumps(fig)))


@mpl.style.context("default")
@check_figures_equal(extensions=['png'])
def test_pickle_load_from_subprocess(fig_test, fig_ref, tmp_path):
    _generate_complete_test_figure(fig_ref)

    fp = tmp_path / 'sinus.pickle'
    assert not fp.exists()

    with fp.open('wb') as file:
        pickle.dump(fig_ref, file, pickle.HIGHEST_PROTOCOL)
    assert fp.exists()

    proc = subprocess_run_helper(
        _pickle_load_subprocess,
        timeout=60,
        extra_env={
            "PICKLE_FILE_PATH": str(fp),
            "MPLBACKEND": "Agg",
            # subprocess_run_helper will set SOURCE_DATE_EPOCH=0, so for a dirty tree,
            # the version will have the date 19700101. As we aren't trying to test the
            # version compatibility warning, force setuptools-scm to use the same
            # version as us.
            "SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MATPLOTLIB": mpl.__version__,
        },
    )

    loaded_fig = pickle.loads(ast.literal_eval(proc.stdout))

    loaded_fig.canvas.draw()

    fig_test.set_size_inches(loaded_fig.get_size_inches())
    fig_test.figimage(loaded_fig.canvas.renderer.buffer_rgba())

    plt.close(loaded_fig)


def test_gcf():
    fig = plt.figure("a label")
    buf = BytesIO()
    pickle.dump(fig, buf, pickle.HIGHEST_PROTOCOL)
    plt.close("all")
    assert plt._pylab_helpers.Gcf.figs == {}  # No figures must be left.
    fig = pickle.loads(buf.getbuffer())
    assert plt._pylab_helpers.Gcf.figs != {}  # A manager is there again.
    assert fig.get_label() == "a label"


def test_no_pyplot():
    # tests pickle-ability of a figure not created with pyplot
    from matplotlib.backends.backend_pdf import FigureCanvasPdf
    fig = mfigure.Figure()
    _ = FigureCanvasPdf(fig)
    ax = fig.add_subplot(1, 1, 1)
    ax.plot([1, 2, 3], [1, 2, 3])
    pickle.dump(fig, BytesIO(), pickle.HIGHEST_PROTOCOL)


def test_renderer():
    from matplotlib.backends.backend_agg import RendererAgg
    renderer = RendererAgg(10, 20, 30)
    pickle.dump(renderer, BytesIO())


def test_image():
    # Prior to v1.4.0 the Image would cache data which was not picklable
    # once it had been drawn.
    from matplotlib.backends.backend_agg import new_figure_manager
    manager = new_figure_manager(1000)
    fig = manager.canvas.figure
    ax = fig.add_subplot(1, 1, 1)
    ax.imshow(np.arange(12).reshape(3, 4))
    manager.canvas.draw()
    pickle.dump(fig, BytesIO())


def test_polar():
    plt.subplot(polar=True)
    fig = plt.gcf()
    pf = pickle.dumps(fig)
    pickle.loads(pf)
    plt.draw()


class TransformBlob:
    def __init__(self):
        self.identity = mtransforms.IdentityTransform()
        self.identity2 = mtransforms.IdentityTransform()
        # Force use of the more complex composition.
        self.composite = mtransforms.CompositeGenericTransform(
            self.identity,
            self.identity2)
        # Check parent -> child links of TransformWrapper.
        self.wrapper = mtransforms.TransformWrapper(self.composite)
        # Check child -> parent links of TransformWrapper.
        self.composite2 = mtransforms.CompositeGenericTransform(
            self.wrapper,
            self.identity)


def test_transform():
    obj = TransformBlob()
    pf = pickle.dumps(obj)
    del obj

    obj = pickle.loads(pf)
    # Check parent -> child links of TransformWrapper.
    assert obj.wrapper._child == obj.composite
    # Check child -> parent links of TransformWrapper.
    assert [v() for v in obj.wrapper._parents.values()] == [obj.composite2]
    # Check input and output dimensions are set as expected.
    assert obj.wrapper.input_dims == obj.composite.input_dims
    assert obj.wrapper.output_dims == obj.composite.output_dims


def test_rrulewrapper():
    r = rrulewrapper(2)
    try:
        pickle.loads(pickle.dumps(r))
    except RecursionError:
        print('rrulewrapper pickling test failed')
        raise


def test_shared():
    fig, axs = plt.subplots(2, sharex=True)
    fig = pickle.loads(pickle.dumps(fig))
    fig.axes[0].set_xlim(10, 20)
    assert fig.axes[1].get_xlim() == (10, 20)


def test_inset_and_secondary():
    fig, ax = plt.subplots()
    ax.inset_axes([.1, .1, .3, .3])
    ax.secondary_xaxis("top", functions=(np.square, np.sqrt))
    pickle.loads(pickle.dumps(fig))


@pytest.mark.parametrize("cmap", cm._colormaps.values())
def test_cmap(cmap):
    pickle.dumps(cmap)


def test_unpickle_canvas():
    fig = mfigure.Figure()
    assert fig.canvas is not None
    out = BytesIO()
    pickle.dump(fig, out)
    out.seek(0)
    fig2 = pickle.load(out)
    assert fig2.canvas is not None


def test_mpl_toolkits():
    ax = parasite_axes.host_axes([0, 0, 1, 1])
    axes_divider.make_axes_area_auto_adjustable(ax)
    assert type(pickle.loads(pickle.dumps(ax))) == parasite_axes.HostAxes


def test_standard_norm():
    assert type(pickle.loads(pickle.dumps(mpl.colors.LogNorm()))) \
        == mpl.colors.LogNorm


def test_dynamic_norm():
    logit_norm_instance = mpl.colors.make_norm_from_scale(
        mpl.scale.LogitScale, mpl.colors.Normalize)()
    assert type(pickle.loads(pickle.dumps(logit_norm_instance))) \
        == type(logit_norm_instance)


def test_vertexselector():
    line, = plt.plot([0, 1], picker=True)
    pickle.loads(pickle.dumps(VertexSelector(line)))


def test_cycler():
    ax = plt.figure().add_subplot()
    ax.set_prop_cycle(c=["c", "m", "y", "k"])
    ax.plot([1, 2])
    ax = pickle.loads(pickle.dumps(ax))
    l, = ax.plot([3, 4])
    assert l.get_color() == "m"


# Run under an interactive backend to test that we don't try to pickle the
# (interactive and non-picklable) canvas.
def _test_axeswidget_interactive():
    ax = plt.figure().add_subplot()
    pickle.dumps(mpl.widgets.Button(ax, "button"))


@pytest.mark.xfail(  # https://github.com/actions/setup-python/issues/649
        ('TF_BUILD' in os.environ or 'GITHUB_ACTION' in os.environ) and
        sys.platform == 'darwin' and sys.version_info[:2] < (3, 11),
        reason='Tk version mismatch on Azure macOS CI'
    )
def test_axeswidget_interactive():
    subprocess_run_helper(
        _test_axeswidget_interactive,
        timeout=120 if is_ci_environment() else 20,
        extra_env={'MPLBACKEND': 'tkagg'}
    )
