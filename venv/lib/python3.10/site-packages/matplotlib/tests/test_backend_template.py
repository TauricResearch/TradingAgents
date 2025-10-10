"""
Backend-loading machinery tests, using variations on the template backend.
"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import matplotlib as mpl
from matplotlib import pyplot as plt
from matplotlib.backends import backend_template
from matplotlib.backends.backend_template import (
    FigureCanvasTemplate, FigureManagerTemplate)


def test_load_template():
    mpl.use("template")
    assert type(plt.figure().canvas) == FigureCanvasTemplate


def test_load_old_api(monkeypatch):
    mpl_test_backend = SimpleNamespace(**vars(backend_template))
    mpl_test_backend.new_figure_manager = (
        lambda num, *args, FigureClass=mpl.figure.Figure, **kwargs:
        FigureManagerTemplate(
            FigureCanvasTemplate(FigureClass(*args, **kwargs)), num))
    monkeypatch.setitem(sys.modules, "mpl_test_backend", mpl_test_backend)
    mpl.use("module://mpl_test_backend")
    assert type(plt.figure().canvas) == FigureCanvasTemplate
    plt.draw_if_interactive()


def test_show(monkeypatch):
    mpl_test_backend = SimpleNamespace(**vars(backend_template))
    mock_show = MagicMock()
    monkeypatch.setattr(
        mpl_test_backend.FigureManagerTemplate, "pyplot_show", mock_show)
    monkeypatch.setitem(sys.modules, "mpl_test_backend", mpl_test_backend)
    mpl.use("module://mpl_test_backend")
    plt.show()
    mock_show.assert_called_with()


def test_show_old_global_api(monkeypatch):
    mpl_test_backend = SimpleNamespace(**vars(backend_template))
    mock_show = MagicMock()
    monkeypatch.setattr(mpl_test_backend, "show", mock_show, raising=False)
    monkeypatch.setitem(sys.modules, "mpl_test_backend", mpl_test_backend)
    mpl.use("module://mpl_test_backend")
    plt.show()
    mock_show.assert_called_with()


def test_load_case_sensitive(monkeypatch):
    mpl_test_backend = SimpleNamespace(**vars(backend_template))
    mock_show = MagicMock()
    monkeypatch.setattr(
        mpl_test_backend.FigureManagerTemplate, "pyplot_show", mock_show)
    monkeypatch.setitem(sys.modules, "mpl_Test_Backend", mpl_test_backend)
    mpl.use("module://mpl_Test_Backend")
    plt.show()
    mock_show.assert_called_with()
