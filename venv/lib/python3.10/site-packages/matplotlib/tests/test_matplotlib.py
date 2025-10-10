import os
import subprocess
import sys
from unittest.mock import patch

import pytest

import matplotlib
from matplotlib.testing import subprocess_run_for_testing


@pytest.mark.parametrize('version_str, version_tuple', [
    ('3.5.0', (3, 5, 0, 'final', 0)),
    ('3.5.0rc2', (3, 5, 0, 'candidate', 2)),
    ('3.5.0.dev820+g6768ef8c4c', (3, 5, 0, 'alpha', 820)),
    ('3.5.0.post820+g6768ef8c4c', (3, 5, 1, 'alpha', 820)),
])
def test_parse_to_version_info(version_str, version_tuple):
    assert matplotlib._parse_to_version_info(version_str) == version_tuple


@pytest.mark.skipif(sys.platform == "win32",
                    reason="chmod() doesn't work as is on Windows")
@pytest.mark.skipif(sys.platform != "win32" and os.geteuid() == 0,
                    reason="chmod() doesn't work as root")
def test_tmpconfigdir_warning(tmp_path):
    """Test that a warning is emitted if a temporary configdir must be used."""
    mode = os.stat(tmp_path).st_mode
    try:
        os.chmod(tmp_path, 0)
        proc = subprocess_run_for_testing(
            [sys.executable, "-c", "import matplotlib"],
            env={**os.environ, "MPLCONFIGDIR": str(tmp_path)},
            stderr=subprocess.PIPE, text=True, check=True)
        assert "set the MPLCONFIGDIR" in proc.stderr
    finally:
        os.chmod(tmp_path, mode)


def test_importable_with_no_home(tmp_path):
    subprocess_run_for_testing(
        [sys.executable, "-c",
         "import pathlib; pathlib.Path.home = lambda *args: 1/0; "
         "import matplotlib.pyplot"],
        env={**os.environ, "MPLCONFIGDIR": str(tmp_path)}, check=True)


def test_use_doc_standard_backends():
    """
    Test that the standard backends mentioned in the docstring of
    matplotlib.use() are the same as in matplotlib.rcsetup.
    """
    def parse(key):
        backends = []
        for line in matplotlib.use.__doc__.split(key)[1].split('\n'):
            if not line.strip():
                break
            backends += [e.strip().lower() for e in line.split(',') if e]
        return backends

    from matplotlib.backends import BackendFilter, backend_registry

    assert (set(parse('- interactive backends:\n')) ==
            set(backend_registry.list_builtin(BackendFilter.INTERACTIVE)))
    assert (set(parse('- non-interactive backends:\n')) ==
            set(backend_registry.list_builtin(BackendFilter.NON_INTERACTIVE)))


def test_importable_with__OO():
    """
    When using -OO or export PYTHONOPTIMIZE=2, docstrings are discarded,
    this simple test may prevent something like issue #17970.
    """
    program = (
        "import matplotlib as mpl; "
        "import matplotlib.pyplot as plt; "
        "import matplotlib.cbook as cbook; "
        "import matplotlib.patches as mpatches"
    )
    subprocess_run_for_testing(
        [sys.executable, "-OO", "-c", program],
        env={**os.environ, "MPLBACKEND": ""}, check=True
        )


@patch('matplotlib.subprocess.check_output')
def test_get_executable_info_timeout(mock_check_output):
    """
    Test that _get_executable_info raises ExecutableNotFoundError if the
    command times out.
    """

    mock_check_output.side_effect = subprocess.TimeoutExpired(cmd=['mock'], timeout=30)

    with pytest.raises(matplotlib.ExecutableNotFoundError, match='Timed out'):
        matplotlib._get_executable_info.__wrapped__('inkscape')
