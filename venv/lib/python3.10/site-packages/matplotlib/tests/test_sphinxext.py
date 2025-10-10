"""Tests for tinypages build using sphinx extensions."""

import filecmp
import os
from pathlib import Path
import shutil
import sys

from matplotlib.testing import subprocess_run_for_testing
import pytest


pytest.importorskip('sphinx', minversion='4.1.3')


def build_sphinx_html(source_dir, doctree_dir, html_dir, extra_args=None):
    # Build the pages with warnings turned into errors
    extra_args = [] if extra_args is None else extra_args
    cmd = [sys.executable, '-msphinx', '-W', '-b', 'html',
           '-d', str(doctree_dir), str(source_dir), str(html_dir), *extra_args]
    proc = subprocess_run_for_testing(
        cmd, capture_output=True, text=True,
        env={**os.environ, "MPLBACKEND": ""})
    out = proc.stdout
    err = proc.stderr

    assert proc.returncode == 0, \
        f"sphinx build failed with stdout:\n{out}\nstderr:\n{err}\n"
    if err:
        pytest.fail(f"sphinx build emitted the following warnings:\n{err}")

    assert html_dir.is_dir()


def test_tinypages(tmp_path):
    shutil.copytree(Path(__file__).parent / 'tinypages', tmp_path,
                    dirs_exist_ok=True)
    html_dir = tmp_path / '_build' / 'html'
    img_dir = html_dir / '_images'
    doctree_dir = tmp_path / 'doctrees'
    # Build the pages with warnings turned into errors
    cmd = [sys.executable, '-msphinx', '-W', '-b', 'html',
           '-d', str(doctree_dir),
           str(Path(__file__).parent / 'tinypages'), str(html_dir)]
    # On CI, gcov emits warnings (due to agg headers being included with the
    # same name in multiple extension modules -- but we don't care about their
    # coverage anyways); hide them using GCOV_ERROR_FILE.
    proc = subprocess_run_for_testing(
        cmd, capture_output=True, text=True,
        env={**os.environ, "MPLBACKEND": "", "GCOV_ERROR_FILE": os.devnull}
    )
    out = proc.stdout
    err = proc.stderr

    # Build the pages with warnings turned into errors
    build_sphinx_html(tmp_path, doctree_dir, html_dir)

    def plot_file(num):
        return img_dir / f'some_plots-{num}.png'

    def plot_directive_file(num):
        # This is always next to the doctree dir.
        return doctree_dir.parent / 'plot_directive' / f'some_plots-{num}.png'

    range_10, range_6, range_4 = (plot_file(i) for i in range(1, 4))
    # Plot 5 is range(6) plot
    assert filecmp.cmp(range_6, plot_file(5))
    # Plot 7 is range(4) plot
    assert filecmp.cmp(range_4, plot_file(7))
    # Plot 11 is range(10) plot
    assert filecmp.cmp(range_10, plot_file(11))
    # Plot 12 uses the old range(10) figure and the new range(6) figure
    assert filecmp.cmp(range_10, plot_file('12_00'))
    assert filecmp.cmp(range_6, plot_file('12_01'))
    # Plot 13 shows close-figs in action
    assert filecmp.cmp(range_4, plot_file(13))
    # Plot 14 has included source
    html_contents = (html_dir / 'some_plots.html').read_text(encoding='utf-8')

    assert '# Only a comment' in html_contents
    # check plot defined in external file.
    assert filecmp.cmp(range_4, img_dir / 'range4.png')
    assert filecmp.cmp(range_6, img_dir / 'range6_range6.png')
    # check if figure caption made it into html file
    assert 'This is the caption for plot 15.' in html_contents
    # check if figure caption using :caption: made it into html file (because this plot
    # doesn't use srcset, the caption preserves newlines in the output.)
    assert 'Plot 17 uses the caption option,\nwith multi-line input.' in html_contents
    # check if figure alt text using :alt: made it into html file
    assert 'Plot 17 uses the alt option, with multi-line input.' in html_contents
    # check if figure caption made it into html file
    assert 'This is the caption for plot 18.' in html_contents
    # check if the custom classes made it into the html file
    assert 'plot-directive my-class my-other-class' in html_contents
    # check that the multi-image caption is applied twice
    assert html_contents.count('This caption applies to both plots.') == 2
    # Plot 21 is range(6) plot via an include directive. But because some of
    # the previous plots are repeated, the argument to plot_file() is only 17.
    assert filecmp.cmp(range_6, plot_file(17))
    # plot 22 is from the range6.py file again, but a different function
    assert filecmp.cmp(range_10, img_dir / 'range6_range10.png')

    # Modify the included plot
    contents = (tmp_path / 'included_plot_21.rst').read_bytes()
    contents = contents.replace(b'plt.plot(range(6))', b'plt.plot(range(4))')
    (tmp_path / 'included_plot_21.rst').write_bytes(contents)
    # Build the pages again and check that the modified file was updated
    modification_times = [plot_directive_file(i).stat().st_mtime
                          for i in (1, 2, 3, 5)]
    build_sphinx_html(tmp_path, doctree_dir, html_dir)
    assert filecmp.cmp(range_4, plot_file(17))
    # Check that the plots in the plot_directive folder weren't changed.
    # (plot_directive_file(1) won't be modified, but it will be copied to html/
    # upon compilation, so plot_file(1) will be modified)
    assert plot_directive_file(1).stat().st_mtime == modification_times[0]
    assert plot_directive_file(2).stat().st_mtime == modification_times[1]
    assert plot_directive_file(3).stat().st_mtime == modification_times[2]
    assert filecmp.cmp(range_10, plot_file(1))
    assert filecmp.cmp(range_6, plot_file(2))
    assert filecmp.cmp(range_4, plot_file(3))
    # Make sure that figures marked with context are re-created (but that the
    # contents are the same)
    assert plot_directive_file(5).stat().st_mtime > modification_times[3]
    assert filecmp.cmp(range_6, plot_file(5))


