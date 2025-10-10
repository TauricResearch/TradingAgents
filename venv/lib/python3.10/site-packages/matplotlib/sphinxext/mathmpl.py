r"""
A role and directive to display mathtext in Sphinx
==================================================

The ``mathmpl`` Sphinx extension creates a mathtext image in Matplotlib and
shows it in html output. Thus, it is a true and faithful representation of what
you will see if you pass a given LaTeX string to Matplotlib (see
:ref:`mathtext`).

.. warning::
    In most cases, you will likely want to use one of `Sphinx's builtin Math
    extensions
    <https://www.sphinx-doc.org/en/master/usage/extensions/math.html>`__
    instead of this one. The builtin Sphinx math directive uses MathJax to
    render mathematical expressions, and addresses accessibility concerns that
    ``mathmpl`` doesn't address.

Mathtext may be included in two ways:

1. Inline, using the role::

     This text uses inline math: :mathmpl:`\alpha > \beta`.

   which produces:

     This text uses inline math: :mathmpl:`\alpha > \beta`.

2. Standalone, using the directive::

     Here is some standalone math:

     .. mathmpl::

         \alpha > \beta

   which produces:

     Here is some standalone math:

     .. mathmpl::

         \alpha > \beta

Options
-------

The ``mathmpl`` role and directive both support the following options:

fontset : str, default: 'cm'
    The font set to use when displaying math. See :rc:`mathtext.fontset`.

fontsize : float
    The font size, in points. Defaults to the value from the extension
    configuration option defined below.

Configuration options
---------------------

The mathtext extension has the following configuration options:

mathmpl_fontsize : float, default: 10.0
    Default font size, in points.

mathmpl_srcset : list of str, default: []
    Additional image sizes to generate when embedding in HTML, to support
    `responsive resolution images
    <https://developer.mozilla.org/en-US/docs/Learn/HTML/Multimedia_and_embedding/Responsive_images>`__.
    The list should contain additional x-descriptors (``'1.5x'``, ``'2x'``,
    etc.) to generate (1x is the default and always included.)

"""

import hashlib
from pathlib import Path

from docutils import nodes
from docutils.parsers.rst import Directive, directives
import sphinx
from sphinx.errors import ConfigError, ExtensionError

import matplotlib as mpl
from matplotlib import _api, mathtext
from matplotlib.rcsetup import validate_float_or_None


# Define LaTeX math node:
class latex_math(nodes.General, nodes.Element):
    pass


def fontset_choice(arg):
    return directives.choice(arg, mathtext.MathTextParser._font_type_mapping)


def math_role(role, rawtext, text, lineno, inliner,
              options={}, content=[]):
    i = rawtext.find('`')
    latex = rawtext[i+1:-1]
    node = latex_math(rawtext)
    node['latex'] = latex
    node['fontset'] = options.get('fontset', 'cm')
    node['fontsize'] = options.get('fontsize',
                                   setup.app.config.mathmpl_fontsize)
    return [node], []
math_role.options = {'fontset': fontset_choice,
                     'fontsize': validate_float_or_None}


class MathDirective(Directive):
    """
    The ``.. mathmpl::`` directive, as documented in the module's docstring.
    """
    has_content = True
    required_arguments = 0
    optional_arguments = 0
    final_argument_whitespace = False
    option_spec = {'fontset': fontset_choice,
                   'fontsize': validate_float_or_None}

    def run(self):
        latex = ''.join(self.content)
        node = latex_math(self.block_text)
        node['latex'] = latex
        node['fontset'] = self.options.get('fontset', 'cm')
        node['fontsize'] = self.options.get('fontsize',
                                            setup.app.config.mathmpl_fontsize)
        return [node]


# This uses mathtext to render the expression
def latex2png(latex, filename, fontset='cm', fontsize=10, dpi=100):
    with mpl.rc_context({'mathtext.fontset': fontset, 'font.size': fontsize}):
        try:
            depth = mathtext.math_to_image(
                f"${latex}$", filename, dpi=dpi, format="png")
        except Exception:
            _api.warn_external(f"Could not render math expression {latex}")
            depth = 0
    return depth


