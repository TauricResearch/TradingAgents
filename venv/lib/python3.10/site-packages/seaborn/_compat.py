from __future__ import annotations
from typing import Literal

import numpy as np
import pandas as pd
import matplotlib as mpl
from matplotlib.figure import Figure
from seaborn.utils import _version_predates


def norm_from_scale(scale, norm):
    """Produce a Normalize object given a Scale and min/max domain limits."""
    # This is an internal maplotlib function that simplifies things to access
    # It is likely to become part of the matplotlib API at some point:
    # https://github.com/matplotlib/matplotlib/issues/20329
    if isinstance(norm, mpl.colors.Normalize):
        return norm

    if scale is None:
        return None

    if norm is None:
        vmin = vmax = None
    else:
        vmin, vmax = norm  # TODO more helpful error if this fails?

    class ScaledNorm(mpl.colors.Normalize):

        def __call__(self, value, clip=None):
            # From github.com/matplotlib/matplotlib/blob/v3.4.2/lib/matplotlib/colors.py
            # See github.com/matplotlib/matplotlib/tree/v3.4.2/LICENSE
            value, is_scalar = self.process_value(value)
            self.autoscale_None(value)
            if self.vmin > self.vmax:
                raise ValueError("vmin must be less or equal to vmax")
            if self.vmin == self.vmax:
                return np.full_like(value, 0)
            if clip is None:
                clip = self.clip
            if clip:
                value = np.clip(value, self.vmin, self.vmax)
            # ***** Seaborn changes start ****
            t_value = self.transform(value).reshape(np.shape(value))
            t_vmin, t_vmax = self.transform([self.vmin, self.vmax])
            # ***** Seaborn changes end *****
            if not np.isfinite([t_vmin, t_vmax]).all():
                raise ValueError("Invalid vmin or vmax")
            t_value -= t_vmin
            t_value /= (t_vmax - t_vmin)
            t_value = np.ma.masked_invalid(t_value, copy=False)
            return t_value[0] if is_scalar else t_value

    new_norm = ScaledNorm(vmin, vmax)
    new_norm.transform = scale.get_transform().transform

    return new_norm


def get_colormap(name):
    """Handle changes to matplotlib colormap interface in 3.6."""
    try:
        return mpl.colormaps[name]
    except AttributeError:
        return mpl.cm.get_cmap(name)


def register_colormap(name, cmap):
    """Handle changes to matplotlib colormap interface in 3.6."""
    try:
        if name not in mpl.colormaps:
            mpl.colormaps.register(cmap, name=name)
    except AttributeError:
        mpl.cm.register_cmap(name, cmap)


def set_layout_engine(
    fig: Figure,
    engine: Literal["constrained", "compressed", "tight", "none"],
) -> None:
    """Handle changes to auto layout engine interface in 3.6"""
    if hasattr(fig, "set_layout_engine"):
        fig.set_layout_engine(engine)
    else:
        # _version_predates(mpl, 3.6)
        if engine == "tight":
            fig.set_tight_layout(True)  # type: ignore  # predates typing
        elif engine == "constrained":
            fig.set_constrained_layout(True)  # type: ignore
        elif engine == "none":
            fig.set_tight_layout(False)  # type: ignore
            fig.set_constrained_layout(False)  # type: ignore


def get_layout_engine(fig: Figure) -> mpl.layout_engine.LayoutEngine | None:
    """Handle changes to auto layout engine interface in 3.6"""
    if hasattr(fig, "get_layout_engine"):
        return fig.get_layout_engine()
    else:
        # _version_predates(mpl, 3.6)
        return None


def share_axis(ax0, ax1, which):
    """Handle changes to post-hoc axis sharing."""
    if _version_predates(mpl, "3.5"):
        group = getattr(ax0, f"get_shared_{which}_axes")()
        group.join(ax1, ax0)
    else:
        getattr(ax1, f"share{which}")(ax0)


def get_legend_handles(legend):
    """Handle legendHandles attribute rename."""
    if _version_predates(mpl, "3.7"):
        return legend.legendHandles
    else:
        return legend.legend_handles


def groupby_apply_include_groups(val):
    if _version_predates(pd, "2.2.0"):
        return {}
    return {"include_groups": val}
