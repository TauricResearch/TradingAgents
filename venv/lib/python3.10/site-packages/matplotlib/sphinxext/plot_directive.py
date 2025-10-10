"""
A directive for including a Matplotlib plot in a Sphinx document
================================================================

This is a Sphinx extension providing a reStructuredText directive
``.. plot::`` for including a plot in a Sphinx document.

In HTML output, ``.. plot::`` will include a .png file with a link
to a high-res .png and .pdf.  In LaTeX output, it will include a .pdf.

The plot content may be defined in one of three ways:

1. **A path to a source file** as the argument to the directive::

     .. plot:: path/to/plot.py

   When a path to a source file is given, the content of the
   directive may optionally contain a caption for the plot::

     .. plot:: path/to/plot.py

        The plot caption.

   Additionally, one may specify the name of a function to call (with
   no arguments) immediately after importing the module::

     .. plot:: path/to/plot.py plot_function1

2. Included as **inline content** to the directive::

     .. plot::

        import matplotlib.pyplot as plt
        plt.plot([1, 2, 3], [4, 5, 6])
        plt.title("A plotting exammple")

3. Using **doctest** syntax::

     .. plot::

        A plotting example:
        >>> import matplotlib.pyplot as plt
        >>> plt.plot([1, 2, 3], [4, 5, 6])

Options
-------

The ``.. plot::`` directive supports the following options:

``:format:`` : {'python', 'doctest'}
    The format of the input.  If unset, the format is auto-detected.

``:include-source:`` : bool
    Whether to display the source code. The default can be changed using
    the ``plot_include_source`` variable in :file:`conf.py` (which itself
    defaults to False).

``:show-source-link:`` : bool
    Whether to show a link to the source in HTML. The default can be
    changed using the ``plot_html_show_source_link`` variable in
    :file:`conf.py` (which itself defaults to True).

``:context:`` : bool or str
    If provided, the code will be run in the context of all previous plot
    directives for which the ``:context:`` option was specified.  This only
    applies to inline code plot directives, not those run from files. If
    the ``:context: reset`` option is specified, the context is reset
    for this and future plots, and previous figures are closed prior to
    running the code. ``:context: close-figs`` keeps the context but closes
    previous figures before running the code.

``:nofigs:`` : bool
    If specified, the code block will be run, but no figures will be
    inserted.  This is usually useful with the ``:context:`` option.

``:caption:`` : str
    If specified, the option's argument will be used as a caption for the
    figure. This overwrites the caption given in the content, when the plot
    is generated from a file.

Additionally, this directive supports all the options of the `image directive
<https://docutils.sourceforge.io/docs/ref/rst/directives.html#image>`_,
except for ``:target:`` (since plot will add its own target).  These include
``:alt:``, ``:height:``, ``:width:``, ``:scale:``, ``:align:`` and ``:class:``.

Configuration options
---------------------

The plot directive has the following configuration options:

plot_include_source
    Default value for the include-source option (default: False).

plot_html_show_source_link
    Whether to show a link to the source in HTML (default: True).

plot_pre_code
    Code that should be executed before each plot. If None (the default),
    it will default to a string containing::

        import numpy as np
        from matplotlib import pyplot as plt

plot_basedir
    Base directory, to which ``plot::`` file names are relative to.
    If None or empty (the default), file names are relative to the
    directory where the file containing the directive is.

plot_formats
    File formats to generate (default: ['png', 'hires.png', 'pdf']).
    List of tuples or strings::

        [(suffix, dpi), suffix, ...]

    that determine the file format and the DPI. For entries whose
    DPI was omitted, sensible defaults are chosen. When passing from
    the command line through sphinx_build the list should be passed as
    suffix:dpi,suffix:dpi, ...

plot_html_show_formats
    Whether to show links to the files in HTML (default: True).

plot_rcparams
    A dictionary containing any non-standard rcParams that should
    be applied before each plot (default: {}).

plot_apply_rcparams
    By default, rcParams are applied when ``:context:`` option is not used
    in a plot directive.  If set, this configuration option overrides this
    behavior and applies rcParams before each plot.

plot_working_directory
    By default, the working directory will be changed to the directory of
    the example, so the code can get at its data files, if any.  Also its
    path will be added to `sys.path` so it can import any helper modules
    sitting beside it.  This configuration option can be used to specify
    a central directory (also added to `sys.path`) where data files and
    helper modules for all code are located.

plot_template
    Provide a customized template for preparing restructured text.

plot_srcset
    Allow the srcset image option for responsive image resolutions. List of
    strings with the multiplicative factors followed by an "x".
    e.g. ["2.0x", "1.5x"].  "2.0x" will create a png with the default "png"
    resolution from plot_formats, multiplied by 2. If plot_srcset is
    specified, the plot directive uses the
    :doc:`/api/sphinxext_figmpl_directive_api` (instead of the usual figure
    directive) in the intermediary rst file that is generated.
    The plot_srcset option is incompatible with *singlehtml* builds, and an
    error will be raised.

Notes on how it works
---------------------

The plot directive runs the code it is given, either in the source file or the
code under the directive. The figure created (if any) is saved in the sphinx
build directory under a subdirectory named ``plot_directive``.  It then creates
an intermediate rst file that calls a ``.. figure:`` directive (or
``.. figmpl::`` directive if ``plot_srcset`` is being used) and has links to
the ``*.png`` files in the ``plot_directive`` directory.  These translations can
be customized by changing the *plot_template*.  See the source of
:doc:`/api/sphinxext_plot_directive_api` for the templates defined in *TEMPLATE*
and *TEMPLATE_SRCSET*.
"""

