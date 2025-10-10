import os
from pathlib import Path
import re
import sys

import pytest

import matplotlib.pyplot as plt
from matplotlib.testing import subprocess_run_for_testing
from matplotlib.testing._markers import needs_usetex
from matplotlib.texmanager import TexManager


def test_fontconfig_preamble():
    """Test that the preamble is included in the source."""
    plt.rcParams['text.usetex'] = True

    src1 = TexManager()._get_tex_source("", fontsize=12)
    plt.rcParams['text.latex.preamble'] = '\\usepackage{txfonts}'
    src2 = TexManager()._get_tex_source("", fontsize=12)

    assert src1 != src2


@pytest.mark.parametrize(
    "rc, preamble, family", [
        ({"font.family": "sans-serif", "font.sans-serif": "helvetica"},
         r"\usepackage{helvet}", r"\sffamily"),
        ({"font.family": "serif", "font.serif": "palatino"},
         r"\usepackage{mathpazo}", r"\rmfamily"),
        ({"font.family": "cursive", "font.cursive": "zapf chancery"},
         r"\usepackage{chancery}", r"\rmfamily"),
        ({"font.family": "monospace", "font.monospace": "courier"},
         r"\usepackage{courier}", r"\ttfamily"),
        ({"font.family": "helvetica"}, r"\usepackage{helvet}", r"\sffamily"),
        ({"font.family": "palatino"}, r"\usepackage{mathpazo}", r"\rmfamily"),
        ({"font.family": "zapf chancery"},
         r"\usepackage{chancery}", r"\rmfamily"),
        ({"font.family": "courier"}, r"\usepackage{courier}", r"\ttfamily")
    ])
def test_font_selection(rc, preamble, family):
    plt.rcParams.update(rc)
    tm = TexManager()
    src = Path(tm.make_tex("hello, world", fontsize=12)).read_text()
    assert preamble in src
    assert [*re.findall(r"\\\w+family", src)] == [family]


@needs_usetex
def test_unicode_characters():
    # Smoke test to see that Unicode characters does not cause issues
    # See #23019
    plt.rcParams['text.usetex'] = True
    fig, ax = plt.subplots()
    ax.set_ylabel('\\textit{Velocity (\N{DEGREE SIGN}/sec)}')
    ax.set_xlabel('\N{VULGAR FRACTION ONE QUARTER}Öøæ')
    fig.canvas.draw()

    # But not all characters.
    # Should raise RuntimeError, not UnicodeDecodeError
    with pytest.raises(RuntimeError):
        ax.set_title('\N{SNOWMAN}')
        fig.canvas.draw()


@needs_usetex
def test_openin_any_paranoid():
    completed = subprocess_run_for_testing(
        [sys.executable, "-c",
         'import matplotlib.pyplot as plt;'
         'plt.rcParams.update({"text.usetex": True});'
         'plt.title("paranoid");'
         'plt.show(block=False);'],
        env={**os.environ, 'openin_any': 'p'}, check=True, capture_output=True)
    assert completed.stderr == ""
