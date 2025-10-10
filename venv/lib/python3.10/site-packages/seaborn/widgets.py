import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

try:
    from ipywidgets import interact, FloatSlider, IntSlider
except ImportError:
    def interact(f):
        msg = "Interactive palettes require `ipywidgets`, which is not installed."
        raise ImportError(msg)

from .miscplot import palplot
from .palettes import (color_palette, dark_palette, light_palette,
                       diverging_palette, cubehelix_palette)


__all__ = ["choose_colorbrewer_palette", "choose_cubehelix_palette",
           "choose_dark_palette", "choose_light_palette",
           "choose_diverging_palette"]


def _init_mutable_colormap():
    """Create a matplotlib colormap that will be updated by the widgets."""
    greys = color_palette("Greys", 256)
    cmap = LinearSegmentedColormap.from_list("interactive", greys)
    cmap._init()
    cmap._set_extremes()
    return cmap


def _update_lut(cmap, colors):
    """Change the LUT values in a matplotlib colormap in-place."""
    cmap._lut[:256] = colors
    cmap._set_extremes()


def _show_cmap(cmap):
    """Show a continuous matplotlib colormap."""
    from .rcmod import axes_style  # Avoid circular import
    with axes_style("white"):
        f, ax = plt.subplots(figsize=(8.25, .75))
    ax.set(xticks=[], yticks=[])
    x = np.linspace(0, 1, 256)[np.newaxis, :]
    ax.pcolormesh(x, cmap=cmap)


def choose_colorbrewer_palette(data_type, as_cmap=False):
    """Select a palette from the ColorBrewer set.

    These palettes are built into matplotlib and can be used by name in
    many seaborn functions, or by passing the object returned by this function.

    Parameters
    ----------
    data_type : {'sequential', 'diverging', 'qualitative'}
        This describes the kind of data you want to visualize. See the seaborn
        color palette docs for more information about how to choose this value.
        Note that you can pass substrings (e.g. 'q' for 'qualitative.

    as_cmap : bool
        If True, the return value is a matplotlib colormap rather than a
        list of discrete colors.

    Returns
    -------
    pal or cmap : list of colors or matplotlib colormap
        Object that can be passed to plotting functions.

    See Also
    --------
    dark_palette : Create a sequential palette with dark low values.
    light_palette : Create a sequential palette with bright low values.
    diverging_palette : Create a diverging palette from selected colors.
    cubehelix_palette : Create a sequential palette or colormap using the
                        cubehelix system.


    """
    if data_type.startswith("q") and as_cmap:
        raise ValueError("Qualitative palettes cannot be colormaps.")

    pal = []
    if as_cmap:
        cmap = _init_mutable_colormap()

    if data_type.startswith("s"):
        opts = ["Greys", "Reds", "Greens", "Blues", "Oranges", "Purples",
                "BuGn", "BuPu", "GnBu", "OrRd", "PuBu", "PuRd", "RdPu", "YlGn",
                "PuBuGn", "YlGnBu", "YlOrBr", "YlOrRd"]
        variants = ["regular", "reverse", "dark"]

        @interact
        def choose_sequential(name=opts, n=(2, 18),
                              desat=FloatSlider(min=0, max=1, value=1),
                              variant=variants):
            if variant == "reverse":
                name += "_r"
            elif variant == "dark":
                name += "_d"

            if as_cmap:
                colors = color_palette(name, 256, desat)
                _update_lut(cmap, np.c_[colors, np.ones(256)])
                _show_cmap(cmap)
            else:
                pal[:] = color_palette(name, n, desat)
                palplot(pal)

    elif data_type.startswith("d"):
        opts = ["RdBu", "RdGy", "PRGn", "PiYG", "BrBG",
                "RdYlBu", "RdYlGn", "Spectral"]
        variants = ["regular", "reverse"]

        @interact
        def choose_diverging(name=opts, n=(2, 16),
                             desat=FloatSlider(min=0, max=1, value=1),
                             variant=variants):
            if variant == "reverse":
                name += "_r"
            if as_cmap:
                colors = color_palette(name, 256, desat)
                _update_lut(cmap, np.c_[colors, np.ones(256)])
                _show_cmap(cmap)
            else:
                pal[:] = color_palette(name, n, desat)
                palplot(pal)

    elif data_type.startswith("q"):
        opts = ["Set1", "Set2", "Set3", "Paired", "Accent",
                "Pastel1", "Pastel2", "Dark2"]

        @interact
        def choose_qualitative(name=opts, n=(2, 16),
                               desat=FloatSlider(min=0, max=1, value=1)):
            pal[:] = color_palette(name, n, desat)
            palplot(pal)

    if as_cmap:
        return cmap
    return pal