import contextlib
import doctest
from io import StringIO
import itertools
import os
from os.path import relpath
from pathlib import Path
import re
import shutil
import sys
import textwrap
import traceback

from docutils.parsers.rst import directives, Directive
from docutils.parsers.rst.directives.images import Image
import jinja2  # Sphinx dependency.

from sphinx.errors import ExtensionError

import matplotlib
from matplotlib.backend_bases import FigureManagerBase
import matplotlib.pyplot as plt
from matplotlib import _pylab_helpers, cbook

matplotlib.use("agg")

__version__ = 2


# -----------------------------------------------------------------------------
# Registration hook
# -----------------------------------------------------------------------------


def _option_boolean(arg):
    if not arg or not arg.strip():
        # no argument given, assume used as a flag
        return True
    elif arg.strip().lower() in ('no', '0', 'false'):
        return False
    elif arg.strip().lower() in ('yes', '1', 'true'):
        return True
    else:
        raise ValueError(f'{arg!r} unknown boolean')


def _option_context(arg):
    if arg in [None, 'reset', 'close-figs']:
        return arg
    raise ValueError("Argument should be None or 'reset' or 'close-figs'")


def _option_format(arg):
    return directives.choice(arg, ('python', 'doctest'))


def mark_plot_labels(app, document):
    """
    To make plots referenceable, we need to move the reference from the
    "htmlonly" (or "latexonly") node to the actual figure node itself.
    """
    for name, explicit in document.nametypes.items():
        if not explicit:
            continue
        labelid = document.nameids[name]
        if labelid is None:
            continue
        node = document.ids[labelid]
        if node.tagname in ('html_only', 'latex_only'):
            for n in node:
                if n.tagname == 'figure':
                    sectname = name
                    for c in n:
                        if c.tagname == 'caption':
                            sectname = c.astext()
                            break

                    node['ids'].remove(labelid)
                    node['names'].remove(name)
                    n['ids'].append(labelid)
                    n['names'].append(name)
                    document.settings.env.labels[name] = \
                        document.settings.env.docname, labelid, sectname
                    break


class PlotDirective(Directive):
    """The ``.. plot::`` directive, as documented in the module's docstring."""

    has_content = True
    required_arguments = 0
    optional_arguments = 2
    final_argument_whitespace = False
    option_spec = {
        'alt': directives.unchanged,
        'height': directives.length_or_unitless,
        'width': directives.length_or_percentage_or_unitless,
        'scale': directives.nonnegative_int,
        'align': Image.align,
        'class': directives.class_option,
        'include-source': _option_boolean,
        'show-source-link': _option_boolean,
        'format': _option_format,
        'context': _option_context,
        'nofigs': directives.flag,
        'caption': directives.unchanged,
        }

    def run(self):
        """Run the plot directive."""
        try:
            return run(self.arguments, self.content, self.options,
                       self.state_machine, self.state, self.lineno)
        except Exception as e:
            raise self.error(str(e))


