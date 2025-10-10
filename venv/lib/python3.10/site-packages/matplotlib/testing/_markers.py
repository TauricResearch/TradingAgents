"""
pytest markers for the internal Matplotlib test suite.
"""

import logging
import shutil

import pytest

import matplotlib.testing
import matplotlib.testing.compare
from matplotlib import _get_executable_info, ExecutableNotFoundError


_log = logging.getLogger(__name__)


def _checkdep_usetex() -> bool:
    if not shutil.which("tex"):
        _log.warning("usetex mode requires TeX.")
        return False
    try:
        _get_executable_info("dvipng")
    except ExecutableNotFoundError:
        _log.warning("usetex mode requires dvipng.")
        return False
    try:
        _get_executable_info("gs")
    except ExecutableNotFoundError:
        _log.warning("usetex mode requires ghostscript.")
        return False
    return True


needs_ghostscript = pytest.mark.skipif(
    "eps" not in matplotlib.testing.compare.converter,
    reason="This test needs a ghostscript installation")
needs_pgf_lualatex = pytest.mark.skipif(
    not matplotlib.testing._check_for_pgf('lualatex'),
    reason='lualatex + pgf is required')
needs_pgf_pdflatex = pytest.mark.skipif(
    not matplotlib.testing._check_for_pgf('pdflatex'),
    reason='pdflatex + pgf is required')
needs_pgf_xelatex = pytest.mark.skipif(
    not matplotlib.testing._check_for_pgf('xelatex'),
    reason='xelatex + pgf is required')
needs_usetex = pytest.mark.skipif(
    not _checkdep_usetex(),
    reason="This test needs a TeX installation")
