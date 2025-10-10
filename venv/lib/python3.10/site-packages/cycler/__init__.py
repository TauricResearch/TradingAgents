"""
Cycler
======

Cycling through combinations of values, producing dictionaries.

You can add cyclers::

    from cycler import cycler
    cc = (cycler(color=list('rgb')) +
          cycler(linestyle=['-', '--', '-.']))
    for d in cc:
        print(d)

Results in::

    {'color': 'r', 'linestyle': '-'}
    {'color': 'g', 'linestyle': '--'}
    {'color': 'b', 'linestyle': '-.'}


You can multiply cyclers::

    from cycler import cycler
    cc = (cycler(color=list('rgb')) *
          cycler(linestyle=['-', '--', '-.']))
    for d in cc:
        print(d)

Results in::

    {'color': 'r', 'linestyle': '-'}
    {'color': 'r', 'linestyle': '--'}
    {'color': 'r', 'linestyle': '-.'}
    {'color': 'g', 'linestyle': '-'}
    {'color': 'g', 'linestyle': '--'}
    {'color': 'g', 'linestyle': '-.'}
    {'color': 'b', 'linestyle': '-'}
    {'color': 'b', 'linestyle': '--'}
    {'color': 'b', 'linestyle': '-.'}
"""


from __future__ import annotations

from collections.abc import Hashable, Iterable, Generator
import copy
from functools import reduce
from itertools import product, cycle
from operator import mul, add
# Dict, List, Union required for runtime cast calls
from typing import TypeVar, Generic, Callable, Union, Dict, List, Any, overload, cast

__version__ = "0.12.1"

K = TypeVar("K", bound=Hashable)
L = TypeVar("L", bound=Hashable)
V = TypeVar("V")
U = TypeVar("U")


def _process_keys(
    left: Cycler[K, V] | Iterable[dict[K, V]],
    right: Cycler[K, V] | Iterable[dict[K, V]] | None,
) -> set[K]:
    """
    Helper function to compose cycler keys.

    Parameters
    ----------
    left, right : iterable of dictionaries or None
        The cyclers to be composed.

    Returns
    -------
    keys : set
        The keys in the composition of the two cyclers.
    """
    l_peek: dict[K, V] = next(iter(left)) if left != [] else {}
    r_peek: dict[K, V] = next(iter(right)) if right is not None else {}
    l_key: set[K] = set(l_peek.keys())
    r_key: set[K] = set(r_peek.keys())
    if l_key & r_key:
        raise ValueError("Can not compose overlapping cycles")
    return l_key | r_key


def concat(left: Cycler[K, V], right: Cycler[K, U]) -> Cycler[K, V | U]:
    r"""
    Concatenate `Cycler`\s, as if chained using `itertools.chain`.

    The keys must match exactly.

    Examples
    --------
    >>> num = cycler('a', range(3))
    >>> let = cycler('a', 'abc')
    >>> num.concat(let)
    cycler('a', [0, 1, 2, 'a', 'b', 'c'])

    Returns
    -------
    `Cycler`
        The concatenated cycler.
    """
    if left.keys != right.keys:
        raise ValueError(
            "Keys do not match:\n"
            "\tIntersection: {both!r}\n"
            "\tDisjoint: {just_one!r}".format(
                both=left.keys & right.keys, just_one=left.keys ^ right.keys
            )
        )
    _l = cast(Dict[K, List[Union[V, U]]], left.by_key())
    _r = cast(Dict[K, List[Union[V, U]]], right.by_key())
    return reduce(add, (_cycler(k, _l[k] + _r[k]) for k in left.keys))


