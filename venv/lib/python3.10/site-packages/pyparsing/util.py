# util.py
import contextlib
import re
from functools import lru_cache, wraps
import inspect
import itertools
import types
from typing import Callable, Union, Iterable, TypeVar, cast
import warnings

_bslash = chr(92)
C = TypeVar("C", bound=Callable)


class __config_flags:
    """Internal class for defining compatibility and debugging flags"""

    _all_names: list[str] = []
    _fixed_names: list[str] = []
    _type_desc = "configuration"

    @classmethod
    def _set(cls, dname, value):
        if dname in cls._fixed_names:
            warnings.warn(
                f"{cls.__name__}.{dname} {cls._type_desc} is {str(getattr(cls, dname)).upper()}"
                f" and cannot be overridden",
                stacklevel=3,
            )
            return
        if dname in cls._all_names:
            setattr(cls, dname, value)
        else:
            raise ValueError(f"no such {cls._type_desc} {dname!r}")

    enable = classmethod(lambda cls, name: cls._set(name, True))
    disable = classmethod(lambda cls, name: cls._set(name, False))


@lru_cache(maxsize=128)
def col(loc: int, strg: str) -> int:
    """
    Returns current column within a string, counting newlines as line separators.
    The first column is number 1.

    Note: the default parsing behavior is to expand tabs in the input string
    before starting the parsing process.  See
    :meth:`ParserElement.parse_string` for more
    information on parsing strings containing ``<TAB>`` s, and suggested
    methods to maintain a consistent view of the parsed string, the parse
    location, and line and column positions within the parsed string.
    """
    s = strg
    return 1 if 0 < loc < len(s) and s[loc - 1] == "\n" else loc - s.rfind("\n", 0, loc)


@lru_cache(maxsize=128)
def lineno(loc: int, strg: str) -> int:
    """Returns current line number within a string, counting newlines as line separators.
    The first line is number 1.

    Note - the default parsing behavior is to expand tabs in the input string
    before starting the parsing process.  See :meth:`ParserElement.parse_string`
    for more information on parsing strings containing ``<TAB>`` s, and
    suggested methods to maintain a consistent view of the parsed string, the
    parse location, and line and column positions within the parsed string.
    """
    return strg.count("\n", 0, loc) + 1


@lru_cache(maxsize=128)
def line(loc: int, strg: str) -> str:
    """
    Returns the line of text containing loc within a string, counting newlines as line separators.
    """
    last_cr = strg.rfind("\n", 0, loc)
    next_cr = strg.find("\n", loc)
    return strg[last_cr + 1 : next_cr] if next_cr >= 0 else strg[last_cr + 1 :]


class _UnboundedCache:
    def __init__(self):
        cache = {}
        cache_get = cache.get
        self.not_in_cache = not_in_cache = object()

        def get(_, key):
            return cache_get(key, not_in_cache)

        def set_(_, key, value):
            cache[key] = value

        def clear(_):
            cache.clear()

        self.size = None
        self.get = types.MethodType(get, self)
        self.set = types.MethodType(set_, self)
        self.clear = types.MethodType(clear, self)


class _FifoCache:
    def __init__(self, size):
        cache = {}
        self.size = size
        self.not_in_cache = not_in_cache = object()
        cache_get = cache.get
        cache_pop = cache.pop

        def get(_, key):
            return cache_get(key, not_in_cache)

        def set_(_, key, value):
            cache[key] = value
            while len(cache) > size:
                # pop oldest element in cache by getting the first key
                cache_pop(next(iter(cache)))

        def clear(_):
            cache.clear()

        self.get = types.MethodType(get, self)
        self.set = types.MethodType(set_, self)
        self.clear = types.MethodType(clear, self)


class LRUMemo:
    """
    A memoizing mapping that retains `capacity` deleted items

    The memo tracks retained items by their access order; once `capacity` items
    are retained, the least recently used item is discarded.
    """

    def __init__(self, capacity):
        self._capacity = capacity
        self._active = {}
        self._memory = {}

    def __getitem__(self, key):
        try:
            return self._active[key]
        except KeyError:
            self._memory[key] = self._memory.pop(key)
            return self._memory[key]

    def __setitem__(self, key, value):
        self._memory.pop(key, None)
        self._active[key] = value

    def __delitem__(self, key):
        try:
            value = self._active.pop(key)
        except KeyError:
            pass
        else:
            oldest_keys = list(self._memory)[: -(self._capacity + 1)]
            for key_to_delete in oldest_keys:
                self._memory.pop(key_to_delete)
            self._memory[key] = value

    def clear(self):
        self._active.clear()
        self._memory.clear()


