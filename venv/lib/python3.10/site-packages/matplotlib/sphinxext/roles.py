"""
Custom roles for the Matplotlib documentation.

.. warning::

    These roles are considered semi-public. They are only intended to be used in
    the Matplotlib documentation.

However, it can happen that downstream packages end up pulling these roles into
their documentation, which will result in documentation build errors. The following
describes the exact mechanism and how to fix the errors.

There are two ways, Matplotlib docstrings can end up in downstream documentation.
You have to subclass a Matplotlib class and either use the ``:inherited-members:``
option in your autodoc configuration, or you have to override a method without
specifying a new docstring; the new method will inherit the original docstring and
still render in your autodoc. If the docstring contains one of the custom sphinx
roles, you'll see one of the following error messages:

.. code-block:: none

    Unknown interpreted text role "mpltype".
    Unknown interpreted text role "rc".

To fix this, you can add this module as extension to your sphinx :file:`conf.py`::

    extensions = [
        'matplotlib.sphinxext.roles',
        # Other extensions.
    ]

.. warning::

    Direct use of these roles in other packages is not officially supported. We
    reserve the right to modify or remove these roles without prior notification.
"""

from urllib.parse import urlsplit, urlunsplit

from docutils import nodes

import matplotlib
from matplotlib import rcParamsDefault


class _QueryReference(nodes.Inline, nodes.TextElement):
    """
    Wraps a reference or pending reference to add a query string.

    The query string is generated from the attributes added to this node.

    Also equivalent to a `~docutils.nodes.literal` node.
    """

    def to_query_string(self):
        """Generate query string from node attributes."""
        return '&'.join(f'{name}={value}' for name, value in self.attlist())


def _visit_query_reference_node(self, node):
    """
    Resolve *node* into query strings on its ``reference`` children.

    Then act as if this is a `~docutils.nodes.literal`.
    """
    query = node.to_query_string()
    for refnode in node.findall(nodes.reference):
        uri = urlsplit(refnode['refuri'])._replace(query=query)
        refnode['refuri'] = urlunsplit(uri)

    self.visit_literal(node)


def _depart_query_reference_node(self, node):
    """
    Act as if this is a `~docutils.nodes.literal`.
    """
    self.depart_literal(node)


def _rcparam_role(name, rawtext, text, lineno, inliner, options=None, content=None):
    """
    Sphinx role ``:rc:`` to highlight and link ``rcParams`` entries.

    Usage: Give the desired ``rcParams`` key as parameter.

    :code:`:rc:`figure.dpi`` will render as: :rc:`figure.dpi`
    """
    # Generate a pending cross-reference so that Sphinx will ensure this link
    # isn't broken at some point in the future.
    title = f'rcParams["{text}"]'
    target = 'matplotlibrc-sample'
    ref_nodes, messages = inliner.interpreted(title, f'{title} <{target}>',
                                              'ref', lineno)

    qr = _QueryReference(rawtext, highlight=text)
    qr += ref_nodes
    node_list = [qr]

    # The default backend would be printed as "agg", but that's not correct (as
    # the default is actually determined by fallback).
    if text in rcParamsDefault and text != "backend":
        node_list.extend([
            nodes.Text(' (default: '),
            nodes.literal('', repr(rcParamsDefault[text])),
            nodes.Text(')'),
            ])

    return node_list, messages


def _mpltype_role(name, rawtext, text, lineno, inliner, options=None, content=None):
    """
    Sphinx role ``:mpltype:`` for custom matplotlib types.

    In Matplotlib, there are a number of type-like concepts that do not have a
    direct type representation; example: color. This role allows to properly
    highlight them in the docs and link to their definition.

    Currently supported values:

    - :code:`:mpltype:`color`` will render as: :mpltype:`color`

    """
    mpltype = text
    type_to_link_target = {
        'color': 'colors_def',
    }
    if mpltype not in type_to_link_target:
        raise ValueError(f"Unknown mpltype: {mpltype!r}")

    node_list, messages = inliner.interpreted(
        mpltype, f'{mpltype} <{type_to_link_target[mpltype]}>', 'ref', lineno)
    return node_list, messages


def setup(app):
    app.add_role("rc", _rcparam_role)
    app.add_role("mpltype", _mpltype_role)
    app.add_node(
        _QueryReference,
        html=(_visit_query_reference_node, _depart_query_reference_node),
        latex=(_visit_query_reference_node, _depart_query_reference_node),
        text=(_visit_query_reference_node, _depart_query_reference_node),
    )
    return {"version": matplotlib.__version__,
            "parallel_read_safe": True, "parallel_write_safe": True}
