"""UnitDbl module."""

import functools
import operator

from matplotlib import _api


class UnitDbl:
    """Class UnitDbl in development."""

    # Unit conversion table.  Small subset of the full one but enough
    # to test the required functions.  First field is a scale factor to
    # convert the input units to the units of the second field.  Only
    # units in this table are allowed.
    allowed = {
        "m": (0.001, "km"),
        "km": (1, "km"),
        "mile": (1.609344, "km"),

        "rad": (1, "rad"),
        "deg": (1.745329251994330e-02, "rad"),

        "sec": (1, "sec"),
        "min": (60.0, "sec"),
        "hour": (3600, "sec"),
        }

    _types = {
        "km": "distance",
        "rad": "angle",
        "sec": "time",
        }

    def __init__(self, value, units):
        """
        Create a new UnitDbl object.

        Units are internally converted to km, rad, and sec.  The only
        valid inputs for units are [m, km, mile, rad, deg, sec, min, hour].

        The field UnitDbl.value will contain the converted value.  Use
        the convert() method to get a specific type of units back.

        = ERROR CONDITIONS
        - If the input units are not in the allowed list, an error is thrown.

        = INPUT VARIABLES
        - value     The numeric value of the UnitDbl.
        - units     The string name of the units the value is in.
        """
        data = _api.check_getitem(self.allowed, units=units)
        self._value = float(value * data[0])
        self._units = data[1]

    def convert(self, units):
        """
        Convert the UnitDbl to a specific set of units.

        = ERROR CONDITIONS
        - If the input units are not in the allowed list, an error is thrown.

        = INPUT VARIABLES
        - units     The string name of the units to convert to.

        = RETURN VALUE
        - Returns the value of the UnitDbl in the requested units as a floating
          point number.
        """
        if self._units == units:
            return self._value
        data = _api.check_getitem(self.allowed, units=units)
        if self._units != data[1]:
            raise ValueError(f"Error trying to convert to different units.\n"
                             f"    Invalid conversion requested.\n"
                             f"    UnitDbl: {self}\n"
                             f"    Units:   {units}\n")
        return self._value / data[0]

    def __abs__(self):
        """Return the absolute value of this UnitDbl."""
        return UnitDbl(abs(self._value), self._units)

    def __neg__(self):
        """Return the negative value of this UnitDbl."""
        return UnitDbl(-self._value, self._units)

    def __bool__(self):
        """Return the truth value of a UnitDbl."""
        return bool(self._value)

    def _cmp(self, op, rhs):
        """Check that *self* and *rhs* share units; compare them using *op*."""
        self.checkSameUnits(rhs, "compare")
        return op(self._value, rhs._value)

    __eq__ = functools.partialmethod(_cmp, operator.eq)
    __ne__ = functools.partialmethod(_cmp, operator.ne)
    __lt__ = functools.partialmethod(_cmp, operator.lt)
    __le__ = functools.partialmethod(_cmp, operator.le)
    __gt__ = functools.partialmethod(_cmp, operator.gt)
    __ge__ = functools.partialmethod(_cmp, operator.ge)

    def _binop_unit_unit(self, op, rhs):
        """Check that *self* and *rhs* share units; combine them using *op*."""
        self.checkSameUnits(rhs, op.__name__)
        return UnitDbl(op(self._value, rhs._value), self._units)

    __add__ = functools.partialmethod(_binop_unit_unit, operator.add)
    __sub__ = functools.partialmethod(_binop_unit_unit, operator.sub)

    def _binop_unit_scalar(self, op, scalar):
        """Combine *self* and *scalar* using *op*."""
        return UnitDbl(op(self._value, scalar), self._units)

    __mul__ = functools.partialmethod(_binop_unit_scalar, operator.mul)
    __rmul__ = functools.partialmethod(_binop_unit_scalar, operator.mul)

    def __str__(self):
        """Print the UnitDbl."""
        return f"{self._value:g} *{self._units}"

    def __repr__(self):
        """Print the UnitDbl."""
        return f"UnitDbl({self._value:g}, '{self._units}')"

    def type(self):
        """Return the type of UnitDbl data."""
        return self._types[self._units]

    @staticmethod
    def range(start, stop, step=None):
        """
        Generate a range of UnitDbl objects.

        Similar to the Python range() method.  Returns the range [
        start, stop) at the requested step.  Each element will be a
        UnitDbl object.

        = INPUT VARIABLES
        - start     The starting value of the range.
        - stop      The stop value of the range.
        - step      Optional step to use.  If set to None, then a UnitDbl of
                      value 1 w/ the units of the start is used.

        = RETURN VALUE
        - Returns a list containing the requested UnitDbl values.
        """
        if step is None:
            step = UnitDbl(1, start._units)

        elems = []

        i = 0
        while True:
            d = start + i * step
            if d >= stop:
                break

            elems.append(d)
            i += 1

        return elems

    def checkSameUnits(self, rhs, func):
        """
        Check to see if units are the same.

        = ERROR CONDITIONS
        - If the units of the rhs UnitDbl are not the same as our units,
          an error is thrown.

        = INPUT VARIABLES
        - rhs     The UnitDbl to check for the same units
        - func    The name of the function doing the check.
        """
        if self._units != rhs._units:
            raise ValueError(f"Cannot {func} units of different types.\n"
                             f"LHS: {self._units}\n"
                             f"RHS: {rhs._units}")
