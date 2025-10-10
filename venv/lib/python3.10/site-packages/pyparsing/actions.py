# actions.py
from __future__ import annotations

from typing import Union, Callable, Any

from .exceptions import ParseException
from .util import col, replaced_by_pep8
from .results import ParseResults


ParseAction = Union[
    Callable[[], Any],
    Callable[[ParseResults], Any],
    Callable[[int, ParseResults], Any],
    Callable[[str, int, ParseResults], Any],
]


class OnlyOnce:
    """
    Wrapper for parse actions, to ensure they are only called once.
    Note: parse action signature must include all 3 arguments.
    """

    def __init__(self, method_call: Callable[[str, int, ParseResults], Any]) -> None:
        from .core import _trim_arity

        self.callable = _trim_arity(method_call)
        self.called = False

    def __call__(self, s: str, l: int, t: ParseResults) -> ParseResults:
        if not self.called:
            results = self.callable(s, l, t)
            self.called = True
            return results
        raise ParseException(s, l, "OnlyOnce obj called multiple times w/out reset")

    def reset(self):
        """
        Allow the associated parse action to be called once more.
        """

        self.called = False


def match_only_at_col(n: int) -> ParseAction:
    """
    Helper method for defining parse actions that require matching at
    a specific column in the input text.
    """

    def verify_col(strg: str, locn: int, toks: ParseResults) -> None:
        if col(locn, strg) != n:
            raise ParseException(strg, locn, f"matched token not at column {n}")

    return verify_col


def replace_with(repl_str: Any) -> ParseAction:
    """
    Helper method for common parse actions that simply return
    a literal value.  Especially useful when used with
    :meth:`~ParserElement.transform_string`.

    Example:

    .. doctest::

       >>> num = Word(nums).set_parse_action(lambda toks: int(toks[0]))
       >>> na = one_of("N/A NA").set_parse_action(replace_with(math.nan))
       >>> term = na | num

       >>> term[1, ...].parse_string("324 234 N/A 234")
       ParseResults([324, 234, nan, 234], {})
    """
    return lambda s, l, t: [repl_str]


def remove_quotes(s: str, l: int, t: ParseResults) -> Any:
    r"""
    Helper parse action for removing quotation marks from parsed
    quoted strings, that use a single character for quoting. For parsing
    strings that may have multiple characters, use the :class:`QuotedString`
    class.

    Example:

    .. doctest::

       >>> # by default, quotation marks are included in parsed results
       >>> quoted_string.parse_string("'Now is the Winter of our Discontent'")
       ParseResults(["'Now is the Winter of our Discontent'"], {})

       >>> # use remove_quotes to strip quotation marks from parsed results
       >>> dequoted = quoted_string().set_parse_action(remove_quotes)
       >>> dequoted.parse_string("'Now is the Winter of our Discontent'")
       ParseResults(['Now is the Winter of our Discontent'], {})
    """
    return t[0][1:-1]


