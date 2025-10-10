"""UnitDblConverter module containing class UnitDblConverter."""

import numpy as np

from matplotlib import cbook, units
import matplotlib.projections.polar as polar

__all__ = ['UnitDblConverter']


# A special function for use with the matplotlib FuncFormatter class
# for formatting axes with radian units.
# This was copied from matplotlib example code.
def rad_fn(x, pos=None):
    """Radian function formatter."""
    n = int((x / np.pi) * 2.0 + 0.25)
    if n == 0:
        return str(x)
    elif n == 1:
        return r'$\pi/2$'
    elif n == 2:
        return r'$\pi$'
    elif n % 2 == 0:
        return fr'${n//2}\pi$'
    else:
        return fr'${n}\pi/2$'


class UnitDblConverter(units.ConversionInterface):
    """
    Provides Matplotlib conversion functionality for the Monte UnitDbl class.
    """
    # default for plotting
    defaults = {
       "distance": 'km',
       "angle": 'deg',
       "time": 'sec',
       }

    @staticmethod
    def axisinfo(unit, axis):
        # docstring inherited

        # Delay-load due to circular dependencies.
        import matplotlib.testing.jpl_units as U

        # Check to see if the value used for units is a string unit value
        # or an actual instance of a UnitDbl so that we can use the unit
        # value for the default axis label value.
        if unit:
            label = unit if isinstance(unit, str) else unit.label()
        else:
            label = None

        if label == "deg" and isinstance(axis.axes, polar.PolarAxes):
            # If we want degrees for a polar plot, use the PolarPlotFormatter
            majfmt = polar.PolarAxes.ThetaFormatter()
        else:
            majfmt = U.UnitDblFormatter(useOffset=False)

        return units.AxisInfo(majfmt=majfmt, label=label)

    @staticmethod
    def convert(value, unit, axis):
        # docstring inherited
        if not cbook.is_scalar_or_string(value):
            return [UnitDblConverter.convert(x, unit, axis) for x in value]
        # If no units were specified, then get the default units to use.
        if unit is None:
            unit = UnitDblConverter.default_units(value, axis)
        # Convert the incoming UnitDbl value/values to float/floats
        if isinstance(axis.axes, polar.PolarAxes) and value.type() == "angle":
            # Guarantee that units are radians for polar plots.
            return value.convert("rad")
        return value.convert(unit)

    @staticmethod
    def default_units(value, axis):
        # docstring inherited
        # Determine the default units based on the user preferences set for
        # default units when printing a UnitDbl.
        if cbook.is_scalar_or_string(value):
            return UnitDblConverter.defaults[value.type()]
        else:
            return UnitDblConverter.default_units(value[0], axis)