def choose_dark_palette(input="husl", as_cmap=False):
    """Launch an interactive widget to create a dark sequential palette.

    This corresponds with the :func:`dark_palette` function. This kind
    of palette is good for data that range between relatively uninteresting
    low values and interesting high values.

    Requires IPython 2+ and must be used in the notebook.

    Parameters
    ----------
    input : {'husl', 'hls', 'rgb'}
        Color space for defining the seed value. Note that the default is
        different than the default input for :func:`dark_palette`.
    as_cmap : bool
        If True, the return value is a matplotlib colormap rather than a
        list of discrete colors.

    Returns
    -------
    pal or cmap : list of colors or matplotlib colormap
        Object that can be passed to plotting functions.

    See Also
    --------
    dark_palette : Create a sequential palette with dark low values.
    light_palette : Create a sequential palette with bright low values.
    cubehelix_palette : Create a sequential palette or colormap using the
                        cubehelix system.

    """
    pal = []
    if as_cmap:
        cmap = _init_mutable_colormap()

    if input == "rgb":
        @interact
        def choose_dark_palette_rgb(r=(0., 1.),
                                    g=(0., 1.),
                                    b=(0., 1.),
                                    n=(3, 17)):
            color = r, g, b
            if as_cmap:
                colors = dark_palette(color, 256, input="rgb")
                _update_lut(cmap, colors)
                _show_cmap(cmap)
            else:
                pal[:] = dark_palette(color, n, input="rgb")
                palplot(pal)

    elif input == "hls":
        @interact
        def choose_dark_palette_hls(h=(0., 1.),
                                    l=(0., 1.),  # noqa: E741
                                    s=(0., 1.),
                                    n=(3, 17)):
            color = h, l, s
            if as_cmap:
                colors = dark_palette(color, 256, input="hls")
                _update_lut(cmap, colors)
                _show_cmap(cmap)
            else:
                pal[:] = dark_palette(color, n, input="hls")
                palplot(pal)

    elif input == "husl":
        @interact
        def choose_dark_palette_husl(h=(0, 359),
                                     s=(0, 99),
                                     l=(0, 99),  # noqa: E741
                                     n=(3, 17)):
            color = h, s, l
            if as_cmap:
                colors = dark_palette(color, 256, input="husl")
                _update_lut(cmap, colors)
                _show_cmap(cmap)
            else:
                pal[:] = dark_palette(color, n, input="husl")
                palplot(pal)

    if as_cmap:
        return cmap
    return pal


def choose_light_palette(input="husl", as_cmap=False):
    """Launch an interactive widget to create a light sequential palette.

    This corresponds with the :func:`light_palette` function. This kind
    of palette is good for data that range between relatively uninteresting
    low values and interesting high values.

    Requires IPython 2+ and must be used in the notebook.

    Parameters
    ----------
    input : {'husl', 'hls', 'rgb'}
        Color space for defining the seed value. Note that the default is
        different than the default input for :func:`light_palette`.
    as_cmap : bool
        If True, the return value is a matplotlib colormap rather than a
        list of discrete colors.

    Returns
    -------
    pal or cmap : list of colors or matplotlib colormap
        Object that can be passed to plotting functions.

    See Also
    --------
    light_palette : Create a sequential palette with bright low values.
    dark_palette : Create a sequential palette with dark low values.
    cubehelix_palette : Create a sequential palette or colormap using the
                        cubehelix system.

    """
    pal = []
    if as_cmap:
        cmap = _init_mutable_colormap()

    if input == "rgb":
        @interact
        def choose_light_palette_rgb(r=(0., 1.),
                                     g=(0., 1.),
                                     b=(0., 1.),
                                     n=(3, 17)):
            color = r, g, b
            if as_cmap:
                colors = light_palette(color, 256, input="rgb")
                _update_lut(cmap, colors)
                _show_cmap(cmap)
            else:
                pal[:] = light_palette(color, n, input="rgb")
                palplot(pal)

    elif input == "hls":
        @interact
        def choose_light_palette_hls(h=(0., 1.),
                                     l=(0., 1.),  # noqa: E741
                                     s=(0., 1.),
                                     n=(3, 17)):
            color = h, l, s
            if as_cmap:
                colors = light_palette(color, 256, input="hls")
                _update_lut(cmap, colors)
                _show_cmap(cmap)
            else:
                pal[:] = light_palette(color, n, input="hls")
                palplot(pal)

    elif input == "husl":
        @interact
        def choose_light_palette_husl(h=(0, 359),
                                      s=(0, 99),
                                      l=(0, 99),  # noqa: E741
                                      n=(3, 17)):
            color = h, s, l
            if as_cmap:
                colors = light_palette(color, 256, input="husl")
                _update_lut(cmap, colors)
                _show_cmap(cmap)
            else:
                pal[:] = light_palette(color, n, input="husl")
                palplot(pal)

    if as_cmap:
        return cmap
    return pal