class Cycler(Generic[K, V]):
    """
    Composable cycles.

    This class has compositions methods:

    ``+``
      for 'inner' products (zip)

    ``+=``
      in-place ``+``

    ``*``
      for outer products (`itertools.product`) and integer multiplication

    ``*=``
      in-place ``*``

    and supports basic slicing via ``[]``.

    Parameters
    ----------
    left, right : Cycler or None
        The 'left' and 'right' cyclers.
    op : func or None
        Function which composes the 'left' and 'right' cyclers.
    """

    def __call__(self):
        return cycle(self)

    def __init__(
        self,
        left: Cycler[K, V] | Iterable[dict[K, V]] | None,
        right: Cycler[K, V] | None = None,
        op: Any = None,
    ):
        """
        Semi-private init.

        Do not use this directly, use `cycler` function instead.
        """
        if isinstance(left, Cycler):
            self._left: Cycler[K, V] | list[dict[K, V]] = Cycler(
                left._left, left._right, left._op
            )
        elif left is not None:
            # Need to copy the dictionary or else that will be a residual
            # mutable that could lead to strange errors
            self._left = [copy.copy(v) for v in left]
        else:
            self._left = []

        if isinstance(right, Cycler):
            self._right: Cycler[K, V] | None = Cycler(
                right._left, right._right, right._op
            )
        else:
            self._right = None

        self._keys: set[K] = _process_keys(self._left, self._right)
        self._op: Any = op

    def __contains__(self, k):
        return k in self._keys

    @property
    def keys(self) -> set[K]:
        """The keys this Cycler knows about."""
        return set(self._keys)

    def change_key(self, old: K, new: K) -> None:
        """
        Change a key in this cycler to a new name.
        Modification is performed in-place.

        Does nothing if the old key is the same as the new key.
        Raises a ValueError if the new key is already a key.
        Raises a KeyError if the old key isn't a key.
        """
        if old == new:
            return
        if new in self._keys:
            raise ValueError(
                f"Can't replace {old} with {new}, {new} is already a key"
            )
        if old not in self._keys:
            raise KeyError(
                f"Can't replace {old} with {new}, {old} is not a key"
            )

        self._keys.remove(old)
        self._keys.add(new)

        if self._right is not None and old in self._right.keys:
            self._right.change_key(old, new)

        # self._left should always be non-None
        # if self._keys is non-empty.
        elif isinstance(self._left, Cycler):
            self._left.change_key(old, new)
        else:
            # It should be completely safe at this point to
            # assume that the old key can be found in each
            # iteration.
            self._left = [{new: entry[old]} for entry in self._left]

    @classmethod
    def _from_iter(cls, label: K, itr: Iterable[V]) -> Cycler[K, V]:
        """
        Class method to create 'base' Cycler objects
        that do not have a 'right' or 'op' and for which
        the 'left' object is not another Cycler.

        Parameters
        ----------
        label : hashable
            The property key.

        itr : iterable
            Finite length iterable of the property values.

        Returns
        -------
        `Cycler`
            New 'base' cycler.
        """
        ret: Cycler[K, V] = cls(None)
        ret._left = list({label: v} for v in itr)
        ret._keys = {label}
        return ret

    def __getitem__(self, key: slice) -> Cycler[K, V]:
        # TODO : maybe add numpy style fancy slicing
        if isinstance(key, slice):
            trans = self.by_key()
            return reduce(add, (_cycler(k, v[key]) for k, v in trans.items()))
        else:
            raise ValueError("Can only use slices with Cycler.__getitem__")

    def __iter__(self) -> Generator[dict[K, V], None, None]:
        if self._right is None:
            for left in self._left:
                yield dict(left)
        else:
            if self._op is None:
                raise TypeError(
                    "Operation cannot be None when both left and right are defined"
                )
            for a, b in self._op(self._left, self._right):
                out = {}
                out.update(a)
                out.update(b)
                yield out

    def __add__(self, other: Cycler[L, U]) -> Cycler[K | L, V | U]:
        """
        Pair-wise combine two equal length cyclers (zip).

        Parameters
        ----------
        other : Cycler
        """
        if len(self) != len(other):
            raise ValueError(
                f"Can only add equal length cycles, not {len(self)} and {len(other)}"
            )
        return Cycler(
            cast(Cycler[Union[K, L], Union[V, U]], self),
            cast(Cycler[Union[K, L], Union[V, U]], other),
            zip
        )

    @overload
    def __mul__(self, other: Cycler[L, U]) -> Cycler[K | L, V | U]:
        ...

    @overload
    def __mul__(self, other: int) -> Cycler[K, V]:
        ...

    def __mul__(self, other):
        """
        Outer product of two cyclers (`itertools.product`) or integer
        multiplication.

        Parameters
        ----------
        other : Cycler or int
        """
        if isinstance(other, Cycler):
            return Cycler(
                cast(Cycler[Union[K, L], Union[V, U]], self),
                cast(Cycler[Union[K, L], Union[V, U]], other),
                product
            )
        elif isinstance(other, int):
            trans = self.by_key()
            return reduce(
                add, (_cycler(k, v * other) for k, v in trans.items())
            )
        else:
            return NotImplemented

    @overload
    def __rmul__(self, other: Cycler[L, U]) -> Cycler[K | L, V | U]:
        ...

    @overload
    def __rmul__(self, other: int) -> Cycler[K, V]:
        ...

    def __rmul__(self, other):
        return self * other

    def __len__(self) -> int:
        op_dict: dict[Callable, Callable[[int, int], int]] = {zip: min, product: mul}
        if self._right is None:
            return len(self._left)
        l_len = len(self._left)
        r_len = len(self._right)
        return op_dict[self._op](l_len, r_len)

    # iadd and imul do not exapand the the type as the returns must be consistent with
    # self, thus they flag as inconsistent with add/mul
    def __iadd__(self, other: Cycler[K, V]) -> Cycler[K, V]:  # type: ignore[misc]
        """
        In-place pair-wise combine two equal length cyclers (zip).

        Parameters
        ----------
        other : Cycler
        """
        if not isinstance(other, Cycler):
            raise TypeError("Cannot += with a non-Cycler object")
        # True shallow copy of self is fine since this is in-place
        old_self = copy.copy(self)
        self._keys = _process_keys(old_self, other)
        self._left = old_self
        self._op = zip
        self._right = Cycler(other._left, other._right, other._op)
        return self

    def __imul__(self, other: Cycler[K, V] | int) -> Cycler[K, V]:  # type: ignore[misc]
        """
        In-place outer product of two cyclers (`itertools.product`).

        Parameters
        ----------
        other : Cycler
        """
        if not isinstance(other, Cycler):
            raise TypeError("Cannot *= with a non-Cycler object")
        # True shallow copy of self is fine since this is in-place
        old_self = copy.copy(self)
        self._keys = _process_keys(old_self, other)
        self._left = old_self
        self._op = product
        self._right = Cycler(other._left, other._right, other._op)
        return self

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Cycler):
            return False
        if len(self) != len(other):
            return False
        if self.keys ^ other.keys:
            return False
        return all(a == b for a, b in zip(self, other))

    __hash__ = None  # type: ignore

    def __repr__(self) -> str:
        op_map = {zip: "+", product: "*"}
        if self._right is None:
            lab = self.keys.pop()
            itr = list(v[lab] for v in self)
            return f"cycler({lab!r}, {itr!r})"
        else:
            op = op_map.get(self._op, "?")
            msg = "({left!r} {op} {right!r})"
            return msg.format(left=self._left, op=op, right=self._right)

    def _repr_html_(self) -> str:
        # an table showing the value of each key through a full cycle
        output = "<table>"
        sorted_keys = sorted(self.keys, key=repr)
        for key in sorted_keys:
            output += f"<th>{key!r}</th>"
        for d in iter(self):
            output += "<tr>"
            for k in sorted_keys:
                output += f"<td>{d[k]!r}</td>"
            output += "</tr>"
        output += "</table>"
        return output

    def by_key(self) -> dict[K, list[V]]:
        """
        Values by key.

        This returns the transposed values of the cycler.  Iterating
        over a `Cycler` yields dicts with a single value for each key,
        this method returns a `dict` of `list` which are the values
        for the given key.

        The returned value can be used to create an equivalent `Cycler`
        using only `+`.

        Returns
        -------
        transpose : dict
            dict of lists of the values for each key.
        """

        # TODO : sort out if this is a bottle neck, if there is a better way
        # and if we care.

        keys = self.keys
        out: dict[K, list[V]] = {k: list() for k in keys}

        for d in self:
            for k in keys:
                out[k].append(d[k])
        return out

    # for back compatibility
    _transpose = by_key

    def simplify(self) -> Cycler[K, V]:
        """
        Simplify the cycler into a sum (but no products) of cyclers.

        Returns
        -------
        simple : Cycler
        """
        # TODO: sort out if it is worth the effort to make sure this is
        # balanced.  Currently it is is
        # (((a + b) + c) + d) vs
        # ((a + b) + (c + d))
        # I would believe that there is some performance implications
        trans = self.by_key()
        return reduce(add, (_cycler(k, v) for k, v in trans.items()))

    concat = concat