def _copy_css_file(app, exc):
    if exc is None and app.builder.format == 'html':
        src = cbook._get_data_path('plot_directive/plot_directive.css')
        dst = app.outdir / Path('_static')
        dst.mkdir(exist_ok=True)
        # Use copyfile because we do not want to copy src's permissions.
        shutil.copyfile(src, dst / Path('plot_directive.css'))


def setup(app):
    setup.app = app
    setup.config = app.config
    setup.confdir = app.confdir
    app.add_directive('plot', PlotDirective)
    app.add_config_value('plot_pre_code', None, True)
    app.add_config_value('plot_include_source', False, True)
    app.add_config_value('plot_html_show_source_link', True, True)
    app.add_config_value('plot_formats', ['png', 'hires.png', 'pdf'], True)
    app.add_config_value('plot_basedir', None, True)
    app.add_config_value('plot_html_show_formats', True, True)
    app.add_config_value('plot_rcparams', {}, True)
    app.add_config_value('plot_apply_rcparams', False, True)
    app.add_config_value('plot_working_directory', None, True)
    app.add_config_value('plot_template', None, True)
    app.add_config_value('plot_srcset', [], True)
    app.connect('doctree-read', mark_plot_labels)
    app.add_css_file('plot_directive.css')
    app.connect('build-finished', _copy_css_file)
    metadata = {'parallel_read_safe': True, 'parallel_write_safe': True,
                'version': matplotlib.__version__}
    return metadata


# -----------------------------------------------------------------------------
# Doctest handling
# -----------------------------------------------------------------------------


def contains_doctest(text):
    try:
        # check if it's valid Python as-is
        compile(text, '<string>', 'exec')
        return False
    except SyntaxError:
        pass
    r = re.compile(r'^\s*>>>', re.M)
    m = r.search(text)
    return bool(m)


def _split_code_at_show(text, function_name):
    """Split code at plt.show()."""

    is_doctest = contains_doctest(text)
    if function_name is None:
        parts = []
        part = []
        for line in text.split("\n"):
            if ((not is_doctest and line.startswith('plt.show(')) or
                   (is_doctest and line.strip() == '>>> plt.show()')):
                part.append(line)
                parts.append("\n".join(part))
                part = []
            else:
                part.append(line)
        if "\n".join(part).strip():
            parts.append("\n".join(part))
    else:
        parts = [text]
    return is_doctest, parts


# -----------------------------------------------------------------------------
# Template
# -----------------------------------------------------------------------------

_SOURCECODE = """
{{ source_code }}

.. only:: html

   {% if src_name or (html_show_formats and not multi_image) %}
   (
   {%- if src_name -%}
   :download:`Source code <{{ build_dir }}/{{ src_name }}>`
   {%- endif -%}
   {%- if html_show_formats and not multi_image -%}
     {%- for img in images -%}
       {%- for fmt in img.formats -%}
         {%- if src_name or not loop.first -%}, {% endif -%}
         :download:`{{ fmt }} <{{ build_dir }}/{{ img.basename }}.{{ fmt }}>`
       {%- endfor -%}
     {%- endfor -%}
   {%- endif -%}
   )
   {% endif %}
"""