# LaTeX to HTML translation stuff:
def latex2html(node, source):
    inline = isinstance(node.parent, nodes.TextElement)
    latex = node['latex']
    fontset = node['fontset']
    fontsize = node['fontsize']
    name = 'math-{}'.format(
        hashlib.sha256(
            f'{latex}{fontset}{fontsize}'.encode(),
            usedforsecurity=False,
        ).hexdigest()[-10:])

    destdir = Path(setup.app.builder.outdir, '_images', 'mathmpl')
    destdir.mkdir(parents=True, exist_ok=True)

    dest = destdir / f'{name}.png'
    depth = latex2png(latex, dest, fontset, fontsize=fontsize)

    srcset = []
    for size in setup.app.config.mathmpl_srcset:
        filename = f'{name}-{size.replace(".", "_")}.png'
        latex2png(latex, destdir / filename, fontset, fontsize=fontsize,
                  dpi=100 * float(size[:-1]))
        srcset.append(
            f'{setup.app.builder.imgpath}/mathmpl/{filename} {size}')
    if srcset:
        srcset = (f'srcset="{setup.app.builder.imgpath}/mathmpl/{name}.png, ' +
                  ', '.join(srcset) + '" ')

    if inline:
        cls = ''
    else:
        cls = 'class="center" '
    if inline and depth != 0:
        style = 'style="position: relative; bottom: -%dpx"' % (depth + 1)
    else:
        style = ''

    return (f'<img src="{setup.app.builder.imgpath}/mathmpl/{name}.png"'
            f' {srcset}{cls}{style}/>')


def _config_inited(app, config):
    # Check for srcset hidpi images
    for i, size in enumerate(app.config.mathmpl_srcset):
        if size[-1] == 'x':  # "2x" = "2.0"
            try:
                float(size[:-1])
            except ValueError:
                raise ConfigError(
                    f'Invalid value for mathmpl_srcset parameter: {size!r}. '
                    'Must be a list of strings with the multiplicative '
                    'factor followed by an "x".  e.g. ["2.0x", "1.5x"]')
        else:
            raise ConfigError(
                f'Invalid value for mathmpl_srcset parameter: {size!r}. '
                'Must be a list of strings with the multiplicative '
                'factor followed by an "x".  e.g. ["2.0x", "1.5x"]')


def setup(app):
    setup.app = app
    app.add_config_value('mathmpl_fontsize', 10.0, True)
    app.add_config_value('mathmpl_srcset', [], True)
    try:
        app.connect('config-inited', _config_inited)  # Sphinx 1.8+
    except ExtensionError:
        app.connect('env-updated', lambda app, env: _config_inited(app, None))

    # Add visit/depart methods to HTML-Translator:
    def visit_latex_math_html(self, node):
        source = self.document.attributes['source']
        self.body.append(latex2html(node, source))

    def depart_latex_math_html(self, node):
        pass

    # Add visit/depart methods to LaTeX-Translator:
    def visit_latex_math_latex(self, node):
        inline = isinstance(node.parent, nodes.TextElement)
        if inline:
            self.body.append('$%s$' % node['latex'])
        else:
            self.body.extend(['\\begin{equation}',
                              node['latex'],
                              '\\end{equation}'])

    def depart_latex_math_latex(self, node):
        pass

    app.add_node(latex_math,
                 html=(visit_latex_math_html, depart_latex_math_html),
                 latex=(visit_latex_math_latex, depart_latex_math_latex))
    app.add_role('mathmpl', math_role)
    app.add_directive('mathmpl', MathDirective)
    if sphinx.version_info < (1, 8):
        app.add_role('math', math_role)
        app.add_directive('math', MathDirective)

    metadata = {'parallel_read_safe': True, 'parallel_write_safe': True}
    return metadata
