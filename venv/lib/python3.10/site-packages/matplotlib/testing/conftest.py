import pytest
import sys
import matplotlib
from matplotlib import _api


def pytest_configure(config):
    # config is initialized here rather than in pytest.ini so that `pytest
    # --pyargs matplotlib` (which would not find pytest.ini) works.  The only
    # entries in pytest.ini set minversion (which is checked earlier),
    # testpaths/python_files, as they are required to properly find the tests
    for key, value in [
        ("markers", "flaky: (Provided by pytest-rerunfailures.)"),
        ("markers", "timeout: (Provided by pytest-timeout.)"),
        ("markers", "backend: Set alternate Matplotlib backend temporarily."),
        ("markers", "baseline_images: Compare output against references."),
        ("markers", "pytz: Tests that require pytz to be installed."),
        ("filterwarnings", "error"),
        ("filterwarnings",
         "ignore:.*The py23 module has been deprecated:DeprecationWarning"),
        ("filterwarnings",
         r"ignore:DynamicImporter.find_spec\(\) not found; "
         r"falling back to find_module\(\):ImportWarning"),
    ]:
        config.addinivalue_line(key, value)

    matplotlib.use('agg', force=True)
    matplotlib._called_from_pytest = True
    matplotlib._init_tests()


def pytest_unconfigure(config):
    matplotlib._called_from_pytest = False


@pytest.fixture(autouse=True)
def mpl_test_settings(request):
    from matplotlib.testing.decorators import _cleanup_cm

    with _cleanup_cm():

        backend = None
        backend_marker = request.node.get_closest_marker('backend')
        prev_backend = matplotlib.get_backend()
        if backend_marker is not None:
            assert len(backend_marker.args) == 1, \
                "Marker 'backend' must specify 1 backend."
            backend, = backend_marker.args
            skip_on_importerror = backend_marker.kwargs.get(
                'skip_on_importerror', False)

            # special case Qt backend importing to avoid conflicts
            if backend.lower().startswith('qt5'):
                if any(sys.modules.get(k) for k in ('PyQt4', 'PySide')):
                    pytest.skip('Qt4 binding already imported')

        matplotlib.testing.setup()
        with _api.suppress_matplotlib_deprecation_warning():
            if backend is not None:
                # This import must come after setup() so it doesn't load the
                # default backend prematurely.
                import matplotlib.pyplot as plt
                try:
                    plt.switch_backend(backend)
                except ImportError as exc:
                    # Should only occur for the cairo backend tests, if neither
                    # pycairo nor cairocffi are installed.
                    if 'cairo' in backend.lower() or skip_on_importerror:
                        pytest.skip("Failed to switch to backend "
                                    f"{backend} ({exc}).")
                    else:
                        raise
            # Default of cleanup and image_comparison too.
            matplotlib.style.use(["classic", "_classic_test_patch"])
        try:
            yield
        finally:
            if backend is not None:
                plt.close("all")
                matplotlib.use(prev_backend)


@pytest.fixture
def pd():
    """
    Fixture to import and configure pandas. Using this fixture, the test is skipped when
    pandas is not installed. Use this fixture instead of importing pandas in test files.

    Examples
    --------
    Request the pandas fixture by passing in ``pd`` as an argument to the test ::

        def test_matshow_pandas(pd):

            df = pd.DataFrame({'x':[1,2,3], 'y':[4,5,6]})
            im = plt.figure().subplots().matshow(df)
            np.testing.assert_array_equal(im.get_array(), df)
    """
    pd = pytest.importorskip('pandas')
    try:
        from pandas.plotting import (
            deregister_matplotlib_converters as deregister)
        deregister()
    except ImportError:
        pass
    return pd


@pytest.fixture
def xr():
    """
    Fixture to import xarray so that the test is skipped when xarray is not installed.
    Use this fixture instead of importing xrray in test files.

    Examples
    --------
    Request the xarray fixture by passing in ``xr`` as an argument to the test ::

        def test_imshow_xarray(xr):

            ds = xr.DataArray(np.random.randn(2, 3))
            im = plt.figure().subplots().imshow(ds)
            np.testing.assert_array_equal(im.get_array(), ds)
    """

    xr = pytest.importorskip('xarray')
    return xr


@pytest.fixture
def text_placeholders(monkeypatch):
    """
    Replace texts with placeholder rectangles.

    The rectangle size only depends on the font size and the number of characters. It is
    thus insensitive to font properties and rendering details. This should be used for
    tests that depend on text geometries but not the actual text rendering, e.g. layout
    tests.
    """
    from matplotlib.patches import Rectangle

    def patched_get_text_metrics_with_cache(renderer, text, fontprop, ismath, dpi):
        """
        Replace ``_get_text_metrics_with_cache`` with fixed results.

        The usual ``renderer.get_text_width_height_descent`` would depend on font
        metrics; instead the fixed results are based on font size and the length of the
        string only.
        """
        # While get_window_extent returns pixels and font size is in points, font size
        # includes ascenders and descenders. Leaving out this factor and setting
        # descent=0 ends up with a box that is relatively close to DejaVu Sans.
        height = fontprop.get_size()
        width = len(text) * height / 1.618  # Golden ratio for character size.
        descent = 0
        return width, height, descent

    def patched_text_draw(self, renderer):
        """
        Replace ``Text.draw`` with a fixed bounding box Rectangle.

        The bounding box corresponds to ``Text.get_window_extent``, which ultimately
        depends on the above patched ``_get_text_metrics_with_cache``.
        """
        if renderer is not None:
            self._renderer = renderer
        if not self.get_visible():
            return
        if self.get_text() == '':
            return
        bbox = self.get_window_extent()
        rect = Rectangle(bbox.p0, bbox.width, bbox.height,
                         facecolor=self.get_color(), edgecolor='none')
        rect.draw(renderer)

    monkeypatch.setattr('matplotlib.text._get_text_metrics_with_cache',
                        patched_get_text_metrics_with_cache)
    monkeypatch.setattr('matplotlib.text.Text.draw', patched_text_draw)
