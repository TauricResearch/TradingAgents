import pytest

from pandas import (
    DataFrame,
    DatetimeIndex,
    Series,
    _testing as tm,
    date_range,
    errors,
    read_hdf,
)
from pandas.tests.io.pytables.common import (
    _maybe_remove,
    ensure_clean_store,
)

pytestmark = pytest.mark.single_cpu


def test_retain_index_attributes(setup_path, unit):
    # GH 3499, losing frequency info on index recreation
    dti = date_range("2000-1-1", periods=3, freq="h", unit=unit)
    df = DataFrame({"A": Series(range(3), index=dti)})

    with ensure_clean_store(setup_path) as store:
        _maybe_remove(store, "data")
        store.put("data", df, format="table")

        result = store.get("data")
        tm.assert_frame_equal(df, result)

        for attr in ["freq", "tz", "name"]:
            for idx in ["index", "columns"]:
                assert getattr(getattr(df, idx), attr, None) == getattr(
                    getattr(result, idx), attr, None
                )

        dti2 = date_range("2002-1-1", periods=3, freq="D", unit=unit)
        # try to append a table with a different frequency
        with tm.assert_produces_warning(errors.AttributeConflictWarning):
            df2 = DataFrame({"A": Series(range(3), index=dti2)})
            store.append("data", df2)

        assert store.get_storer("data").info["index"]["freq"] is None

        # this is ok
        _maybe_remove(store, "df2")
        dti3 = DatetimeIndex(
            ["2001-01-01", "2001-01-02", "2002-01-01"], dtype=f"M8[{unit}]"
        )
        df2 = DataFrame(
            {
                "A": Series(
                    range(3),
                    index=dti3,
                )
            }
        )
        store.append("df2", df2)
        dti4 = date_range("2002-1-1", periods=3, freq="D", unit=unit)
        df3 = DataFrame({"A": Series(range(3), index=dti4)})
        store.append("df2", df3)


def test_retain_index_attributes2(tmp_path, setup_path):
    path = tmp_path / setup_path

    with tm.assert_produces_warning(errors.AttributeConflictWarning):
        df = DataFrame(
            {"A": Series(range(3), index=date_range("2000-1-1", periods=3, freq="h"))}
        )
        df.to_hdf(path, key="data", mode="w", append=True)
        df2 = DataFrame(
            {"A": Series(range(3), index=date_range("2002-1-1", periods=3, freq="D"))}
        )

        df2.to_hdf(path, key="data", append=True)

        idx = date_range("2000-1-1", periods=3, freq="h")
        idx.name = "foo"
        df = DataFrame({"A": Series(range(3), index=idx)})
        df.to_hdf(path, key="data", mode="w", append=True)

    assert read_hdf(path, key="data").index.name == "foo"

    with tm.assert_produces_warning(errors.AttributeConflictWarning):
        idx2 = date_range("2001-1-1", periods=3, freq="h")
        idx2.name = "bar"
        df2 = DataFrame({"A": Series(range(3), index=idx2)})
        df2.to_hdf(path, key="data", append=True)

    assert read_hdf(path, "data").index.name is None
