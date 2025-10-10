from numbers import Number
import math
import operator
import warnings


__all__ = ["Vector"]


class Vector(tuple):
    """A math-like vector.

    Represents an n-dimensional numeric vector. ``Vector`` objects support
    vector addition and subtraction, scalar multiplication and division,
    negation, rounding, and comparison tests.
    """

    __slots__ = ()

    def __new__(cls, values, keep=False):
        if keep is not False:
            warnings.warn(
                "the 'keep' argument has been deprecated",
                DeprecationWarning,
            )
        if type(values) == Vector:
            # No need to create a new object
            return values
        return super().__new__(cls, values)

    def __repr__(self):
        return f"{self.__class__.__name__}({super().__repr__()})"

    def _vectorOp(self, other, op):
        if isinstance(other, Vector):
            assert len(self) == len(other)
            return self.__class__(op(a, b) for a, b in zip(self, other))
        if isinstance(other, Number):
            return self.__class__(op(v, other) for v in self)
        raise NotImplementedError()

    def _scalarOp(self, other, op):
        if isinstance(other, Number):
            return self.__class__(op(v, other) for v in self)
        raise NotImplementedError()

    def _unaryOp(self, op):
        return self.__class__(op(v) for v in self)

    def __add__(self, other):
        return self._vectorOp(other, operator.add)

    __radd__ = __add__

    def __sub__(self, other):
        return self._vectorOp(other, operator.sub)

    def __rsub__(self, other):
        return self._vectorOp(other, _operator_rsub)

    def __mul__(self, other):
        return self._scalarOp(other, operator.mul)

    __rmul__ = __mul__

    def __truediv__(self, other):
        return self._scalarOp(other, operator.truediv)

    def __rtruediv__(self, other):
        return self._scalarOp(other, _operator_rtruediv)

    def __pos__(self):
        return self._unaryOp(operator.pos)

    def __neg__(self):
        return self._unaryOp(operator.neg)

    def __round__(self, *, round=round):
        return self._unaryOp(round)

    def __eq__(self, other):
        if isinstance(other, list):
            # bw compat Vector([1, 2, 3]) == [1, 2, 3]
            other = tuple(other)
        return super().__eq__(other)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __bool__(self):
        return any(self)

    __nonzero__ = __bool__

    def __abs__(self):
        return math.sqrt(sum(x * x for x in self))

    def length(self):
        """Return the length of the vector. Equivalent to abs(vector)."""
        return abs(self)

    def normalized(self):
        """Return the normalized vector of the vector."""
        return self / abs(self)

    def dot(self, other):
        """Performs vector dot product, returning the sum of
        ``a[0] * b[0], a[1] * b[1], ...``"""
        assert len(self) == len(other)
        return sum(a * b for a, b in zip(self, other))

    # Deprecated methods/properties

    def toInt(self):
        warnings.warn(
            "the 'toInt' method has been deprecated, use round(vector) instead",
            DeprecationWarning,
        )
        return self.__round__()

    @property
    def values(self):
        warnings.warn(
            "the 'values' attribute has been deprecated, use "
            "the vector object itself instead",
            DeprecationWarning,
        )
        return list(self)

    @values.setter
    def values(self, values):
        raise AttributeError(
            "can't set attribute, the 'values' attribute has been deprecated",
        )

    def isclose(self, other: "Vector", **kwargs) -> bool:
        """Return True if the vector is close to another Vector."""
        assert len(self) == len(other)
        return all(math.isclose(a, b, **kwargs) for a, b in zip(self, other))


def _operator_rsub(a, b):
    return operator.sub(b, a)


def _operator_rtruediv(a, b):
    return operator.truediv(b, a)
