import numpy as np
import pytest

from pandas.compat import is_platform_arm

from pandas import (
    DataFrame,
    Series,
)
import pandas._testing as tm
from pandas.util.version import Version

pytestmark = [pytest.mark.single_cpu]

numba = pytest.importorskip("numba")
pytestmark.append(
    pytest.mark.skipif(
        Version(numba.__version__) == Version("0.61") and is_platform_arm(),
        reason=f"Segfaults on ARM platforms with numba {numba.__version__}",
    )
)


@pytest.mark.filterwarnings("ignore")
# Filter warnings when parallel=True and the function can't be parallelized by Numba
class TestEWM:
    def test_invalid_update(self):
        df = DataFrame({"a": range(5), "b": range(5)})
        online_ewm = df.head(2).ewm(0.5).online()
        with pytest.raises(
            ValueError,
            match="Must call mean with update=None first before passing update",
        ):
            online_ewm.mean(update=df.head(1))

    @pytest.mark.slow
    @pytest.mark.parametrize(
        "obj", [DataFrame({"a": range(5), "b": range(5)}), Series(range(5), name="foo")]
    )
    def test_online_vs_non_online_mean(
        self, obj, nogil, parallel, nopython, adjust, ignore_na
    ):
        expected = obj.ewm(0.5, adjust=adjust, ignore_na=ignore_na).mean()
        engine_kwargs = {"nogil": nogil, "parallel": parallel, "nopython": nopython}

        online_ewm = (
            obj.head(2)
            .ewm(0.5, adjust=adjust, ignore_na=ignore_na)
            .online(engine_kwargs=engine_kwargs)
        )
        # Test resetting once
        for _ in range(2):
            result = online_ewm.mean()
            tm.assert_equal(result, expected.head(2))

            result = online_ewm.mean(update=obj.tail(3))
            tm.assert_equal(result, expected.tail(3))

            online_ewm.reset()

    @pytest.mark.xfail(raises=NotImplementedError)
    @pytest.mark.parametrize(
        "obj", [DataFrame({"a": range(5), "b": range(5)}), Series(range(5), name="foo")]
    )
    def test_update_times_mean(
        self, obj, nogil, parallel, nopython, adjust, ignore_na, halflife_with_times
    ):
        times = Series(
            np.array(
                ["2020-01-01", "2020-01-05", "2020-01-07", "2020-01-17", "2020-01-21"],
                dtype="datetime64[ns]",
            )
        )
        expected = obj.ewm(
            0.5,
            adjust=adjust,
            ignore_na=ignore_na,
            times=times,
            halflife=halflife_with_times,
        ).mean()

        engine_kwargs = {"nogil": nogil, "parallel": parallel, "nopython": nopython}
        online_ewm = (
            obj.head(2)
            .ewm(
                0.5,
                adjust=adjust,
                ignore_na=ignore_na,
                times=times.head(2),
                halflife=halflife_with_times,
            )
            .online(engine_kwargs=engine_kwargs)
        )
        # Test resetting once
        for _ in range(2):
            result = online_ewm.mean()
            tm.assert_equal(result, expected.head(2))

            result = online_ewm.mean(update=obj.tail(3), update_times=times.tail(3))
            tm.assert_equal(result, expected.tail(3))

            online_ewm.reset()

    @pytest.mark.parametrize("method", ["aggregate", "std", "corr", "cov", "var"])
    def test_ewm_notimplementederror_raises(self, method):
        ser = Series(range(10))
        kwargs = {}
        if method == "aggregate":
            kwargs["func"] = lambda x: x

        with pytest.raises(NotImplementedError, match=".* is not implemented."):
            getattr(ser.ewm(1).online(), method)(**kwargs)
