from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from contourpy._contourpy import CoordinateArray


def simple(
    shape: tuple[int, int], want_mask: bool = False,
) -> tuple[CoordinateArray, CoordinateArray, CoordinateArray | np.ma.MaskedArray[Any, Any]]:
    """Return simple test data consisting of the sum of two gaussians.

    Args:
        shape (tuple(int, int)): 2D shape of data to return.
        want_mask (bool, optional): Whether test data should be masked or not, default ``False``.

    Return:
        Tuple of 3 arrays: ``x``, ``y``, ``z`` test data, ``z`` will be masked if
        ``want_mask=True``.
    """
    ny, nx = shape
    x = np.arange(nx, dtype=np.float64)
    y = np.arange(ny, dtype=np.float64)
    x, y = np.meshgrid(x, y)

    xscale = nx - 1.0
    yscale = ny - 1.0

    # z is sum of 2D gaussians.
    amp = np.asarray([1.0, -1.0, 0.8, -0.9, 0.7])
    mid = np.asarray([[0.4, 0.2], [0.3, 0.8], [0.9, 0.75], [0.7, 0.3], [0.05, 0.7]])
    width = np.asarray([0.4, 0.2, 0.2, 0.2, 0.1])

    z = np.zeros_like(x)
    for i in range(len(amp)):
        z += amp[i]*np.exp(-((x/xscale - mid[i, 0])**2 + (y/yscale - mid[i, 1])**2) / width[i]**2)

    if want_mask:
        mask = np.logical_or(
            ((x/xscale - 1.0)**2 / 0.2 + (y/yscale - 0.0)**2 / 0.1) < 1.0,
            ((x/xscale - 0.2)**2 / 0.02 + (y/yscale - 0.45)**2 / 0.08) < 1.0,
        )
        z = np.ma.array(z, mask=mask)  # type: ignore[no-untyped-call]

    return x, y, z


def random(
    shape: tuple[int, int], seed: int = 2187, mask_fraction: float = 0.0,
) -> tuple[CoordinateArray, CoordinateArray, CoordinateArray | np.ma.MaskedArray[Any, Any]]:
    """Return random test data in the range 0 to 1.

    Args:
        shape (tuple(int, int)): 2D shape of data to return.
        seed (int, optional): Seed for random number generator, default 2187.
        mask_fraction (float, optional): Fraction of elements to mask, default 0.

    Return:
        Tuple of 3 arrays: ``x``, ``y``, ``z`` test data, ``z`` will be masked if
        ``mask_fraction`` is greater than zero.
    """
    ny, nx = shape
    x = np.arange(nx, dtype=np.float64)
    y = np.arange(ny, dtype=np.float64)
    x, y = np.meshgrid(x, y)

    rng = np.random.default_rng(seed)
    z = rng.uniform(size=shape)

    if mask_fraction > 0.0:
        mask_fraction = min(mask_fraction, 0.99)
        mask = rng.uniform(size=shape) < mask_fraction
        z = np.ma.array(z, mask=mask)  # type: ignore[no-untyped-call]

    return x, y, z
