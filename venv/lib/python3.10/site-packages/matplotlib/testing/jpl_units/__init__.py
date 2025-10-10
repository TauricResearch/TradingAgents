"""
A sample set of units for use with testing unit conversion
of Matplotlib routines.  These are used because they use very strict
enforcement of unitized data which will test the entire spectrum of how
unitized data might be used (it is not always meaningful to convert to
a float without specific units given).

UnitDbl is essentially a unitized floating point number.  It has a
minimal set of supported units (enough for testing purposes).  All
of the mathematical operation are provided to fully test any behaviour
that might occur with unitized data.  Remember that unitized data has
rules as to how it can be applied to one another (a value of distance
cannot be added to a value of time).  Thus we need to guard against any
accidental "default" conversion that will strip away the meaning of the
data and render it neutered.

Epoch is different than a UnitDbl of time.  Time is something that can be
measured where an Epoch is a specific moment in time.  Epochs are typically
referenced as an offset from some predetermined epoch.

A difference of two epochs is a Duration.  The distinction between a Duration
and a UnitDbl of time is made because an Epoch can have different frames (or
units).  In the case of our test Epoch class the two allowed frames are 'UTC'
and 'ET' (Note that these are rough estimates provided for testing purposes
and should not be used in production code where accuracy of time frames is
desired).  As such a Duration also has a frame of reference and therefore needs
to be called out as different that a simple measurement of time since a delta-t
in one frame may not be the same in another.
"""

from .Duration import Duration
from .Epoch import Epoch
from .UnitDbl import UnitDbl

from .StrConverter import StrConverter
from .EpochConverter import EpochConverter
from .UnitDblConverter import UnitDblConverter

from .UnitDblFormatter import UnitDblFormatter


__version__ = "1.0"

__all__ = [
            'register',
            'Duration',
            'Epoch',
            'UnitDbl',
            'UnitDblFormatter',
          ]


def register():
    """Register the unit conversion classes with matplotlib."""
    import matplotlib.units as mplU

    mplU.registry[str] = StrConverter()
    mplU.registry[Epoch] = EpochConverter()
    mplU.registry[Duration] = EpochConverter()
    mplU.registry[UnitDbl] = UnitDblConverter()


# Some default unit instances
# Distances
m = UnitDbl(1.0, "m")
km = UnitDbl(1.0, "km")
mile = UnitDbl(1.0, "mile")
# Angles
deg = UnitDbl(1.0, "deg")
rad = UnitDbl(1.0, "rad")
# Time
sec = UnitDbl(1.0, "sec")
min = UnitDbl(1.0, "min")
hr = UnitDbl(1.0, "hour")
day = UnitDbl(24.0, "hour")
sec = UnitDbl(1.0, "sec")
