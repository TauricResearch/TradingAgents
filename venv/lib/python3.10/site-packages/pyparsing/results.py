# results.py

from __future__ import annotations

import collections
from collections.abc import (
    MutableMapping,
    Mapping,
    MutableSequence,
    Iterator,
    Iterable,
)
import pprint
from typing import Any

from .util import replaced_by_pep8


str_type: tuple[type, ...] = (str, bytes)
_generator_type = type((_ for _ in ()))


class _ParseResultsWithOffset:
    tup: tuple[ParseResults, int]
    __slots__ = ["tup"]

    def __init__(self, p1: ParseResults, p2: int) -> None:
        self.tup: tuple[ParseResults, int] = (p1, p2)

    def __getitem__(self, i):
        return self.tup[i]

    def __getstate__(self):
        return self.tup

    def __setstate__(self, *args):
        self.tup = args[0]


class ParseResults:
    """Structured parse results, to provide multiple means of access to
    the parsed data:

    - as a list (``len(results)``)
    - by list index (``results[0], results[1]``, etc.)
    - by attribute (``results.<results_name>`` - see :class:`ParserElement.set_results_name`)

    Example:

    .. testcode::

       integer = Word(nums)
       date_str = (integer.set_results_name("year") + '/'
                   + integer.set_results_name("month") + '/'
                   + integer.set_results_name("day"))
       # equivalent form:
       # date_str = (integer("year") + '/'
       #             + integer("month") + '/'
       #             + integer("day"))

       # parse_string returns a ParseResults object
       result = date_str.parse_string("1999/12/31")

       def test(s, fn=repr):
           print(f"{s} -> {fn(eval(s))}")

       test("list(result)")
       test("result[0]")
       test("result['month']")
       test("result.day")
       test("'month' in result")
       test("'minutes' in result")
       test("result.dump()", str)

    prints:

    .. testoutput::

       list(result) -> ['1999', '/', '12', '/', '31']
       result[0] -> '1999'
       result['month'] -> '12'
       result.day -> '31'
       'month' in result -> True
       'minutes' in result -> False
       result.dump() -> ['1999', '/', '12', '/', '31']
       - day: '31'
       - month: '12'
       - year: '1999'

    """

    _null_values: tuple[Any, ...] = (None, [], ())

    _name: str
    _parent: ParseResults
    _all_names: set[str]
    _modal: bool
    _toklist: list[Any]
    _tokdict: dict[str, Any]

    __slots__ = (
        "_name",
        "_parent",
        "_all_names",
        "_modal",
        "_toklist",
        "_tokdict",
    )

    class List(list):
        """
        Simple wrapper class to distinguish parsed list results that should be preserved
        as actual Python lists, instead of being converted to :class:`ParseResults`:

        .. testcode::

           import pyparsing as pp
           ppc = pp.common

           LBRACK, RBRACK, LPAR, RPAR = pp.Suppress.using_each("[]()")
           element = pp.Forward()
           item = ppc.integer
           item_list = pp.DelimitedList(element)
           element_list = LBRACK + item_list + RBRACK | LPAR + item_list + RPAR
           element <<= item | element_list

           # add parse action to convert from ParseResults
           # to actual Python collection types
           @element_list.add_parse_action
           def as_python_list(t):
               return pp.ParseResults.List(t.as_list())

           element.run_tests('''
               100
               [2,3,4]
               [[2, 1],3,4]
               [(2, 1),3,4]
               (2,3,4)
               ([2, 3], 4)
               ''', post_parse=lambda s, r: (r[0], type(r[0]))
           )

        prints:

        .. testoutput::
           :options: +NORMALIZE_WHITESPACE


           100
           (100, <class 'int'>)

           [2,3,4]
           ([2, 3, 4], <class 'list'>)

           [[2, 1],3,4]
           ([[2, 1], 3, 4], <class 'list'>)

           [(2, 1),3,4]
           ([[2, 1], 3, 4], <class 'list'>)

           (2,3,4)
           ([2, 3, 4], <class 'list'>)

           ([2, 3], 4)
           ([[2, 3], 4], <class 'list'>)

        (Used internally by :class:`Group` when `aslist=True`.)
        """

        def __new__(cls, contained=None):
            if contained is None:
                contained = []

            if not isinstance(contained, list):
                raise TypeError(
                    f"{cls.__name__} may only be constructed with a list, not {type(contained).__name__}"
                )

            return list.__new__(cls)

    def __new__(cls, toklist=None, name=None, **kwargs):
        if isinstance(toklist, ParseResults):
            return toklist
        self = object.__new__(cls)
        self._name = None
        self._parent = None
        self._all_names = set()

        if toklist is None:
            self._toklist = []
        elif isinstance(toklist, (list, _generator_type)):
            self._toklist = (
                [toklist[:]]
                if isinstance(toklist, ParseResults.List)
                else list(toklist)
            )
        else:
            self._toklist = [toklist]
        self._tokdict = dict()
        return self

    # Performance tuning: we construct a *lot* of these, so keep this
    # constructor as small and fast as possible
    def __init__(
        self, toklist=None, name=None, asList=True, modal=True, isinstance=isinstance
    ) -> None:
        self._tokdict: dict[str, _ParseResultsWithOffset]
        self._modal = modal

        if name is None or name == "":
            return

        if isinstance(name, int):
            name = str(name)

        if not modal:
            self._all_names = {name}

        self._name = name

        if toklist in self._null_values:
            return

        if isinstance(toklist, (str_type, type)):
            toklist = [toklist]

        if asList:
            if isinstance(toklist, ParseResults):
                self[name] = _ParseResultsWithOffset(ParseResults(toklist._toklist), 0)
            else:
                self[name] = _ParseResultsWithOffset(ParseResults(toklist[0]), 0)
            self[name]._name = name
            return

        try:
            self[name] = toklist[0]
        except (KeyError, TypeError, IndexError):
            if toklist is not self:
                self[name] = toklist
            else:
                self._name = name

    def __getitem__(self, i):
        if isinstance(i, (int, slice)):
            return self._toklist[i]

        if i not in self._all_names:
            return self._tokdict[i][-1][0]

        return ParseResults([v[0] for v in self._tokdict[i]])

    def __setitem__(self, k, v, isinstance=isinstance):
        if isinstance(v, _ParseResultsWithOffset):
            self._tokdict[k] = self._tokdict.get(k, list()) + [v]
            sub = v[0]
        elif isinstance(k, (int, slice)):
            self._toklist[k] = v
            sub = v
        else:
            self._tokdict[k] = self._tokdict.get(k, []) + [
                _ParseResultsWithOffset(v, 0)
            ]
            sub = v
        if isinstance(sub, ParseResults):
            sub._parent = self

    def __delitem__(self, i):
        if not isinstance(i, (int, slice)):
            del self._tokdict[i]
            return

        mylen = len(self._toklist)
        del self._toklist[i]

        # convert int to slice
        if isinstance(i, int):
            if i < 0:
                i += mylen
            i = slice(i, i + 1)
        # get removed indices
        removed = list(range(*i.indices(mylen)))
        removed.reverse()
        # fixup indices in token dictionary
        for occurrences in self._tokdict.values():
            for j in removed:
                for k, (value, position) in enumerate(occurrences):
                    occurrences[k] = _ParseResultsWithOffset(
                        value, position - (position > j)
                    )

    def __contains__(self, k) -> bool:
        return k in self._tokdict

    def __len__(self) -> int:
        return len(self._toklist)

    def __bool__(self) -> bool:
        return not not (self._toklist or self._tokdict)

    def __iter__(self) -> Iterator:
        return iter(self._toklist)

    def __reversed__(self) -> Iterator:
        return iter(self._toklist[::-1])

    def keys(self):
        return iter(self._tokdict)

    def values(self):
        return (self[k] for k in self.keys())

    def items(self):
        return ((k, self[k]) for k in self.keys())

    def haskeys(self) -> bool:
        """
        Since ``keys()`` returns an iterator, this method is helpful in bypassing
        code that looks for the existence of any defined results names."""
        return not not self._tokdict

    def pop(self, *args, **kwargs):
        """
        Removes and returns item at specified index (default= ``last``).
        Supports both ``list`` and ``dict`` semantics for ``pop()``. If
        passed no argument or an integer argument, it will use ``list``
        semantics and pop tokens from the list of parsed tokens. If passed
        a non-integer argument (most likely a string), it will use ``dict``
        semantics and pop the corresponding value from any defined results
        names. A second default return value argument is supported, just as in
        ``dict.pop()``.

        Example:

        .. doctest::

           >>> numlist = Word(nums)[...]
           >>> print(numlist.parse_string("0 123 321"))
           ['0', '123', '321']

           >>> def remove_first(tokens):
           ...     tokens.pop(0)
           ...
           >>> numlist.add_parse_action(remove_first)
           [W:(0-9)]...
           >>> print(numlist.parse_string("0 123 321"))
           ['123', '321']

           >>> label = Word(alphas)
           >>> patt = label("LABEL") + Word(nums)[1, ...]
           >>> print(patt.parse_string("AAB 123 321").dump())
           ['AAB', '123', '321']
           - LABEL: 'AAB'

           >>> # Use pop() in a parse action to remove named result
           >>> # (note that corresponding value is not
           >>> # removed from list form of results)
           >>> def remove_LABEL(tokens):
           ...     tokens.pop("LABEL")
           ...     return tokens
           ...
           >>> patt.add_parse_action(remove_LABEL)
           {W:(A-Za-z) {W:(0-9)}...}
           >>> print(patt.parse_string("AAB 123 321").dump())
           ['AAB', '123', '321']

        """
        if not args:
            args = [-1]
        for k, v in kwargs.items():
            if k == "default":
                args = (args[0], v)
            else:
                raise TypeError(f"pop() got an unexpected keyword argument {k!r}")
        if isinstance(args[0], int) or len(args) == 1 or args[0] in self:
            index = args[0]
            ret = self[index]
            del self[index]
            return ret
        else:
            defaultvalue = args[1]
            return defaultvalue

    def get(self, key, default_value=None):
        """
        Returns named result matching the given key, or if there is no
        such name, then returns the given ``default_value`` or ``None`` if no
        ``default_value`` is specified.

        Similar to ``dict.get()``.

        Example:

        .. doctest::

           >>> integer = Word(nums)
           >>> date_str = integer("year") + '/' + integer("month") + '/' + integer("day")

           >>> result = date_str.parse_string("1999/12/31")
           >>> result.get("year")
           '1999'
           >>> result.get("hour", "not specified")
           'not specified'
           >>> result.get("hour")

        """
        if key in self:
            return self[key]
        else:
            return default_value

    def insert(self, index, ins_string):
        """
        Inserts new element at location index in the list of parsed tokens.

        Similar to ``list.insert()``.

        Example:

        .. doctest::

           >>> numlist = Word(nums)[...]
           >>> print(numlist.parse_string("0 123 321"))
           ['0', '123', '321']

           >>> # use a parse action to insert the parse location
           >>> # in the front of the parsed results
           >>> def insert_locn(locn, tokens):
           ...     tokens.insert(0, locn)
           ...
           >>> numlist.add_parse_action(insert_locn)
           [W:(0-9)]...
           >>> print(numlist.parse_string("0 123 321"))
           [0, '0', '123', '321']

        """
        self._toklist.insert(index, ins_string)
        # fixup indices in token dictionary
        for occurrences in self._tokdict.values():
            for k, (value, position) in enumerate(occurrences):
                occurrences[k] = _ParseResultsWithOffset(
                    value, position + (position > index)
                )

    def append(self, item):
        """
        Add single element to end of ``ParseResults`` list of elements.

        Example:

        .. doctest::

           >>> numlist = Word(nums)[...]
           >>> print(numlist.parse_string("0 123 321"))
           ['0', '123', '321']

           >>> # use a parse action to compute the sum of the parsed integers,
           >>> # and add it to the end
           >>> def append_sum(tokens):
           ...     tokens.append(sum(map(int, tokens)))
           ...
           >>> numlist.add_parse_action(append_sum)
           [W:(0-9)]...
           >>> print(numlist.parse_string("0 123 321"))
           ['0', '123', '321', 444]
        """
        self._toklist.append(item)

    def extend(self, itemseq):
        """
        Add sequence of elements to end of :class:`ParseResults` list of elements.

        Example:

        .. testcode::

           patt = Word(alphas)[1, ...]

           # use a parse action to append the reverse of the matched strings,
           # to make a palindrome
           def make_palindrome(tokens):
               tokens.extend(reversed([t[::-1] for t in tokens]))
               return ''.join(tokens)

           patt.add_parse_action(make_palindrome)
           print(patt.parse_string("lskdj sdlkjf lksd"))

        prints:

        .. testoutput::

           ['lskdjsdlkjflksddsklfjkldsjdksl']
        """
        if isinstance(itemseq, ParseResults):
            self.__iadd__(itemseq)
        else:
            self._toklist.extend(itemseq)

    def clear(self):
        """
        Clear all elements and results names.
        """
        del self._toklist[:]
        self._tokdict.clear()

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            if name.startswith("__"):
                raise AttributeError(name)
            return ""

    def __add__(self, other: ParseResults) -> ParseResults:
        ret = self.copy()
        ret += other
        return ret

    def __iadd__(self, other: ParseResults) -> ParseResults:
        if not other:
            return self

        if other._tokdict:
            offset = len(self._toklist)
            addoffset = lambda a: offset if a < 0 else a + offset
            otheritems = other._tokdict.items()
            otherdictitems = [
                (k, _ParseResultsWithOffset(v[0], addoffset(v[1])))
                for k, vlist in otheritems
                for v in vlist
            ]
            for k, v in otherdictitems:
                self[k] = v
                if isinstance(v[0], ParseResults):
                    v[0]._parent = self

        self._toklist += other._toklist
        self._all_names |= other._all_names
        return self

    def __radd__(self, other) -> ParseResults:
        if isinstance(other, int) and other == 0:
            # useful for merging many ParseResults using sum() builtin
            return self.copy()
        else:
            # this may raise a TypeError - so be it
            return other + self

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._toklist!r}, {self.as_dict()})"

    def __str__(self) -> str:
        return (
            "["
            + ", ".join(
                [
                    str(i) if isinstance(i, ParseResults) else repr(i)
                    for i in self._toklist
                ]
            )
            + "]"
        )

    def _asStringList(self, sep=""):
        out = []
        for item in self._toklist:
            if out and sep:
                out.append(sep)
            if isinstance(item, ParseResults):
                out += item._asStringList()
            else:
                out.append(str(item))
        return out

    def as_list(self, *, flatten: bool = False) -> list:
        """
        Returns the parse results as a nested list of matching tokens, all converted to strings.
        If ``flatten`` is True, all the nesting levels in the returned list are collapsed.

        Example:

        .. doctest::

           >>> patt = Word(alphas)[1, ...]
           >>> result = patt.parse_string("sldkj lsdkj sldkj")
           >>> # even though the result prints in string-like form,
           >>> # it is actually a pyparsing ParseResults
           >>> type(result)
           <class 'pyparsing.results.ParseResults'>
           >>> print(result)
           ['sldkj', 'lsdkj', 'sldkj']

        .. doctest::

           >>> # Use as_list() to create an actual list
           >>> result_list = result.as_list()
           >>> type(result_list)
           <class 'list'>
           >>> print(result_list)
           ['sldkj', 'lsdkj', 'sldkj']
        
        .. versionchanged:: 3.2.0
           New ``flatten`` argument.
        """

        def flattened(pr):
            to_visit = collections.deque([*self])
            while to_visit:
                to_do = to_visit.popleft()
                if isinstance(to_do, ParseResults):
                    to_visit.extendleft(to_do[::-1])
                else:
                    yield to_do

        if flatten:
            return [*flattened(self)]
        else:
            return [
                res.as_list() if isinstance(res, ParseResults) else res
                for res in self._toklist
            ]

    def as_dict(self) -> dict:
        """
        Returns the named parse results as a nested dictionary.

        Example:

        .. doctest::

           >>> integer = pp.Word(pp.nums)
           >>> date_str = integer("year") + '/' + integer("month") + '/' + integer("day")

           >>> result = date_str.parse_string('1999/12/31')
           >>> type(result)
           <class 'pyparsing.results.ParseResults'>
           >>> result
           ParseResults(['1999', '/', '12', '/', '31'], {'year': '1999', 'month': '12', 'day': '31'})

           >>> result_dict = result.as_dict()
           >>> type(result_dict)
           <class 'dict'>
           >>> result_dict
           {'year': '1999', 'month': '12', 'day': '31'}

           >>> # even though a ParseResults supports dict-like access,
           >>> # sometime you just need to have a dict
           >>> import json
           >>> print(json.dumps(result))
           Traceback (most recent call last):
           TypeError: Object of type ParseResults is not JSON serializable
           >>> print(json.dumps(result.as_dict()))
           {"year": "1999", "month": "12", "day": "31"}
        """

        def to_item(obj):
            if isinstance(obj, ParseResults):
                return obj.as_dict() if obj.haskeys() else [to_item(v) for v in obj]
            else:
                return obj

        return dict((k, to_item(v)) for k, v in self.items())

    def copy(self) -> ParseResults:
        """
        Returns a new shallow copy of a :class:`ParseResults` object.
        :class:`ParseResults` items contained within the source are
        shared with the copy. Use :meth:`ParseResults.deepcopy` to
        create a copy with its own separate content values.
        """
        ret = ParseResults(self._toklist)
        ret._tokdict = self._tokdict.copy()
        ret._parent = self._parent
        ret._all_names |= self._all_names
        ret._name = self._name
        return ret

    def deepcopy(self) -> ParseResults:
        """
        Returns a new deep copy of a :class:`ParseResults` object.

        .. versionadded:: 3.1.0
        """
        ret = self.copy()
        # replace values with copies if they are of known mutable types
        for i, obj in enumerate(self._toklist):
            if isinstance(obj, ParseResults):
                ret._toklist[i] = obj.deepcopy()
            elif isinstance(obj, (str, bytes)):
                pass
            elif isinstance(obj, MutableMapping):
                ret._toklist[i] = dest = type(obj)()
                for k, v in obj.items():
                    dest[k] = v.deepcopy() if isinstance(v, ParseResults) else v
            elif isinstance(obj, Iterable):
                ret._toklist[i] = type(obj)(
                    v.deepcopy() if isinstance(v, ParseResults) else v for v in obj  # type: ignore[call-arg]
                )
        return ret

    def get_name(self) -> str | None:
        r"""
        Returns the results name for this token expression.

        Useful when several different expressions might match
        at a particular location.

        Example:

        .. testcode::

           integer = Word(nums)
           ssn_expr = Regex(r"\d\d\d-\d\d-\d\d\d\d")
           house_number_expr = Suppress('#') + Word(nums, alphanums)
           user_data = (Group(house_number_expr)("house_number")
                       | Group(ssn_expr)("ssn")
                       | Group(integer)("age"))
           user_info = user_data[1, ...]

           result = user_info.parse_string("22 111-22-3333 #221B")
           for item in result:
               print(item.get_name(), ':', item[0])

        prints:

        .. testoutput::

           age : 22
           ssn : 111-22-3333
           house_number : 221B

        """
        if self._name:
            return self._name
        elif self._parent:
            par: ParseResults = self._parent
            parent_tokdict_items = par._tokdict.items()
            return next(
                (
                    k
                    for k, vlist in parent_tokdict_items
                    for v, loc in vlist
                    if v is self
                ),
                None,
            )
        elif (
            len(self) == 1
            and len(self._tokdict) == 1
            and next(iter(self._tokdict.values()))[0][1] in (0, -1)
        ):
            return next(iter(self._tokdict.keys()))
        else:
            return None

    def dump(self, indent="", full=True, include_list=True, _depth=0) -> str:
        """
        Diagnostic method for listing out the contents of
        a :class:`ParseResults`. Accepts an optional ``indent`` argument so
        that this string can be embedded in a nested display of other data.

        Example:

        .. testcode::

           integer = Word(nums)
           date_str = integer("year") + '/' + integer("month") + '/' + integer("day")

           result = date_str.parse_string('1999/12/31')
           print(result.dump())

        prints:

        .. testoutput::

           ['1999', '/', '12', '/', '31']
           - day: '31'
           - month: '12'
           - year: '1999'
        """
        out = []
        NL = "\n"
        out.append(indent + str(self.as_list()) if include_list else "")

        if not full:
            return "".join(out)

        if self.haskeys():
            items = sorted((str(k), v) for k, v in self.items())
            for k, v in items:
                if out:
                    out.append(NL)
                out.append(f"{indent}{('  ' * _depth)}- {k}: ")
                if not isinstance(v, ParseResults):
                    out.append(repr(v))
                    continue

                if not v:
                    out.append(str(v))
                    continue

                out.append(
                    v.dump(
                        indent=indent,
                        full=full,
                        include_list=include_list,
                        _depth=_depth + 1,
                    )
                )
        if not any(isinstance(vv, ParseResults) for vv in self):
            return "".join(out)

        v = self
        incr = "  "
        nl = "\n"
        for i, vv in enumerate(v):
            if isinstance(vv, ParseResults):
                vv_dump = vv.dump(
                    indent=indent,
                    full=full,
                    include_list=include_list,
                    _depth=_depth + 1,
                )
                out.append(
                    f"{nl}{indent}{incr * _depth}[{i}]:{nl}{indent}{incr * (_depth + 1)}{vv_dump}"
                )
            else:
                out.append(
                    f"{nl}{indent}{incr * _depth}[{i}]:{nl}{indent}{incr * (_depth + 1)}{vv}"
                )

        return "".join(out)

    def pprint(self, *args, **kwargs):
        """
        Pretty-printer for parsed results as a list, using the
        `pprint <https://docs.python.org/3/library/pprint.html>`_ module.
        Accepts additional positional or keyword args as defined for
        `pprint.pprint <https://docs.python.org/3/library/pprint.html#pprint.pprint>`_ .

        Example:

        .. testcode::

           ident = Word(alphas, alphanums)
           num = Word(nums)
           func = Forward()
           term = ident | num | Group('(' + func + ')')
           func <<= ident + Group(Optional(DelimitedList(term)))
           result = func.parse_string("fna a,b,(fnb c,d,200),100")
           result.pprint(width=40)

        prints:

        .. testoutput::

           ['fna',
            ['a',
             'b',
             ['(', 'fnb', ['c', 'd', '200'], ')'],
             '100']]
        """
        pprint.pprint(self.as_list(), *args, **kwargs)

    # add support for pickle protocol
    def __getstate__(self):
        return (
            self._toklist,
            (
                self._tokdict.copy(),
                None,
                self._all_names,
                self._name,
            ),
        )

    def __setstate__(self, state):
        self._toklist, (self._tokdict, par, inAccumNames, self._name) = state
        self._all_names = set(inAccumNames)
        self._parent = None

    def __getnewargs__(self):
        return self._toklist, self._name

    def __dir__(self):
        return dir(type(self)) + list(self.keys())

    @classmethod
    def from_dict(cls, other, name=None) -> ParseResults:
        """
        Helper classmethod to construct a :class:`ParseResults` from a ``dict``, preserving the
        name-value relations as results names. If an optional ``name`` argument is
        given, a nested :class:`ParseResults` will be returned.
        """

        def is_iterable(obj):
            try:
                iter(obj)
            except Exception:
                return False
            # str's are iterable, but in pyparsing, we don't want to iterate over them
            else:
                return not isinstance(obj, str_type)

        ret = cls([])
        for k, v in other.items():
            if isinstance(v, Mapping):
                ret += cls.from_dict(v, name=k)
            else:
                ret += cls([v], name=k, asList=is_iterable(v))
        if name is not None:
            ret = cls([ret], name=name)
        return ret

    asList = as_list
    """
    .. deprecated:: 3.0.0
       use :meth:`as_list`
    """
    asDict = as_dict
    """
    .. deprecated:: 3.0.0
       use :meth:`as_dict`
    """
    getName = get_name
    """
    .. deprecated:: 3.0.0
       use :meth:`get_name`
    """


MutableMapping.register(ParseResults)
MutableSequence.register(ParseResults)