TEMPLATE_SRCSET = _SOURCECODE + """
   {% for img in images %}
   .. figure-mpl:: {{ build_dir }}/{{ img.basename }}.{{ default_fmt }}
      {% for option in options -%}
      {{ option }}
      {% endfor %}
      {%- if caption -%}
      {{ caption }}  {# appropriate leading whitespace added beforehand #}
      {% endif -%}
      {%- if srcset -%}
        :srcset: {{ build_dir }}/{{ img.basename }}.{{ default_fmt }}
        {%- for sr in srcset -%}
            , {{ build_dir }}/{{ img.basename }}.{{ sr }}.{{ default_fmt }} {{sr}}
        {%- endfor -%}
      {% endif %}

   {% if html_show_formats and multi_image %}
   (
    {%- for fmt in img.formats -%}
    {%- if not loop.first -%}, {% endif -%}
    :download:`{{ fmt }} <{{ build_dir }}/{{ img.basename }}.{{ fmt }}>`
    {%- endfor -%}
   )
   {% endif %}


   {% endfor %}

.. only:: not html

   {% for img in images %}
   .. figure-mpl:: {{ build_dir }}/{{ img.basename }}.*
      {% for option in options -%}
      {{ option }}
      {% endfor -%}

      {{ caption }}  {# appropriate leading whitespace added beforehand #}
   {% endfor %}

"""

TEMPLATE = _SOURCECODE + """

   {% for img in images %}
   .. figure:: {{ build_dir }}/{{ img.basename }}.{{ default_fmt }}
      {% for option in options -%}
      {{ option }}
      {% endfor %}

      {% if html_show_formats and multi_image -%}
        (
        {%- for fmt in img.formats -%}
        {%- if not loop.first -%}, {% endif -%}
        :download:`{{ fmt }} <{{ build_dir }}/{{ img.basename }}.{{ fmt }}>`
        {%- endfor -%}
        )
      {%- endif -%}

      {{ caption }}  {# appropriate leading whitespace added beforehand #}
   {% endfor %}

.. only:: not html

   {% for img in images %}
   .. figure:: {{ build_dir }}/{{ img.basename }}.*
      {% for option in options -%}
      {{ option }}
      {% endfor -%}

      {{ caption }}  {# appropriate leading whitespace added beforehand #}
   {% endfor %}

"""

exception_template = """
.. only:: html

   [`source code <%(linkdir)s/%(basename)s.py>`__]

Exception occurred rendering plot.

"""

# the context of the plot for all directives specified with the
# :context: option
plot_context = dict()


class ImageFile:
    def __init__(self, basename, dirname):
        self.basename = basename
        self.dirname = dirname
        self.formats = []

    def filename(self, format):
        return os.path.join(self.dirname, f"{self.basename}.{format}")

    def filenames(self):
        return [self.filename(fmt) for fmt in self.formats]


def out_of_date(original, derived, includes=None):
    """
    Return whether *derived* is out-of-date relative to *original* or any of
    the RST files included in it using the RST include directive (*includes*).
    *derived* and *original* are full paths, and *includes* is optionally a
    list of full paths which may have been included in the *original*.
    """
    if not os.path.exists(derived):
        return True

    if includes is None:
        includes = []
    files_to_check = [original, *includes]

    def out_of_date_one(original, derived_mtime):
        return (os.path.exists(original) and
                derived_mtime < os.stat(original).st_mtime)

    derived_mtime = os.stat(derived).st_mtime
    return any(out_of_date_one(f, derived_mtime) for f in files_to_check)


class PlotError(RuntimeError):
    pass


def _run_code(code, code_path, ns=None, function_name=None):
    """
    Import a Python module from a path, and run the function given by
    name, if function_name is not None.
    """

    # Change the working directory to the directory of the example, so
    # it can get at its data files, if any.  Add its path to sys.path
    # so it can import any helper modules sitting beside it.
    pwd = os.getcwd()
    if setup.config.plot_working_directory is not None:
        try:
            os.chdir(setup.config.plot_working_directory)
        except OSError as err:
            raise OSError(f'{err}\n`plot_working_directory` option in '
                          f'Sphinx configuration file must be a valid '
                          f'directory path') from err
        except TypeError as err:
            raise TypeError(f'{err}\n`plot_working_directory` option in '
                            f'Sphinx configuration file must be a string or '
                            f'None') from err
    elif code_path is not None:
        dirname = os.path.abspath(os.path.dirname(code_path))
        os.chdir(dirname)

    with cbook._setattr_cm(
            sys, argv=[code_path], path=[os.getcwd(), *sys.path]), \
            contextlib.redirect_stdout(StringIO()):
        try:
            if ns is None:
                ns = {}
            if not ns:
                if setup.config.plot_pre_code is None:
                    exec('import numpy as np\n'
                         'from matplotlib import pyplot as plt\n', ns)
                else:
                    exec(str(setup.config.plot_pre_code), ns)
            if "__main__" in code:
                ns['__name__'] = '__main__'

            # Patch out non-interactive show() to avoid triggering a warning.
            with cbook._setattr_cm(FigureManagerBase, show=lambda self: None):
                exec(code, ns)
                if function_name is not None:
                    exec(function_name + "()", ns)

        except (Exception, SystemExit) as err:
            raise PlotError(traceback.format_exc()) from err
        finally:
            os.chdir(pwd)
    return ns


