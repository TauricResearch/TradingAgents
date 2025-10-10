import numpy as np

import matplotlib as mpl
from matplotlib import _api
from matplotlib.axes import Axes
import matplotlib.axis as maxis
from matplotlib.patches import Circle
from matplotlib.path import Path
import matplotlib.spines as mspines
from matplotlib.ticker import (
    Formatter, NullLocator, FixedLocator, NullFormatter)
from matplotlib.transforms import Affine2D, BboxTransformTo, Transform


class GeoAxes(Axes):
    """An abstract base class for geographic projections."""

    class ThetaFormatter(Formatter):
        """
        Used to format the theta tick labels.  Converts the native
        unit of radians into degrees and adds a degree symbol.
        """
        def __init__(self, round_to=1.0):
            self._round_to = round_to

        def __call__(self, x, pos=None):
            degrees = round(np.rad2deg(x) / self._round_to) * self._round_to
            return f"{degrees:0.0f}\N{DEGREE SIGN}"

    RESOLUTION = 75

    def _init_axis(self):
        self.xaxis = maxis.XAxis(self, clear=False)
        self.yaxis = maxis.YAxis(self, clear=False)
        self.spines['geo'].register_axis(self.yaxis)

    def clear(self):
        # docstring inherited
        super().clear()

        self.set_longitude_grid(30)
        self.set_latitude_grid(15)
        self.set_longitude_grid_ends(75)
        self.xaxis.set_minor_locator(NullLocator())
        self.yaxis.set_minor_locator(NullLocator())
        self.xaxis.set_ticks_position('none')
        self.yaxis.set_ticks_position('none')
        self.yaxis.set_tick_params(label1On=True)
        # Why do we need to turn on yaxis tick labels, but
        # xaxis tick labels are already on?

        self.grid(mpl.rcParams['axes.grid'])

        Axes.set_xlim(self, -np.pi, np.pi)
        Axes.set_ylim(self, -np.pi / 2.0, np.pi / 2.0)

    def _set_lim_and_transforms(self):
        # A (possibly non-linear) projection on the (already scaled) data
        self.transProjection = self._get_core_transform(self.RESOLUTION)

        self.transAffine = self._get_affine_transform()

        self.transAxes = BboxTransformTo(self.bbox)

        # The complete data transformation stack -- from data all the
        # way to display coordinates
        self.transData = \
            self.transProjection + \
            self.transAffine + \
            self.transAxes

        # This is the transform for longitude ticks.
        self._xaxis_pretransform = \
            Affine2D() \
            .scale(1, self._longitude_cap * 2) \
            .translate(0, -self._longitude_cap)
        self._xaxis_transform = \
            self._xaxis_pretransform + \
            self.transData
        self._xaxis_text1_transform = \
            Affine2D().scale(1, 0) + \
            self.transData + \
            Affine2D().translate(0, 4)
        self._xaxis_text2_transform = \
            Affine2D().scale(1, 0) + \
            self.transData + \
            Affine2D().translate(0, -4)

        # This is the transform for latitude ticks.
        yaxis_stretch = Affine2D().scale(np.pi * 2, 1).translate(-np.pi, 0)
        yaxis_space = Affine2D().scale(1, 1.1)
        self._yaxis_transform = \
            yaxis_stretch + \
            self.transData
        yaxis_text_base = \
            yaxis_stretch + \
            self.transProjection + \
            (yaxis_space +
             self.transAffine +
             self.transAxes)
        self._yaxis_text1_transform = \
            yaxis_text_base + \
            Affine2D().translate(-8, 0)
        self._yaxis_text2_transform = \
            yaxis_text_base + \
            Affine2D().translate(8, 0)

    def _get_affine_transform(self):
        transform = self._get_core_transform(1)
        xscale, _ = transform.transform((np.pi, 0))
        _, yscale = transform.transform((0, np.pi/2))
        return Affine2D() \
            .scale(0.5 / xscale, 0.5 / yscale) \
            .translate(0.5, 0.5)

    def get_xaxis_transform(self, which='grid'):
        _api.check_in_list(['tick1', 'tick2', 'grid'], which=which)
        return self._xaxis_transform

    def get_xaxis_text1_transform(self, pad):
        return self._xaxis_text1_transform, 'bottom', 'center'

    def get_xaxis_text2_transform(self, pad):
        return self._xaxis_text2_transform, 'top', 'center'

    def get_yaxis_transform(self, which='grid'):
        _api.check_in_list(['tick1', 'tick2', 'grid'], which=which)
        return self._yaxis_transform

    def get_yaxis_text1_transform(self, pad):
        return self._yaxis_text1_transform, 'center', 'right'

    def get_yaxis_text2_transform(self, pad):
        return self._yaxis_text2_transform, 'center', 'left'

    def _gen_axes_patch(self):
        return Circle((0.5, 0.5), 0.5)

    def _gen_axes_spines(self):
        return {'geo': mspines.Spine.circular_spine(self, (0.5, 0.5), 0.5)}

    def set_yscale(self, *args, **kwargs):
        if args[0] != 'linear':
            raise NotImplementedError

    set_xscale = set_yscale

    def set_xlim(self, *args, **kwargs):
        """Not supported. Please consider using Cartopy."""
        raise TypeError("Changing axes limits of a geographic projection is "
                        "not supported.  Please consider using Cartopy.")

    set_ylim = set_xlim
    set_xbound = set_xlim
    set_ybound = set_ylim

    def invert_xaxis(self):
        """Not supported. Please consider using Cartopy."""
        raise TypeError("Changing axes limits of a geographic projection is "
                        "not supported.  Please consider using Cartopy.")

    invert_yaxis = invert_xaxis

    def format_coord(self, lon, lat):
        """Return a format string formatting the coordinate."""
        lon, lat = np.rad2deg([lon, lat])
        ns = 'N' if lat >= 0.0 else 'S'
        ew = 'E' if lon >= 0.0 else 'W'
        return ('%f\N{DEGREE SIGN}%s, %f\N{DEGREE SIGN}%s'
                % (abs(lat), ns, abs(lon), ew))

    def set_longitude_grid(self, degrees):
        """
        Set the number of degrees between each longitude grid.
        """
        # Skip -180 and 180, which are the fixed limits.
        grid = np.arange(-180 + degrees, 180, degrees)
        self.xaxis.set_major_locator(FixedLocator(np.deg2rad(grid)))
        self.xaxis.set_major_formatter(self.ThetaFormatter(degrees))

    def set_latitude_grid(self, degrees):
        """
        Set the number of degrees between each latitude grid.
        """
        # Skip -90 and 90, which are the fixed limits.
        grid = np.arange(-90 + degrees, 90, degrees)
        self.yaxis.set_major_locator(FixedLocator(np.deg2rad(grid)))
        self.yaxis.set_major_formatter(self.ThetaFormatter(degrees))

    def set_longitude_grid_ends(self, degrees):
        """
        Set the latitude(s) at which to stop drawing the longitude grids.
        """
        self._longitude_cap = np.deg2rad(degrees)
        self._xaxis_pretransform \
            .clear() \
            .scale(1.0, self._longitude_cap * 2.0) \
            .translate(0.0, -self._longitude_cap)

    def get_data_ratio(self):
        """Return the aspect ratio of the data itself."""
        return 1.0

    ### Interactive panning

    def can_zoom(self):
        """
        Return whether this Axes supports the zoom box button functionality.

        This Axes object does not support interactive zoom box.
        """
        return False

    def can_pan(self):
        """
        Return whether this Axes supports the pan/zoom button functionality.

        This Axes object does not support interactive pan/zoom.
        """
        return False

    def start_pan(self, x, y, button):
        pass

    def end_pan(self):
        pass

    def drag_pan(self, button, key, x, y):
        pass