def with_attribute(*args: tuple[str, str], **attr_dict) -> ParseAction:
    """
    Helper to create a validating parse action to be used with start
    tags created with :class:`make_xml_tags` or
    :class:`make_html_tags`. Use ``with_attribute`` to qualify
    a starting tag with a required attribute value, to avoid false
    matches on common tags such as ``<TD>`` or ``<DIV>``.

    Call ``with_attribute`` with a series of attribute names and
    values. Specify the list of filter attributes names and values as:

    - keyword arguments, as in ``(align="right")``, or
    - as an explicit dict with ``**`` operator, when an attribute
      name is also a Python reserved word, as in ``**{"class":"Customer", "align":"right"}``
    - a list of name-value tuples, as in ``(("ns1:class", "Customer"), ("ns2:align", "right"))``

    For attribute names with a namespace prefix, you must use the second
    form.  Attribute names are matched insensitive to upper/lower case.

    If just testing for ``class`` (with or without a namespace), use
    :class:`with_class`.

    To verify that the attribute exists, but without specifying a value,
    pass ``with_attribute.ANY_VALUE`` as the value.

    The next two examples use the following input data and tag parsers:

    .. testcode::

       html = '''
           <div>
           Some text
           <div type="grid">1 4 0 1 0</div>
           <div type="graph">1,3 2,3 1,1</div>
           <div>this has no type</div>
           </div>
       '''
       div,div_end = make_html_tags("div")

    Only match div tag having a type attribute with value "grid":

    .. testcode::

       div_grid = div().set_parse_action(with_attribute(type="grid"))
       grid_expr = div_grid + SkipTo(div | div_end)("body")
       for grid_header in grid_expr.search_string(html):
           print(grid_header.body)

    prints:

    .. testoutput::

       1 4 0 1 0

    Construct a match with any div tag having a type attribute,
    regardless of the value:

    .. testcode::

       div_any_type = div().set_parse_action(
           with_attribute(type=with_attribute.ANY_VALUE)
       )
       div_expr = div_any_type + SkipTo(div | div_end)("body")
       for div_header in div_expr.search_string(html):
           print(div_header.body)

    prints:

    .. testoutput::

       1 4 0 1 0
       1,3 2,3 1,1
    """
    attrs_list: list[tuple[str, str]] = []
    if args:
        attrs_list.extend(args)
    else:
        attrs_list.extend(attr_dict.items())

    def pa(s: str, l: int, tokens: ParseResults) -> None:
        for attrName, attrValue in attrs_list:
            if attrName not in tokens:
                raise ParseException(s, l, "no matching attribute " + attrName)
            if attrValue != with_attribute.ANY_VALUE and tokens[attrName] != attrValue:  # type: ignore [attr-defined]
                raise ParseException(
                    s,
                    l,
                    f"attribute {attrName!r} has value {tokens[attrName]!r}, must be {attrValue!r}",
                )

    return pa


with_attribute.ANY_VALUE = object()  # type: ignore [attr-defined]


def with_class(classname: str, namespace: str = "") -> ParseAction:
    """
    Simplified version of :meth:`with_attribute` when
    matching on a div class - made difficult because ``class`` is
    a reserved word in Python.

    Using similar input data to the :meth:`with_attribute` examples:

    .. testcode::

       html = '''
           <div>
           Some text
           <div class="grid">1 4 0 1 0</div>
           <div class="graph">1,3 2,3 1,1</div>
           <div>this &lt;div&gt; has no class</div>
           </div>
       '''
       div,div_end = make_html_tags("div")

    Only match div tag having the "grid" class:

    .. testcode::

       div_grid = div().set_parse_action(with_class("grid"))
       grid_expr = div_grid + SkipTo(div | div_end)("body")
       for grid_header in grid_expr.search_string(html):
           print(grid_header.body)

    prints:

    .. testoutput::

       1 4 0 1 0

    Construct a match with any div tag having a class attribute,
    regardless of the value:

    .. testcode::

       div_any_type = div().set_parse_action(
           with_class(withAttribute.ANY_VALUE)
       )
       div_expr = div_any_type + SkipTo(div | div_end)("body")
       for div_header in div_expr.search_string(html):
           print(div_header.body)

    prints:

    .. testoutput::

       1 4 0 1 0
       1,3 2,3 1,1
    """
    classattr = f"{namespace}:class" if namespace else "class"
    return with_attribute(**{classattr: classname})


# Compatibility synonyms
# fmt: off
replaceWith = replaced_by_pep8("replaceWith", replace_with)
removeQuotes = replaced_by_pep8("removeQuotes", remove_quotes)
withAttribute = replaced_by_pep8("withAttribute", with_attribute)
withClass = replaced_by_pep8("withClass", with_class)
matchOnlyAtCol = replaced_by_pep8("matchOnlyAtCol", match_only_at_col)
# fmt: on