def clear_state(plot_rcparams, close=True):
    if close:
        plt.close('all')
    matplotlib.rc_file_defaults()
    matplotlib.rcParams.update(plot_rcparams)


def get_plot_formats(config):
    default_dpi = {'png': 80, 'hires.png': 200, 'pdf': 200}
    formats = []
    plot_formats = config.plot_formats
    for fmt in plot_formats:
        if isinstance(fmt, str):
            if ':' in fmt:
                suffix, dpi = fmt.split(':')
                formats.append((str(suffix), int(dpi)))
            else:
                formats.append((fmt, default_dpi.get(fmt, 80)))
        elif isinstance(fmt, (tuple, list)) and len(fmt) == 2:
            formats.append((str(fmt[0]), int(fmt[1])))
        else:
            raise PlotError('invalid image format "%r" in plot_formats' % fmt)
    return formats


def _parse_srcset(entries):
    """
    Parse srcset for multiples...
    """
    srcset = {}
    for entry in entries:
        entry = entry.strip()
        if len(entry) >= 2:
            mult = entry[:-1]
            srcset[float(mult)] = entry
        else:
            raise ExtensionError(f'srcset argument {entry!r} is invalid.')
    return srcset


def render_figures(code, code_path, output_dir, output_base, context,
                   function_name, config, context_reset=False,
                   close_figs=False,
                   code_includes=None):
    """
    Run a pyplot script and save the images in *output_dir*.

    Save the images under *output_dir* with file names derived from
    *output_base*
    """

    if function_name is not None:
        output_base = f'{output_base}_{function_name}'
    formats = get_plot_formats(config)

    # Try to determine if all images already exist

    is_doctest, code_pieces = _split_code_at_show(code, function_name)
    # Look for single-figure output files first
    img = ImageFile(output_base, output_dir)
    for format, dpi in formats:
        if context or out_of_date(code_path, img.filename(format),
                                  includes=code_includes):
            all_exists = False
            break
        img.formats.append(format)
    else:
        all_exists = True

    if all_exists:
        return [(code, [img])]

    # Then look for multi-figure output files
    results = []
    for i, code_piece in enumerate(code_pieces):
        images = []
        for j in itertools.count():
            if len(code_pieces) > 1:
                img = ImageFile('%s_%02d_%02d' % (output_base, i, j),
                                output_dir)
            else:
                img = ImageFile('%s_%02d' % (output_base, j), output_dir)
            for fmt, dpi in formats:
                if context or out_of_date(code_path, img.filename(fmt),
                                          includes=code_includes):
                    all_exists = False
                    break
                img.formats.append(fmt)

            # assume that if we have one, we have them all
            if not all_exists:
                all_exists = (j > 0)
                break
            images.append(img)
        if not all_exists:
            break
        results.append((code_piece, images))
    else:
        all_exists = True

    if all_exists:
        return results

    # We didn't find the files, so build them

    results = []
    ns = plot_context if context else {}

    if context_reset:
        clear_state(config.plot_rcparams)
        plot_context.clear()

    close_figs = not context or close_figs

    for i, code_piece in enumerate(code_pieces):

        if not context or config.plot_apply_rcparams:
            clear_state(config.plot_rcparams, close_figs)
        elif close_figs:
            plt.close('all')

        _run_code(doctest.script_from_examples(code_piece) if is_doctest
                  else code_piece,
                  code_path, ns, function_name)

        images = []
        fig_managers = _pylab_helpers.Gcf.get_all_fig_managers()
        for j, figman in enumerate(fig_managers):
            if len(fig_managers) == 1 and len(code_pieces) == 1:
                img = ImageFile(output_base, output_dir)
            elif len(code_pieces) == 1:
                img = ImageFile("%s_%02d" % (output_base, j), output_dir)
            else:
                img = ImageFile("%s_%02d_%02d" % (output_base, i, j),
                                output_dir)
            images.append(img)

            for fmt, dpi in formats:
                try:
                    figman.canvas.figure.savefig(img.filename(fmt), dpi=dpi)
                    if fmt == formats[0][0] and config.plot_srcset:
                        # save a 2x, 3x etc version of the default...
                        srcset = _parse_srcset(config.plot_srcset)
                        for mult, suffix in srcset.items():
                            fm = f'{suffix}.{fmt}'
                            img.formats.append(fm)
                            figman.canvas.figure.savefig(img.filename(fm),
                                                         dpi=int(dpi * mult))
                except Exception as err:
                    raise PlotError(traceback.format_exc()) from err
                img.formats.append(fmt)

        results.append((code_piece, images))

    if not context or config.plot_apply_rcparams:
        clear_state(config.plot_rcparams, close=not context)

    return results