class UnboundedMemo(dict):
    """
    A memoizing mapping that retains all deleted items
    """

    def __delitem__(self, key):
        pass


def _escape_regex_range_chars(s: str) -> str:
    # escape these chars: ^-[]
    for c in r"\^-[]":
        s = s.replace(c, _bslash + c)
    s = s.replace("\n", r"\n")
    s = s.replace("\t", r"\t")
    return str(s)


class _GroupConsecutive:
    """
    Used as a callable `key` for itertools.groupby to group
    characters that are consecutive:
    
    .. testcode::

       from itertools import groupby
       from pyparsing.util import _GroupConsecutive

       grouped = groupby("abcdejkmpqrs", key=_GroupConsecutive())
       for index, group in grouped:
           print(tuple([index, list(group)]))

    prints:

    .. testoutput::

       (0, ['a', 'b', 'c', 'd', 'e'])
       (1, ['j', 'k'])
       (2, ['m'])
       (3, ['p', 'q', 'r', 's'])
    """

    def __init__(self) -> None:
        self.prev = 0
        self.counter = itertools.count()
        self.value = -1

    def __call__(self, char: str) -> int:
        c_int = ord(char)
        self.prev, prev = c_int, self.prev
        if c_int - prev > 1:
            self.value = next(self.counter)
        return self.value


def _collapse_string_to_ranges(
    s: Union[str, Iterable[str]], re_escape: bool = True
) -> str:
    r"""
    Take a string or list of single-character strings, and return
    a string of the consecutive characters in that string collapsed
    into groups, as might be used in a regular expression '[a-z]'
    character set::

        'a' -> 'a' -> '[a]'
        'bc' -> 'bc' -> '[bc]'
        'defgh' -> 'd-h' -> '[d-h]'
        'fdgeh' -> 'd-h' -> '[d-h]'
        'jklnpqrtu' -> 'j-lnp-rtu' -> '[j-lnp-rtu]'

    Duplicates get collapsed out::

        'aaa' -> 'a' -> '[a]'
        'bcbccb' -> 'bc' -> '[bc]'
        'defghhgf' -> 'd-h' -> '[d-h]'
        'jklnpqrjjjtu' -> 'j-lnp-rtu' -> '[j-lnp-rtu]'

    Spaces are preserved::

        'ab c' -> ' a-c' -> '[ a-c]'

    Characters that are significant when defining regex ranges
    get escaped::

        'acde[]-' -> r'\-\[\]ac-e' -> r'[\-\[\]ac-e]'
    """

    # Developer notes:
    # - Do not optimize this code assuming that the given input string
    #   or internal lists will be short (such as in loading generators into
    #   lists to make it easier to find the last element); this method is also
    #   used to generate regex ranges for character sets in the pyparsing.unicode
    #   classes, and these can be _very_ long lists of strings

    def escape_re_range_char(c: str) -> str:
        return "\\" + c if c in r"\^-][" else c

    def no_escape_re_range_char(c: str) -> str:
        return c

    if not re_escape:
        escape_re_range_char = no_escape_re_range_char

    ret = []

    # reduce input string to remove duplicates, and put in sorted order
    s_chars: list[str] = sorted(set(s))

    if len(s_chars) > 2:
        # find groups of characters that are consecutive (can be collapsed
        # down to "<first>-<last>")
        for _, chars in itertools.groupby(s_chars, key=_GroupConsecutive()):
            # _ is unimportant, is just used to identify groups
            # chars is an iterator of one or more consecutive characters
            # that comprise the current group
            first = last = next(chars)
            with contextlib.suppress(ValueError):
                *_, last = chars

            if first == last:
                # there was only a single char in this group
                ret.append(escape_re_range_char(first))

            elif last == chr(ord(first) + 1):
                # there were only 2 characters in this group
                #   'a','b' -> 'ab'
                ret.append(f"{escape_re_range_char(first)}{escape_re_range_char(last)}")

            else:
                # there were > 2 characters in this group, make into a range
                #   'c','d','e' -> 'c-e'
                ret.append(
                    f"{escape_re_range_char(first)}-{escape_re_range_char(last)}"
                )
    else:
        # only 1 or 2 chars were given to form into groups
        #   'a' -> ['a']
        #   'bc' -> ['b', 'c']
        #   'dg' -> ['d', 'g']
        # no need to list them with "-", just return as a list
        # (after escaping)
        ret = [escape_re_range_char(c) for c in s_chars]

    return "".join(ret)


def _flatten(ll: Iterable) -> list:
    ret = []
    to_visit = [*ll]
    while to_visit:
        i = to_visit.pop(0)
        if isinstance(i, Iterable) and not isinstance(i, str):
            to_visit[:0] = i
        else:
            ret.append(i)
    return ret


