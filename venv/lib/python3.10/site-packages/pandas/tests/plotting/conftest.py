import gc

import numpy as np
import pytest

from pandas import (
    DataFrame,
    to_datetime,
)


@pytest.fixture(autouse=True)
def mpl_cleanup():
    # matplotlib/testing/decorators.py#L24
    # 1) Resets units registry
    # 2) Resets rc_context
    # 3) Closes all figures
    mpl = pytest.importorskip("matplotlib")
    mpl_units = pytest.importorskip("matplotlib.units")
    plt = pytest.importorskip("matplotlib.pyplot")
    orig_units_registry = mpl_units.registry.copy()
    with mpl.rc_context():
        mpl.use("template")
        yield
    mpl_units.registry.clear()
    mpl_units.registry.update(orig_units_registry)
    plt.close("all")
    # https://matplotlib.org/stable/users/prev_whats_new/whats_new_3.6.0.html#garbage-collection-is-no-longer-run-on-figure-close  # noqa: E501
    gc.collect(1)


@pytest.fixture
def hist_df():
    n = 50
    rng = np.random.default_rng(10)
    gender = rng.choice(["Male", "Female"], size=n)
    classroom = rng.choice(["A", "B", "C"], size=n)

    hist_df = DataFrame(
        {
            "gender": gender,
            "classroom": classroom,
            "height": rng.normal(66, 4, size=n),
            "weight": rng.normal(161, 32, size=n),
            "category": rng.integers(4, size=n),
            "datetime": to_datetime(
                rng.integers(
                    812419200000000000,
                    819331200000000000,
                    size=n,
                    dtype=np.int64,
                )
            ),
        }
    )
    return hist_df
