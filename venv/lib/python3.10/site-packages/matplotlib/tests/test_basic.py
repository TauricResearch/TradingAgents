import builtins
import os
import sys
import textwrap

from matplotlib.testing import subprocess_run_for_testing


def test_simple():
    assert 1 + 1 == 2


def test_override_builtins():
    import pylab  # type: ignore[import]
    ok_to_override = {
        '__name__',
        '__doc__',
        '__package__',
        '__loader__',
        '__spec__',
        'any',
        'all',
        'sum',
        'divmod'
    }
    overridden = {key for key in {*dir(pylab)} & {*dir(builtins)}
                  if getattr(pylab, key) != getattr(builtins, key)}
    assert overridden <= ok_to_override


def test_lazy_imports():
    source = textwrap.dedent("""
    import sys

    import matplotlib.figure
    import matplotlib.backend_bases
    import matplotlib.pyplot

    assert 'matplotlib._tri' not in sys.modules
    assert 'matplotlib._qhull' not in sys.modules
    assert 'matplotlib._contour' not in sys.modules
    assert 'urllib.request' not in sys.modules
    """)

    subprocess_run_for_testing(
        [sys.executable, '-c', source],
        env={**os.environ, "MPLBACKEND": "", "MATPLOTLIBRC": os.devnull},
        check=True)
