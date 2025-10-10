"""EpochConverter module containing class EpochConverter."""

from matplotlib import cbook, units
import matplotlib.dates as date_ticker

__all__ = ['EpochConverter']


class EpochConverter(units.ConversionInterface):
    """
    Provides Matplotlib conversion functionality for Monte Epoch and Duration
    classes.
    """

    jdRef = 1721425.5

    @staticmethod
    def axisinfo(unit, axis):
        # docstring inherited
        majloc = date_ticker.AutoDateLocator()
        majfmt = date_ticker.AutoDateFormatter(majloc)
        return units.AxisInfo(majloc=majloc, majfmt=majfmt, label=unit)

    @staticmethod
    def float2epoch(value, unit):
        """
        Convert a Matplotlib floating-point date into an Epoch of the specified
        units.

        = INPUT VARIABLES
        - value     The Matplotlib floating-point date.
        - unit      The unit system to use for the Epoch.

        = RETURN VALUE
        - Returns the value converted to an Epoch in the specified time system.
        """
        # Delay-load due to circular dependencies.
        import matplotlib.testing.jpl_units as U

        secPastRef = value * 86400.0 * U.UnitDbl(1.0, 'sec')
        return U.Epoch(unit, secPastRef, EpochConverter.jdRef)

    @staticmethod
    def epoch2float(value, unit):
        """
        Convert an Epoch value to a float suitable for plotting as a python
        datetime object.

        = INPUT VARIABLES
        - value    An Epoch or list of Epochs that need to be converted.
        - unit     The units to use for an axis with Epoch data.

        = RETURN VALUE
        - Returns the value parameter converted to floats.
        """
        return value.julianDate(unit) - EpochConverter.jdRef

    @staticmethod
    def duration2float(value):
        """
        Convert a Duration value to a float suitable for plotting as a python
        datetime object.

        = INPUT VARIABLES
        - value    A Duration or list of Durations that need to be converted.

        = RETURN VALUE
        - Returns the value parameter converted to floats.
        """
        return value.seconds() / 86400.0

    @staticmethod
    def convert(value, unit, axis):
        # docstring inherited

        # Delay-load due to circular dependencies.
        import matplotlib.testing.jpl_units as U

        if not cbook.is_scalar_or_string(value):
            return [EpochConverter.convert(x, unit, axis) for x in value]
        if unit is None:
            unit = EpochConverter.default_units(value, axis)
        if isinstance(value, U.Duration):
            return EpochConverter.duration2float(value)
        else:
            return EpochConverter.epoch2float(value, unit)

    @staticmethod
    def default_units(value, axis):
        # docstring inherited
        if cbook.is_scalar_or_string(value):
            return value.frame()
        else:
            return EpochConverter.default_units(value[0], axis)