class _GeoTransform(Transform):
    # Factoring out some common functionality.
    input_dims = output_dims = 2

    def __init__(self, resolution):
        """
        Create a new geographical transform.

        Resolution is the number of steps to interpolate between each input
        line segment to approximate its path in curved space.
        """
        super().__init__()
        self._resolution = resolution

    def __str__(self):
        return f"{type(self).__name__}({self._resolution})"

    def transform_path_non_affine(self, path):
        # docstring inherited
        ipath = path.interpolated(self._resolution)
        return Path(self.transform(ipath.vertices), ipath.codes)


class AitoffAxes(GeoAxes):
    name = 'aitoff'

    class AitoffTransform(_GeoTransform):
        """The base Aitoff transform."""

        def transform_non_affine(self, values):
            # docstring inherited
            longitude, latitude = values.T

            # Pre-compute some values
            half_long = longitude / 2.0
            cos_latitude = np.cos(latitude)

            alpha = np.arccos(cos_latitude * np.cos(half_long))
            sinc_alpha = np.sinc(alpha / np.pi)  # np.sinc is sin(pi*x)/(pi*x).

            x = (cos_latitude * np.sin(half_long)) / sinc_alpha
            y = np.sin(latitude) / sinc_alpha
            return np.column_stack([x, y])

        def inverted(self):
            # docstring inherited
            return AitoffAxes.InvertedAitoffTransform(self._resolution)

    class InvertedAitoffTransform(_GeoTransform):

        def transform_non_affine(self, values):
            # docstring inherited
            # MGDTODO: Math is hard ;(
            return np.full_like(values, np.nan)

        def inverted(self):
            # docstring inherited
            return AitoffAxes.AitoffTransform(self._resolution)

    def __init__(self, *args, **kwargs):
        self._longitude_cap = np.pi / 2.0
        super().__init__(*args, **kwargs)
        self.set_aspect(0.5, adjustable='box', anchor='C')
        self.clear()

    def _get_core_transform(self, resolution):
        return self.AitoffTransform(resolution)


