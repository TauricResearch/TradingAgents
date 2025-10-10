""" common utilities """
from __future__ import annotations

from typing import (
    Any,
    Literal,
)


def _mklbl(prefix: str, n: int):
    return [f"{prefix}{i}" for i in range(n)]


def check_indexing_smoketest_or_raises(
    obj,
    method: Literal["iloc", "loc"],
    key: Any,
    axes: Literal[0, 1] | None = None,
    fails=None,
) -> None:
    if axes is None:
        axes_list = [0, 1]
    else:
        assert axes in [0, 1]
        axes_list = [axes]

    for ax in axes_list:
        if ax < obj.ndim:
            # create a tuple accessor
            new_axes = [slice(None)] * obj.ndim
            new_axes[ax] = key
            axified = tuple(new_axes)
            try:
                getattr(obj, method).__getitem__(axified)
            except (IndexError, TypeError, KeyError) as detail:
                # if we are in fails, the ok, otherwise raise it
                if fails is not None:
                    if isinstance(detail, fails):
                        return
                raise