def choose_diverging_palette(as_cmap=False):
    """Launch an interactive widget to choose a diverging color palette.

    This corresponds with the :func:`diverging_palette` function. This kind
    of palette is good for data that range between interesting low values
    and interesting high values with a meaningful midpoint. (For example,
    change scores relative to some baseline value).

    Requires IPython 2+ and must be used in the notebook.

    Parameters
    ----------
    as_cmap : bool
        If True, the return value is a matplotlib colormap rather than a
        list of discrete colors.

    Returns
    -------
    pal or cmap : list of colors or matplotlib colormap
        Object that can be passed to plotting functions.

    See Also
    --------
    diverging_palette : Create a diverging color palette or colormap.
    choose_colorbrewer_palette : Interactively choose palettes from the
                                 colorbrewer set, including diverging palettes.

    """
    pal = []
    if as_cmap:
        cmap = _init_mutable_colormap()

    @interact
    def choose_diverging_palette(
        h_neg=IntSlider(min=0,
                        max=359,
                        value=220),
        h_pos=IntSlider(min=0,
                        max=359,
                        value=10),
        s=IntSlider(min=0, max=99, value=74),
        l=IntSlider(min=0, max=99, value=50),  # noqa: E741
        sep=IntSlider(min=1, max=50, value=10),
        n=(2, 16),
        center=["light", "dark"]
    ):
        if as_cmap:
            colors = diverging_palette(h_neg, h_pos, s, l, sep, 256, center)
            _update_lut(cmap, colors)
            _show_cmap(cmap)
        else:
            pal[:] = diverging_palette(h_neg, h_pos, s, l, sep, n, center)
            palplot(pal)

    if as_cmap:
        return cmap
    return pal


def choose_cubehelix_palette(as_cmap=False):
    """Launch an interactive widget to create a sequential cubehelix palette.

    This corresponds with the :func:`cubehelix_palette` function. This kind
    of palette is good for data that range between relatively uninteresting
    low values and interesting high values. The cubehelix system allows the
    palette to have more hue variance across the range, which can be helpful
    for distinguishing a wider range of values.

    Requires IPython 2+ and must be used in the notebook.

    Parameters
    ----------
    as_cmap : bool
        If True, the return value is a matplotlib colormap rather than a
        list of discrete colors.

    Returns
    -------
    pal or cmap : list of colors or matplotlib colormap
        Object that can be passed to plotting functions.

    See Also
    --------
    cubehelix_palette : Create a sequential palette or colormap using the
                        cubehelix system.

    """
    pal = []
    if as_cmap:
        cmap = _init_mutable_colormap()

    @interact
    def choose_cubehelix(n_colors=IntSlider(min=2, max=16, value=9),
                         start=FloatSlider(min=0, max=3, value=0),
                         rot=FloatSlider(min=-1, max=1, value=.4),
                         gamma=FloatSlider(min=0, max=5, value=1),
                         hue=FloatSlider(min=0, max=1, value=.8),
                         light=FloatSlider(min=0, max=1, value=.85),
                         dark=FloatSlider(min=0, max=1, value=.15),
                         reverse=False):

        if as_cmap:
            colors = cubehelix_palette(256, start, rot, gamma,
                                       hue, light, dark, reverse)
            _update_lut(cmap, np.c_[colors, np.ones(256)])
            _show_cmap(cmap)
        else:
            pal[:] = cubehelix_palette(n_colors, start, rot, gamma,
                                       hue, light, dark, reverse)
            palplot(pal)

    if as_cmap:
        return cmap
    return pal
