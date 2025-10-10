import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Series,
)
import pandas._testing as tm
from pandas.tests.io.pytables.common import ensure_clean_store

from pandas.io.pytables import read_hdf


def test_complex_fixed(tmp_path, setup_path):
    df = DataFrame(
        np.random.default_rng(2).random((4, 5)).astype(np.complex64),
        index=list("abcd"),
        columns=list("ABCDE"),
    )

    path = tmp_path / setup_path
    df.to_hdf(path, key="df")
    reread = read_hdf(path, "df")
    tm.assert_frame_equal(df, reread)

    df = DataFrame(
        np.random.default_rng(2).random((4, 5)).astype(np.complex128),
        index=list("abcd"),
        columns=list("ABCDE"),
    )
    path = tmp_path / setup_path
    df.to_hdf(path, key="df")
    reread = read_hdf(path, "df")
    tm.assert_frame_equal(df, reread)


def test_complex_table(tmp_path, setup_path):
    df = DataFrame(
        np.random.default_rng(2).random((4, 5)).astype(np.complex64),
        index=list("abcd"),
        columns=list("ABCDE"),
    )

    path = tmp_path / setup_path
    df.to_hdf(path, key="df", format="table")
    reread = read_hdf(path, key="df")
    tm.assert_frame_equal(df, reread)

    df = DataFrame(
        np.random.default_rng(2).random((4, 5)).astype(np.complex128),
        index=list("abcd"),
        columns=list("ABCDE"),
    )

    path = tmp_path / setup_path
    df.to_hdf(path, key="df", format="table", mode="w")
    reread = read_hdf(path, "df")
    tm.assert_frame_equal(df, reread)


def test_complex_mixed_fixed(tmp_path, setup_path):
    complex64 = np.array(
        [1.0 + 1.0j, 1.0 + 1.0j, 1.0 + 1.0j, 1.0 + 1.0j], dtype=np.complex64
    )
    complex128 = np.array(
        [1.0 + 1.0j, 1.0 + 1.0j, 1.0 + 1.0j, 1.0 + 1.0j], dtype=np.complex128
    )
    df = DataFrame(
        {
            "A": [1, 2, 3, 4],
            "B": ["a", "b", "c", "d"],
            "C": complex64,
            "D": complex128,
            "E": [1.0, 2.0, 3.0, 4.0],
        },
        index=list("abcd"),
    )
    path = tmp_path / setup_path
    df.to_hdf(path, key="df")
    reread = read_hdf(path, "df")
    tm.assert_frame_equal(df, reread)


def test_complex_mixed_table(tmp_path, setup_path):
    complex64 = np.array(
        [1.0 + 1.0j, 1.0 + 1.0j, 1.0 + 1.0j, 1.0 + 1.0j], dtype=np.complex64
    )
    complex128 = np.array(
        [1.0 + 1.0j, 1.0 + 1.0j, 1.0 + 1.0j, 1.0 + 1.0j], dtype=np.complex128
    )
    df = DataFrame(
        {
            "A": [1, 2, 3, 4],
            "B": ["a", "b", "c", "d"],
            "C": complex64,
            "D": complex128,
            "E": [1.0, 2.0, 3.0, 4.0],
        },
        index=list("abcd"),
    )

    with ensure_clean_store(setup_path) as store:
        store.append("df", df, data_columns=["A", "B"])
        result = store.select("df", where="A>2")
        tm.assert_frame_equal(df.loc[df.A > 2], result)

    path = tmp_path / setup_path
    df.to_hdf(path, key="df", format="table")
    reread = read_hdf(path, "df")
    tm.assert_frame_equal(df, reread)


def test_complex_across_dimensions_fixed(tmp_path, setup_path):
    complex128 = np.array([1.0 + 1.0j, 1.0 + 1.0j, 1.0 + 1.0j, 1.0 + 1.0j])
    s = Series(complex128, index=list("abcd"))
    df = DataFrame({"A": s, "B": s})

    objs = [s, df]
    comps = [tm.assert_series_equal, tm.assert_frame_equal]
    for obj, comp in zip(objs, comps):
        path = tmp_path / setup_path
        obj.to_hdf(path, key="obj", format="fixed")
        reread = read_hdf(path, "obj")
        comp(obj, reread)


def test_complex_across_dimensions(tmp_path, setup_path):
    complex128 = np.array([1.0 + 1.0j, 1.0 + 1.0j, 1.0 + 1.0j, 1.0 + 1.0j])
    s = Series(complex128, index=list("abcd"))
    df = DataFrame({"A": s, "B": s})

    path = tmp_path / setup_path
    df.to_hdf(path, key="obj", format="table")
    reread = read_hdf(path, "obj")
    tm.assert_frame_equal(df, reread)


def test_complex_indexing_error(setup_path):
    complex128 = np.array(
        [1.0 + 1.0j, 1.0 + 1.0j, 1.0 + 1.0j, 1.0 + 1.0j], dtype=np.complex128
    )
    df = DataFrame(
        {"A": [1, 2, 3, 4], "B": ["a", "b", "c", "d"], "C": complex128},
        index=list("abcd"),
    )

    msg = (
        "Columns containing complex values can be stored "
        "but cannot be indexed when using table format. "
        "Either use fixed format, set index=False, "
        "or do not include the columns containing complex "
        "values to data_columns when initializing the table."
    )

    with ensure_clean_store(setup_path) as store:
        with pytest.raises(TypeError, match=msg):
            store.append("df", df, data_columns=["C"])


def test_complex_series_error(tmp_path, setup_path):
    complex128 = np.array([1.0 + 1.0j, 1.0 + 1.0j, 1.0 + 1.0j, 1.0 + 1.0j])
    s = Series(complex128, index=list("abcd"))

    msg = (
        "Columns containing complex values can be stored "
        "but cannot be indexed when using table format. "
        "Either use fixed format, set index=False, "
        "or do not include the columns containing complex "
        "values to data_columns when initializing the table."
    )

    path = tmp_path / setup_path
    with pytest.raises(TypeError, match=msg):
        s.to_hdf(path, key="obj", format="t")

    path = tmp_path / setup_path
    s.to_hdf(path, key="obj", format="t", index=False)
    reread = read_hdf(path, "obj")
    tm.assert_series_equal(s, reread)


def test_complex_append(setup_path):
    df = DataFrame(
        {
            "a": np.random.default_rng(2).standard_normal(100).astype(np.complex128),
            "b": np.random.default_rng(2).standard_normal(100),
        }
    )

    with ensure_clean_store(setup_path) as store:
        store.append("df", df, data_columns=["b"])
        store.append("df", df)
        result = store.select("df")
        tm.assert_frame_equal(pd.concat([df, df], axis=0), result)