class HammerAxes(GeoAxes):
    name = 'hammer'

    class HammerTransform(_GeoTransform):
        """The base Hammer transform."""

        def transform_non_affine(self, values):
            # docstring inherited
            longitude, latitude = values.T
            half_long = longitude / 2.0
            cos_latitude = np.cos(latitude)
            sqrt2 = np.sqrt(2.0)
            alpha = np.sqrt(1.0 + cos_latitude * np.cos(half_long))
            x = (2.0 * sqrt2) * (cos_latitude * np.sin(half_long)) / alpha
            y = (sqrt2 * np.sin(latitude)) / alpha
            return np.column_stack([x, y])

        def inverted(self):
            # docstring inherited
            return HammerAxes.InvertedHammerTransform(self._resolution)

    class InvertedHammerTransform(_GeoTransform):

        def transform_non_affine(self, values):
            # docstring inherited
            x, y = values.T
            z = np.sqrt(1 - (x / 4) ** 2 - (y / 2) ** 2)
            longitude = 2 * np.arctan((z * x) / (2 * (2 * z ** 2 - 1)))
            latitude = np.arcsin(y*z)
            return np.column_stack([longitude, latitude])

        def inverted(self):
            # docstring inherited
            return HammerAxes.HammerTransform(self._resolution)

    def __init__(self, *args, **kwargs):
        self._longitude_cap = np.pi / 2.0
        super().__init__(*args, **kwargs)
        self.set_aspect(0.5, adjustable='box', anchor='C')
        self.clear()

    def _get_core_transform(self, resolution):
        return self.HammerTransform(resolution)


class MollweideAxes(GeoAxes):
    name = 'mollweide'

    class MollweideTransform(_GeoTransform):
        """The base Mollweide transform."""

        def transform_non_affine(self, values):
            # docstring inherited
            def d(theta):
                delta = (-(theta + np.sin(theta) - pi_sin_l)
                         / (1 + np.cos(theta)))
                return delta, np.abs(delta) > 0.001

            longitude, latitude = values.T

            clat = np.pi/2 - np.abs(latitude)
            ihigh = clat < 0.087  # within 5 degrees of the poles
            ilow = ~ihigh
            aux = np.empty(latitude.shape, dtype=float)

            if ilow.any():  # Newton-Raphson iteration
                pi_sin_l = np.pi * np.sin(latitude[ilow])
                theta = 2.0 * latitude[ilow]
                delta, large_delta = d(theta)
                while np.any(large_delta):
                    theta[large_delta] += delta[large_delta]
                    delta, large_delta = d(theta)
                aux[ilow] = theta / 2

            if ihigh.any():  # Taylor series-based approx. solution
                e = clat[ihigh]
                d = 0.5 * (3 * np.pi * e**2) ** (1.0/3)
                aux[ihigh] = (np.pi/2 - d) * np.sign(latitude[ihigh])

            xy = np.empty(values.shape, dtype=float)
            xy[:, 0] = (2.0 * np.sqrt(2.0) / np.pi) * longitude * np.cos(aux)
            xy[:, 1] = np.sqrt(2.0) * np.sin(aux)

            return xy

        def inverted(self):
            # docstring inherited
            return MollweideAxes.InvertedMollweideTransform(self._resolution)

    class InvertedMollweideTransform(_GeoTransform):

        def transform_non_affine(self, values):
            # docstring inherited
            x, y = values.T
            # from Equations (7, 8) of
            # https://mathworld.wolfram.com/MollweideProjection.html
            theta = np.arcsin(y / np.sqrt(2))
            longitude = (np.pi / (2 * np.sqrt(2))) * x / np.cos(theta)
            latitude = np.arcsin((2 * theta + np.sin(2 * theta)) / np.pi)
            return np.column_stack([longitude, latitude])

        def inverted(self):
            # docstring inherited
            return MollweideAxes.MollweideTransform(self._resolution)

    def __init__(self, *args, **kwargs):
        self._longitude_cap = np.pi / 2.0
        super().__init__(*args, **kwargs)
        self.set_aspect(0.5, adjustable='box', anchor='C')
        self.clear()

    def _get_core_transform(self, resolution):
        return self.MollweideTransform(resolution)