def run(arguments, content, options, state_machine, state, lineno):
    document = state_machine.document
    config = document.settings.env.config
    nofigs = 'nofigs' in options

    if config.plot_srcset and setup.app.builder.name == 'singlehtml':
        raise ExtensionError(
            'plot_srcset option not compatible with single HTML writer')

    formats = get_plot_formats(config)
    default_fmt = formats[0][0]

    options.setdefault('include-source', config.plot_include_source)
    options.setdefault('show-source-link', config.plot_html_show_source_link)

    if 'class' in options:
        # classes are parsed into a list of string, and output by simply
        # printing the list, abusing the fact that RST guarantees to strip
        # non-conforming characters
        options['class'] = ['plot-directive'] + options['class']
    else:
        options.setdefault('class', ['plot-directive'])
    keep_context = 'context' in options
    context_opt = None if not keep_context else options['context']

    rst_file = document.attributes['source']
    rst_dir = os.path.dirname(rst_file)

    if len(arguments):
        if not config.plot_basedir:
            source_file_name = os.path.join(setup.app.builder.srcdir,
                                            directives.uri(arguments[0]))
        else:
            source_file_name = os.path.join(setup.confdir, config.plot_basedir,
                                            directives.uri(arguments[0]))
        # If there is content, it will be passed as a caption.
        caption = '\n'.join(content)

        # Enforce unambiguous use of captions.
        if "caption" in options:
            if caption:
                raise ValueError(
                    'Caption specified in both content and options.'
                    ' Please remove ambiguity.'
                )
            # Use caption option
            caption = options["caption"]

        # If the optional function name is provided, use it
        if len(arguments) == 2:
            function_name = arguments[1]
        else:
            function_name = None

        code = Path(source_file_name).read_text(encoding='utf-8')
        output_base = os.path.basename(source_file_name)
    else:
        source_file_name = rst_file
        code = textwrap.dedent("\n".join(map(str, content)))
        counter = document.attributes.get('_plot_counter', 0) + 1
        document.attributes['_plot_counter'] = counter
        base, ext = os.path.splitext(os.path.basename(source_file_name))
        output_base = '%s-%d.py' % (base, counter)
        function_name = None
        caption = options.get('caption', '')

    base, source_ext = os.path.splitext(output_base)
    if source_ext in ('.py', '.rst', '.txt'):
        output_base = base
    else:
        source_ext = ''

    # ensure that LaTeX includegraphics doesn't choke in foo.bar.pdf filenames
    output_base = output_base.replace('.', '-')

    # is it in doctest format?
    is_doctest = contains_doctest(code)
    if 'format' in options:
        if options['format'] == 'python':
            is_doctest = False
        else:
            is_doctest = True

    # determine output directory name fragment
    source_rel_name = relpath(source_file_name, setup.confdir)
    source_rel_dir = os.path.dirname(source_rel_name).lstrip(os.path.sep)

    # build_dir: where to place output files (temporarily)
    build_dir = os.path.join(os.path.dirname(setup.app.doctreedir),
                             'plot_directive',
                             source_rel_dir)
    # get rid of .. in paths, also changes pathsep
    # see note in Python docs for warning about symbolic links on Windows.
    # need to compare source and dest paths at end
    build_dir = os.path.normpath(build_dir)
    os.makedirs(build_dir, exist_ok=True)

    # how to link to files from the RST file
    try:
        build_dir_link = relpath(build_dir, rst_dir).replace(os.path.sep, '/')
    except ValueError:
        # on Windows, relpath raises ValueError when path and start are on
        # different mounts/drives
        build_dir_link = build_dir

    # get list of included rst files so that the output is updated when any
    # plots in the included files change. These attributes are modified by the
    # include directive (see the docutils.parsers.rst.directives.misc module).
    try:
        source_file_includes = [os.path.join(os.getcwd(), t[0])
                                for t in state.document.include_log]
    except AttributeError:
        # the document.include_log attribute only exists in docutils >=0.17,
        # before that we need to inspect the state machine
        possible_sources = {os.path.join(setup.confdir, t[0])
                            for t in state_machine.input_lines.items}
        source_file_includes = [f for f in possible_sources
                                if os.path.isfile(f)]
    # remove the source file itself from the includes
    try:
        source_file_includes.remove(source_file_name)
    except ValueError:
        pass

    # save script (if necessary)
    if options['show-source-link']:
        Path(build_dir, output_base + source_ext).write_text(
            doctest.script_from_examples(code)
            if source_file_name == rst_file and is_doctest
            else code,
            encoding='utf-8')

    # make figures
    try:
        results = render_figures(code=code,
                                 code_path=source_file_name,
                                 output_dir=build_dir,
                                 output_base=output_base,
                                 context=keep_context,
                                 function_name=function_name,
                                 config=config,
                                 context_reset=context_opt == 'reset',
                                 close_figs=context_opt == 'close-figs',
                                 code_includes=source_file_includes)
        errors = []
    except PlotError as err:
        reporter = state.memo.reporter
        sm = reporter.system_message(
            2, "Exception occurred in plotting {}\n from {}:\n{}".format(
                output_base, source_file_name, err),
            line=lineno)
        results = [(code, [])]
        errors = [sm]

    # Properly indent the caption
    if caption and config.plot_srcset:
        caption = ':caption: ' + caption.replace('\n', ' ')
    elif caption:
        caption = '\n' + '\n'.join('      ' + line.strip()
                                   for line in caption.split('\n'))
    # generate output restructuredtext
    total_lines = []
    for j, (code_piece, images) in enumerate(results):
        if options['include-source']:
            if is_doctest:
                lines = ['', *code_piece.splitlines()]
            else:
                lines = ['.. code-block:: python', '',
                         *textwrap.indent(code_piece, '    ').splitlines()]
            source_code = "\n".join(lines)
        else:
            source_code = ""

        if nofigs:
            images = []

        if 'alt' in options:
            options['alt'] = options['alt'].replace('\n', ' ')

        opts = [
            f':{key}: {val}' for key, val in options.items()
            if key in ('alt', 'height', 'width', 'scale', 'align', 'class')]

        # Not-None src_name signals the need for a source download in the
        # generated html
        if j == 0 and options['show-source-link']:
            src_name = output_base + source_ext
        else:
            src_name = None
        if config.plot_srcset:
            srcset = [*_parse_srcset(config.plot_srcset).values()]
            template = TEMPLATE_SRCSET
        else:
            srcset = None
            template = TEMPLATE

        result = jinja2.Template(config.plot_template or template).render(
            default_fmt=default_fmt,
            build_dir=build_dir_link,
            src_name=src_name,
            multi_image=len(images) > 1,
            options=opts,
            srcset=srcset,
            images=images,
            source_code=source_code,
            html_show_formats=config.plot_html_show_formats and len(images),
            caption=caption)
        total_lines.extend(result.split("\n"))
        total_lines.extend("\n")

    if total_lines:
        state_machine.insert_input(total_lines, source=source_file_name)

    return errors
