from collections.abc import Sequence
from typing import Any

import pytest

import matplotlib as mpl
from matplotlib.backends import BackendFilter, backend_registry


@pytest.fixture
def clear_backend_registry():
    # Fixture that clears the singleton backend_registry before and after use
    # so that the test state remains isolated.
    backend_registry._clear()
    yield
    backend_registry._clear()


def has_duplicates(seq: Sequence[Any]) -> bool:
    return len(seq) > len(set(seq))


@pytest.mark.parametrize(
    'framework,expected',
    [
        ('qt', 'qtagg'),
        ('gtk3', 'gtk3agg'),
        ('gtk4', 'gtk4agg'),
        ('wx', 'wxagg'),
        ('tk', 'tkagg'),
        ('macosx', 'macosx'),
        ('headless', 'agg'),
        ('does not exist', None),
    ]
)
def test_backend_for_gui_framework(framework, expected):
    assert backend_registry.backend_for_gui_framework(framework) == expected


def test_list_builtin():
    backends = backend_registry.list_builtin()
    assert not has_duplicates(backends)
    # Compare using sets as order is not important
    assert {*backends} == {
        'gtk3agg', 'gtk3cairo', 'gtk4agg', 'gtk4cairo', 'macosx', 'nbagg', 'notebook',
        'qtagg', 'qtcairo', 'qt5agg', 'qt5cairo', 'tkagg',
        'tkcairo', 'webagg', 'wx', 'wxagg', 'wxcairo', 'agg', 'cairo', 'pdf', 'pgf',
        'ps', 'svg', 'template',
    }


@pytest.mark.parametrize(
    'filter,expected',
    [
        (BackendFilter.INTERACTIVE,
         ['gtk3agg', 'gtk3cairo', 'gtk4agg', 'gtk4cairo', 'macosx', 'nbagg', 'notebook',
          'qtagg', 'qtcairo', 'qt5agg', 'qt5cairo', 'tkagg',
          'tkcairo', 'webagg', 'wx', 'wxagg', 'wxcairo']),
        (BackendFilter.NON_INTERACTIVE,
         ['agg', 'cairo', 'pdf', 'pgf', 'ps', 'svg', 'template']),
    ]
)
def test_list_builtin_with_filter(filter, expected):
    backends = backend_registry.list_builtin(filter)
    assert not has_duplicates(backends)
    # Compare using sets as order is not important
    assert {*backends} == {*expected}


def test_list_gui_frameworks():
    frameworks = backend_registry.list_gui_frameworks()
    assert not has_duplicates(frameworks)
    # Compare using sets as order is not important
    assert {*frameworks} == {
        "gtk3", "gtk4", "macosx", "qt", "qt5", "qt6", "tk", "wx",
    }


@pytest.mark.parametrize("backend, is_valid", [
    ("agg", True),
    ("QtAgg", True),
    ("module://anything", True),
    ("made-up-name", False),
])
def test_is_valid_backend(backend, is_valid):
    assert backend_registry.is_valid_backend(backend) == is_valid


@pytest.mark.parametrize("backend, normalized", [
    ("agg", "matplotlib.backends.backend_agg"),
    ("QtAgg", "matplotlib.backends.backend_qtagg"),
    ("module://Anything", "Anything"),
])
def test_backend_normalization(backend, normalized):
    assert backend_registry._backend_module_name(backend) == normalized


def test_deprecated_rcsetup_attributes():
    match = "was deprecated in Matplotlib 3.9"
    with pytest.warns(mpl.MatplotlibDeprecationWarning, match=match):
        mpl.rcsetup.interactive_bk
    with pytest.warns(mpl.MatplotlibDeprecationWarning, match=match):
        mpl.rcsetup.non_interactive_bk
    with pytest.warns(mpl.MatplotlibDeprecationWarning, match=match):
        mpl.rcsetup.all_backends


def test_entry_points_inline():
    pytest.importorskip('matplotlib_inline')
    backends = backend_registry.list_all()
    assert 'inline' in backends


def test_entry_points_ipympl():
    pytest.importorskip('ipympl')
    backends = backend_registry.list_all()
    assert 'ipympl' in backends
    assert 'widget' in backends


def test_entry_point_name_shadows_builtin(clear_backend_registry):
    with pytest.raises(RuntimeError):
        backend_registry._validate_and_store_entry_points(
            [('qtagg', 'module1')])


def test_entry_point_name_duplicate(clear_backend_registry):
    with pytest.raises(RuntimeError):
        backend_registry._validate_and_store_entry_points(
            [('some_name', 'module1'), ('some_name', 'module2')])


def test_entry_point_identical(clear_backend_registry):
    # Issue https://github.com/matplotlib/matplotlib/issues/28367
    # Multiple entry points with the same name and value (value is the module)
    # are acceptable.
    n = len(backend_registry._name_to_module)
    backend_registry._validate_and_store_entry_points(
        [('some_name', 'some.module'), ('some_name', 'some.module')])
    assert len(backend_registry._name_to_module) == n+1
    assert backend_registry._name_to_module['some_name'] == 'module://some.module'


def test_entry_point_name_is_module(clear_backend_registry):
    with pytest.raises(RuntimeError):
        backend_registry._validate_and_store_entry_points(
            [('module://backend.something', 'module1')])


@pytest.mark.parametrize('backend', [
    'agg',
    'module://matplotlib.backends.backend_agg',
])
def test_load_entry_points_only_if_needed(clear_backend_registry, backend):
    assert not backend_registry._loaded_entry_points
    check = backend_registry.resolve_backend(backend)
    assert check == (backend, None)
    assert not backend_registry._loaded_entry_points
    backend_registry.list_all()  # Force load of entry points
    assert backend_registry._loaded_entry_points


@pytest.mark.parametrize(
    'gui_or_backend, expected_backend, expected_gui',
    [
        ('agg', 'agg', None),
        ('qt', 'qtagg', 'qt'),
        ('TkCairo', 'tkcairo', 'tk'),
    ]
)
def test_resolve_gui_or_backend(gui_or_backend, expected_backend, expected_gui):
    backend, gui = backend_registry.resolve_gui_or_backend(gui_or_backend)
    assert backend == expected_backend
    assert gui == expected_gui


def test_resolve_gui_or_backend_invalid():
    match = "is not a recognised GUI loop or backend name"
    with pytest.raises(RuntimeError, match=match):
        backend_registry.resolve_gui_or_backend('no-such-name')