@overload
def cycler(arg: Cycler[K, V]) -> Cycler[K, V]:
    ...


@overload
def cycler(**kwargs: Iterable[V]) -> Cycler[str, V]:
    ...


@overload
def cycler(label: K, itr: Iterable[V]) -> Cycler[K, V]:
    ...


def cycler(*args, **kwargs):
    """
    Create a new `Cycler` object from a single positional argument,
    a pair of positional arguments, or the combination of keyword arguments.

    cycler(arg)
    cycler(label1=itr1[, label2=iter2[, ...]])
    cycler(label, itr)

    Form 1 simply copies a given `Cycler` object.

    Form 2 composes a `Cycler` as an inner product of the
    pairs of keyword arguments. In other words, all of the
    iterables are cycled simultaneously, as if through zip().

    Form 3 creates a `Cycler` from a label and an iterable.
    This is useful for when the label cannot be a keyword argument
    (e.g., an integer or a name that has a space in it).

    Parameters
    ----------
    arg : Cycler
        Copy constructor for Cycler (does a shallow copy of iterables).
    label : name
        The property key. In the 2-arg form of the function,
        the label can be any hashable object. In the keyword argument
        form of the function, it must be a valid python identifier.
    itr : iterable
        Finite length iterable of the property values.
        Can be a single-property `Cycler` that would
        be like a key change, but as a shallow copy.

    Returns
    -------
    cycler : Cycler
        New `Cycler` for the given property

    """
    if args and kwargs:
        raise TypeError(
            "cycler() can only accept positional OR keyword arguments -- not both."
        )

    if len(args) == 1:
        if not isinstance(args[0], Cycler):
            raise TypeError(
                "If only one positional argument given, it must "
                "be a Cycler instance."
            )
        return Cycler(args[0])
    elif len(args) == 2:
        return _cycler(*args)
    elif len(args) > 2:
        raise TypeError(
            "Only a single Cycler can be accepted as the lone "
            "positional argument. Use keyword arguments instead."
        )

    if kwargs:
        return reduce(add, (_cycler(k, v) for k, v in kwargs.items()))

    raise TypeError("Must have at least a positional OR keyword arguments")


def _cycler(label: K, itr: Iterable[V]) -> Cycler[K, V]:
    """
    Create a new `Cycler` object from a property name and iterable of values.

    Parameters
    ----------
    label : hashable
        The property key.
    itr : iterable
        Finite length iterable of the property values.

    Returns
    -------
    cycler : Cycler
        New `Cycler` for the given property
    """
    if isinstance(itr, Cycler):
        keys = itr.keys
        if len(keys) != 1:
            msg = "Can not create Cycler from a multi-property Cycler"
            raise ValueError(msg)

        lab = keys.pop()
        # Doesn't need to be a new list because
        # _from_iter() will be creating that new list anyway.
        itr = (v[lab] for v in itr)

    return Cycler._from_iter(label, itr)