def test_plot_html_show_source_link(tmp_path):
    parent = Path(__file__).parent
    shutil.copyfile(parent / 'tinypages/conf.py', tmp_path / 'conf.py')
    shutil.copytree(parent / 'tinypages/_static', tmp_path / '_static')
    doctree_dir = tmp_path / 'doctrees'
    (tmp_path / 'index.rst').write_text("""
.. plot::

    plt.plot(range(2))
""")
    # Make sure source scripts are created by default
    html_dir1 = tmp_path / '_build' / 'html1'
    build_sphinx_html(tmp_path, doctree_dir, html_dir1)
    assert len(list(html_dir1.glob("**/index-1.py"))) == 1
    # Make sure source scripts are NOT created when
    # plot_html_show_source_link` is False
    html_dir2 = tmp_path / '_build' / 'html2'
    build_sphinx_html(tmp_path, doctree_dir, html_dir2,
                      extra_args=['-D', 'plot_html_show_source_link=0'])
    assert len(list(html_dir2.glob("**/index-1.py"))) == 0


@pytest.mark.parametrize('plot_html_show_source_link', [0, 1])
def test_show_source_link_true(tmp_path, plot_html_show_source_link):
    # Test that a source link is generated if :show-source-link: is true,
    # whether or not plot_html_show_source_link is true.
    parent = Path(__file__).parent
    shutil.copyfile(parent / 'tinypages/conf.py', tmp_path / 'conf.py')
    shutil.copytree(parent / 'tinypages/_static', tmp_path / '_static')
    doctree_dir = tmp_path / 'doctrees'
    (tmp_path / 'index.rst').write_text("""
.. plot::
    :show-source-link: true

    plt.plot(range(2))
""")
    html_dir = tmp_path / '_build' / 'html'
    build_sphinx_html(tmp_path, doctree_dir, html_dir, extra_args=[
        '-D', f'plot_html_show_source_link={plot_html_show_source_link}'])
    assert len(list(html_dir.glob("**/index-1.py"))) == 1


@pytest.mark.parametrize('plot_html_show_source_link', [0, 1])
def test_show_source_link_false(tmp_path, plot_html_show_source_link):
    # Test that a source link is NOT generated if :show-source-link: is false,
    # whether or not plot_html_show_source_link is true.
    parent = Path(__file__).parent
    shutil.copyfile(parent / 'tinypages/conf.py', tmp_path / 'conf.py')
    shutil.copytree(parent / 'tinypages/_static', tmp_path / '_static')
    doctree_dir = tmp_path / 'doctrees'
    (tmp_path / 'index.rst').write_text("""
.. plot::
    :show-source-link: false

    plt.plot(range(2))
""")
    html_dir = tmp_path / '_build' / 'html'
    build_sphinx_html(tmp_path, doctree_dir, html_dir, extra_args=[
        '-D', f'plot_html_show_source_link={plot_html_show_source_link}'])
    assert len(list(html_dir.glob("**/index-1.py"))) == 0


def test_srcset_version(tmp_path):
    shutil.copytree(Path(__file__).parent / 'tinypages', tmp_path,
                    dirs_exist_ok=True)
    html_dir = tmp_path / '_build' / 'html'
    img_dir = html_dir / '_images'
    doctree_dir = tmp_path / 'doctrees'

    build_sphinx_html(tmp_path, doctree_dir, html_dir, extra_args=[
        '-D', 'plot_srcset=2x'])

    def plot_file(num, suff=''):
        return img_dir / f'some_plots-{num}{suff}.png'

    # check some-plots
    for ind in [1, 2, 3, 5, 7, 11, 13, 15, 17]:
        assert plot_file(ind).exists()
        assert plot_file(ind, suff='.2x').exists()

    assert (img_dir / 'nestedpage-index-1.png').exists()
    assert (img_dir / 'nestedpage-index-1.2x.png').exists()
    assert (img_dir / 'nestedpage-index-2.png').exists()
    assert (img_dir / 'nestedpage-index-2.2x.png').exists()
    assert (img_dir / 'nestedpage2-index-1.png').exists()
    assert (img_dir / 'nestedpage2-index-1.2x.png').exists()
    assert (img_dir / 'nestedpage2-index-2.png').exists()
    assert (img_dir / 'nestedpage2-index-2.2x.png').exists()

    # Check html for srcset

    assert ('srcset="_images/some_plots-1.png, _images/some_plots-1.2x.png 2.00x"'
            in (html_dir / 'some_plots.html').read_text(encoding='utf-8'))

    st = ('srcset="../_images/nestedpage-index-1.png, '
          '../_images/nestedpage-index-1.2x.png 2.00x"')
    assert st in (html_dir / 'nestedpage/index.html').read_text(encoding='utf-8')

    st = ('srcset="../_images/nestedpage2-index-2.png, '
          '../_images/nestedpage2-index-2.2x.png 2.00x"')
    assert st in (html_dir / 'nestedpage2/index.html').read_text(encoding='utf-8')
