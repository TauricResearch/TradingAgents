from mpl_toolkits.axes_grid1.parasite_axes import (
    host_axes_class_factory, parasite_axes_class_factory)
from .axislines import Axes


ParasiteAxes = parasite_axes_class_factory(Axes)
HostAxes = SubplotHost = host_axes_class_factory(Axes)