class LambertAxes(GeoAxes):
    name = 'lambert'

    class LambertTransform(_GeoTransform):
        """The base Lambert transform."""

        def __init__(self, center_longitude, center_latitude, resolution):
            """
            Create a new Lambert transform.  Resolution is the number of steps
            to interpolate between each input line segment to approximate its
            path in curved Lambert space.
            """
            _GeoTransform.__init__(self, resolution)
            self._center_longitude = center_longitude
            self._center_latitude = center_latitude

        def transform_non_affine(self, values):
            # docstring inherited
            longitude, latitude = values.T
            clong = self._center_longitude
            clat = self._center_latitude
            cos_lat = np.cos(latitude)
            sin_lat = np.sin(latitude)
            diff_long = longitude - clong
            cos_diff_long = np.cos(diff_long)

            inner_k = np.maximum(  # Prevent divide-by-zero problems
                1 + np.sin(clat)*sin_lat + np.cos(clat)*cos_lat*cos_diff_long,
                1e-15)
            k = np.sqrt(2 / inner_k)
            x = k * cos_lat*np.sin(diff_long)
            y = k * (np.cos(clat)*sin_lat - np.sin(clat)*cos_lat*cos_diff_long)

            return np.column_stack([x, y])

        def inverted(self):
            # docstring inherited
            return LambertAxes.InvertedLambertTransform(
                self._center_longitude,
                self._center_latitude,
                self._resolution)

    class InvertedLambertTransform(_GeoTransform):

        def __init__(self, center_longitude, center_latitude, resolution):
            _GeoTransform.__init__(self, resolution)
            self._center_longitude = center_longitude
            self._center_latitude = center_latitude

        def transform_non_affine(self, values):
            # docstring inherited
            x, y = values.T
            clong = self._center_longitude
            clat = self._center_latitude
            p = np.maximum(np.hypot(x, y), 1e-9)
            c = 2 * np.arcsin(0.5 * p)
            sin_c = np.sin(c)
            cos_c = np.cos(c)

            latitude = np.arcsin(cos_c*np.sin(clat) +
                                 ((y*sin_c*np.cos(clat)) / p))
            longitude = clong + np.arctan(
                (x*sin_c) / (p*np.cos(clat)*cos_c - y*np.sin(clat)*sin_c))

            return np.column_stack([longitude, latitude])

        def inverted(self):
            # docstring inherited
            return LambertAxes.LambertTransform(
                self._center_longitude,
                self._center_latitude,
                self._resolution)

    def __init__(self, *args, center_longitude=0, center_latitude=0, **kwargs):
        self._longitude_cap = np.pi / 2
        self._center_longitude = center_longitude
        self._center_latitude = center_latitude
        super().__init__(*args, **kwargs)
        self.set_aspect('equal', adjustable='box', anchor='C')
        self.clear()

    def clear(self):
        # docstring inherited
        super().clear()
        self.yaxis.set_major_formatter(NullFormatter())

    def _get_core_transform(self, resolution):
        return self.LambertTransform(
            self._center_longitude,
            self._center_latitude,
            resolution)

    def _get_affine_transform(self):
        return Affine2D() \
            .scale(0.25) \
            .translate(0.5, 0.5)