def make_compressed_re(
    word_list: Iterable[str],
    max_level: int = 2,
    *,
    non_capturing_groups: bool = True,
    _level: int = 1,
) -> str:
    """
    Create a regular expression string from a list of words, collapsing by common
    prefixes and optional suffixes.

    Calls itself recursively to build nested sublists for each group of suffixes
    that have a shared prefix.
    """

    def get_suffixes_from_common_prefixes(namelist: list[str]):
        if len(namelist) > 1:
            for prefix, suffixes in itertools.groupby(namelist, key=lambda s: s[:1]):
                yield prefix, sorted([s[1:] for s in suffixes], key=len, reverse=True)
        else:
            yield namelist[0][0], [namelist[0][1:]]

    if _level == 1:
        if not word_list:
            raise ValueError("no words given to make_compressed_re()")

        if "" in word_list:
            raise ValueError("word list cannot contain empty string")
    else:
        # internal recursive call, just return empty string if no words
        if not word_list:
            return ""

    # dedupe the word list
    word_list = list({}.fromkeys(word_list))

    if max_level == 0:
        if any(len(wd) > 1 for wd in word_list):
            return "|".join(
                sorted([re.escape(wd) for wd in word_list], key=len, reverse=True)
            )
        else:
            return f"[{''.join(_escape_regex_range_chars(wd) for wd in word_list)}]"

    ret = []
    sep = ""
    ncgroup = "?:" if non_capturing_groups else ""

    for initial, suffixes in get_suffixes_from_common_prefixes(sorted(word_list)):
        ret.append(sep)
        sep = "|"

        initial = re.escape(initial)

        trailing = ""
        if "" in suffixes:
            trailing = "?"
            suffixes.remove("")

        if len(suffixes) > 1:
            if all(len(s) == 1 for s in suffixes):
                ret.append(
                    f"{initial}[{''.join(_escape_regex_range_chars(s) for s in suffixes)}]{trailing}"
                )
            else:
                if _level < max_level:
                    suffix_re = make_compressed_re(
                        sorted(suffixes),
                        max_level,
                        non_capturing_groups=non_capturing_groups,
                        _level=_level + 1,
                    )
                    ret.append(f"{initial}({ncgroup}{suffix_re}){trailing}")
                else:
                    if all(len(s) == 1 for s in suffixes):
                        ret.append(
                            f"{initial}[{''.join(_escape_regex_range_chars(s) for s in suffixes)}]{trailing}"
                        )
                    else:
                        suffixes.sort(key=len, reverse=True)
                        ret.append(
                            f"{initial}({ncgroup}{'|'.join(re.escape(s) for s in suffixes)}){trailing}"
                        )
        else:
            if suffixes:
                suffix = re.escape(suffixes[0])
                if len(suffix) > 1 and trailing:
                    ret.append(f"{initial}({ncgroup}{suffix}){trailing}")
                else:
                    ret.append(f"{initial}{suffix}{trailing}")
            else:
                ret.append(initial)
    return "".join(ret)


def replaced_by_pep8(compat_name: str, fn: C) -> C:
    # In a future version, uncomment the code in the internal _inner() functions
    # to begin emitting DeprecationWarnings.

    # Unwrap staticmethod/classmethod
    fn = getattr(fn, "__func__", fn)

    # (Presence of 'self' arg in signature is used by explain_exception() methods, so we take
    # some extra steps to add it if present in decorated function.)
    if ["self"] == list(inspect.signature(fn).parameters)[:1]:

        @wraps(fn)
        def _inner(self, *args, **kwargs):
            # warnings.warn(
            #     f"Deprecated - use {fn.__name__}", DeprecationWarning, stacklevel=2
            # )
            return fn(self, *args, **kwargs)

    else:

        @wraps(fn)
        def _inner(*args, **kwargs):
            # warnings.warn(
            #     f"Deprecated - use {fn.__name__}", DeprecationWarning, stacklevel=2
            # )
            return fn(*args, **kwargs)

    _inner.__doc__ = f"""
        .. deprecated:: 3.0.0
           Use :class:`{fn.__name__}` instead
        """
    _inner.__name__ = compat_name
    _inner.__annotations__ = fn.__annotations__
    if isinstance(fn, types.FunctionType):
        _inner.__kwdefaults__ = fn.__kwdefaults__  # type: ignore [attr-defined]
    elif isinstance(fn, type) and hasattr(fn, "__init__"):
        _inner.__kwdefaults__ = fn.__init__.__kwdefaults__  # type: ignore [misc,attr-defined]
    else:
        _inner.__kwdefaults__ = None  # type: ignore [attr-defined]
    _inner.__qualname__ = fn.__qualname__
    return cast(C, _inner)
