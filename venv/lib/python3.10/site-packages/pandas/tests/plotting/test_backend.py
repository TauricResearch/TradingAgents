import sys
import types

import pytest

import pandas.util._test_decorators as td

import pandas


@pytest.fixture
def dummy_backend():
    db = types.ModuleType("pandas_dummy_backend")
    setattr(db, "plot", lambda *args, **kwargs: "used_dummy")
    return db


@pytest.fixture
def restore_backend():
    """Restore the plotting backend to matplotlib"""
    with pandas.option_context("plotting.backend", "matplotlib"):
        yield


def test_backend_is_not_module():
    msg = "Could not find plotting backend 'not_an_existing_module'."
    with pytest.raises(ValueError, match=msg):
        pandas.set_option("plotting.backend", "not_an_existing_module")

    assert pandas.options.plotting.backend == "matplotlib"


def test_backend_is_correct(monkeypatch, restore_backend, dummy_backend):
    monkeypatch.setitem(sys.modules, "pandas_dummy_backend", dummy_backend)

    pandas.set_option("plotting.backend", "pandas_dummy_backend")
    assert pandas.get_option("plotting.backend") == "pandas_dummy_backend"
    assert (
        pandas.plotting._core._get_plot_backend("pandas_dummy_backend") is dummy_backend
    )


def test_backend_can_be_set_in_plot_call(monkeypatch, restore_backend, dummy_backend):
    monkeypatch.setitem(sys.modules, "pandas_dummy_backend", dummy_backend)
    df = pandas.DataFrame([1, 2, 3])

    assert pandas.get_option("plotting.backend") == "matplotlib"
    assert df.plot(backend="pandas_dummy_backend") == "used_dummy"


def test_register_entrypoint(restore_backend, tmp_path, monkeypatch, dummy_backend):
    monkeypatch.syspath_prepend(tmp_path)
    monkeypatch.setitem(sys.modules, "pandas_dummy_backend", dummy_backend)

    dist_info = tmp_path / "my_backend-0.0.0.dist-info"
    dist_info.mkdir()
    # entry_point name should not match module name - otherwise pandas will
    # fall back to backend lookup by module name
    (dist_info / "entry_points.txt").write_bytes(
        b"[pandas_plotting_backends]\nmy_ep_backend = pandas_dummy_backend\n"
    )

    assert pandas.plotting._core._get_plot_backend("my_ep_backend") is dummy_backend

    with pandas.option_context("plotting.backend", "my_ep_backend"):
        assert pandas.plotting._core._get_plot_backend() is dummy_backend


def test_setting_backend_without_plot_raises(monkeypatch):
    # GH-28163
    module = types.ModuleType("pandas_plot_backend")
    monkeypatch.setitem(sys.modules, "pandas_plot_backend", module)

    assert pandas.options.plotting.backend == "matplotlib"
    with pytest.raises(
        ValueError, match="Could not find plotting backend 'pandas_plot_backend'."
    ):
        pandas.set_option("plotting.backend", "pandas_plot_backend")

    assert pandas.options.plotting.backend == "matplotlib"


@td.skip_if_installed("matplotlib")
def test_no_matplotlib_ok():
    msg = (
        'matplotlib is required for plotting when the default backend "matplotlib" is '
        "selected."
    )
    with pytest.raises(ImportError, match=msg):
        pandas.plotting._core._get_plot_backend("matplotlib")


def test_extra_kinds_ok(monkeypatch, restore_backend, dummy_backend):
    # https://github.com/pandas-dev/pandas/pull/28647
    monkeypatch.setitem(sys.modules, "pandas_dummy_backend", dummy_backend)
    pandas.set_option("plotting.backend", "pandas_dummy_backend")
    df = pandas.DataFrame({"A": [1, 2, 3]})
    df.plot(kind="not a real kind")
