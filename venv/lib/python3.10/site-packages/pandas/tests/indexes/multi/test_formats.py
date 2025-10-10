import numpy as np
import pytest

import pandas as pd
from pandas import (
    Index,
    MultiIndex,
)
import pandas._testing as tm


def test_format(idx):
    msg = "MultiIndex.format is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        idx.format()
        idx[:0].format()


def test_format_integer_names():
    index = MultiIndex(
        levels=[[0, 1], [0, 1]], codes=[[0, 0, 1, 1], [0, 1, 0, 1]], names=[0, 1]
    )
    msg = "MultiIndex.format is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        index.format(names=True)


def test_format_sparse_config(idx):
    # GH1538
    msg = "MultiIndex.format is deprecated"
    with pd.option_context("display.multi_sparse", False):
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = idx.format()
    assert result[1] == "foo  two"


def test_format_sparse_display():
    index = MultiIndex(
        levels=[[0, 1], [0, 1], [0, 1], [0]],
        codes=[
            [0, 0, 0, 1, 1, 1],
            [0, 0, 1, 0, 0, 1],
            [0, 1, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 0],
        ],
    )
    msg = "MultiIndex.format is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = index.format()
    assert result[3] == "1  0  0  0"


def test_repr_with_unicode_data():
    with pd.option_context("display.encoding", "UTF-8"):
        d = {"a": ["\u05d0", 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]}
        index = pd.DataFrame(d).set_index(["a", "b"]).index
        assert "\\" not in repr(index)  # we don't want unicode-escaped


def test_repr_roundtrip_raises():
    mi = MultiIndex.from_product([list("ab"), range(3)], names=["first", "second"])
    msg = "Must pass both levels and codes"
    with pytest.raises(TypeError, match=msg):
        eval(repr(mi))


def test_unicode_string_with_unicode():
    d = {"a": ["\u05d0", 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]}
    idx = pd.DataFrame(d).set_index(["a", "b"]).index
    str(idx)


def test_repr_max_seq_item_setting(idx):
    # GH10182
    idx = idx.repeat(50)
    with pd.option_context("display.max_seq_items", None):
        repr(idx)
        assert "..." not in str(idx)


class TestRepr:
    def test_unicode_repr_issues(self):
        levels = [Index(["a/\u03c3", "b/\u03c3", "c/\u03c3"]), Index([0, 1])]
        codes = [np.arange(3).repeat(2), np.tile(np.arange(2), 3)]
        index = MultiIndex(levels=levels, codes=codes)

        repr(index.levels)
        repr(index.get_level_values(1))

    def test_repr_max_seq_items_equal_to_n(self, idx):
        # display.max_seq_items == n
        with pd.option_context("display.max_seq_items", 6):
            result = idx.__repr__()
            expected = """\
MultiIndex([('foo', 'one'),
            ('foo', 'two'),
            ('bar', 'one'),
            ('baz', 'two'),
            ('qux', 'one'),
            ('qux', 'two')],
           names=['first', 'second'])"""
            assert result == expected

    def test_repr(self, idx):
        result = idx[:1].__repr__()
        expected = """\
MultiIndex([('foo', 'one')],
           names=['first', 'second'])"""
        assert result == expected

        result = idx.__repr__()
        expected = """\
MultiIndex([('foo', 'one'),
            ('foo', 'two'),
            ('bar', 'one'),
            ('baz', 'two'),
            ('qux', 'one'),
            ('qux', 'two')],
           names=['first', 'second'])"""
        assert result == expected

        with pd.option_context("display.max_seq_items", 5):
            result = idx.__repr__()
            expected = """\
MultiIndex([('foo', 'one'),
            ('foo', 'two'),
            ...
            ('qux', 'one'),
            ('qux', 'two')],
           names=['first', 'second'], length=6)"""
            assert result == expected

        # display.max_seq_items == 1
        with pd.option_context("display.max_seq_items", 1):
            result = idx.__repr__()
            expected = """\
MultiIndex([...
            ('qux', 'two')],
           names=['first', ...], length=6)"""
            assert result == expected

    def test_rjust(self):
        n = 1000
        ci = pd.CategoricalIndex(list("a" * n) + (["abc"] * n))
        dti = pd.date_range("2000-01-01", freq="s", periods=n * 2)
        mi = MultiIndex.from_arrays([ci, ci.codes + 9, dti], names=["a", "b", "dti"])
        result = mi[:1].__repr__()
        expected = """\
MultiIndex([('a', 9, '2000-01-01 00:00:00')],
           names=['a', 'b', 'dti'])"""
        assert result == expected

        result = mi[::500].__repr__()
        expected = """\
MultiIndex([(  'a',  9, '2000-01-01 00:00:00'),
            (  'a',  9, '2000-01-01 00:08:20'),
            ('abc', 10, '2000-01-01 00:16:40'),
            ('abc', 10, '2000-01-01 00:25:00')],
           names=['a', 'b', 'dti'])"""
        assert result == expected

        result = mi.__repr__()
        expected = """\
MultiIndex([(  'a',  9, '2000-01-01 00:00:00'),
            (  'a',  9, '2000-01-01 00:00:01'),
            (  'a',  9, '2000-01-01 00:00:02'),
            (  'a',  9, '2000-01-01 00:00:03'),
            (  'a',  9, '2000-01-01 00:00:04'),
            (  'a',  9, '2000-01-01 00:00:05'),
            (  'a',  9, '2000-01-01 00:00:06'),
            (  'a',  9, '2000-01-01 00:00:07'),
            (  'a',  9, '2000-01-01 00:00:08'),
            (  'a',  9, '2000-01-01 00:00:09'),
            ...
            ('abc', 10, '2000-01-01 00:33:10'),
            ('abc', 10, '2000-01-01 00:33:11'),
            ('abc', 10, '2000-01-01 00:33:12'),
            ('abc', 10, '2000-01-01 00:33:13'),
            ('abc', 10, '2000-01-01 00:33:14'),
            ('abc', 10, '2000-01-01 00:33:15'),
            ('abc', 10, '2000-01-01 00:33:16'),
            ('abc', 10, '2000-01-01 00:33:17'),
            ('abc', 10, '2000-01-01 00:33:18'),
            ('abc', 10, '2000-01-01 00:33:19')],
           names=['a', 'b', 'dti'], length=2000)"""
        assert result == expected

    def test_tuple_width(self):
        n = 1000
        ci = pd.CategoricalIndex(list("a" * n) + (["abc"] * n))
        dti = pd.date_range("2000-01-01", freq="s", periods=n * 2)
        levels = [ci, ci.codes + 9, dti, dti, dti]
        names = ["a", "b", "dti_1", "dti_2", "dti_3"]
        mi = MultiIndex.from_arrays(levels, names=names)
        result = mi[:1].__repr__()
        expected = """MultiIndex([('a', 9, '2000-01-01 00:00:00', '2000-01-01 00:00:00', ...)],
           names=['a', 'b', 'dti_1', 'dti_2', 'dti_3'])"""  # noqa: E501
        assert result == expected

        result = mi[:10].__repr__()
        expected = """\
MultiIndex([('a', 9, '2000-01-01 00:00:00', '2000-01-01 00:00:00', ...),
            ('a', 9, '2000-01-01 00:00:01', '2000-01-01 00:00:01', ...),
            ('a', 9, '2000-01-01 00:00:02', '2000-01-01 00:00:02', ...),
            ('a', 9, '2000-01-01 00:00:03', '2000-01-01 00:00:03', ...),
            ('a', 9, '2000-01-01 00:00:04', '2000-01-01 00:00:04', ...),
            ('a', 9, '2000-01-01 00:00:05', '2000-01-01 00:00:05', ...),
            ('a', 9, '2000-01-01 00:00:06', '2000-01-01 00:00:06', ...),
            ('a', 9, '2000-01-01 00:00:07', '2000-01-01 00:00:07', ...),
            ('a', 9, '2000-01-01 00:00:08', '2000-01-01 00:00:08', ...),
            ('a', 9, '2000-01-01 00:00:09', '2000-01-01 00:00:09', ...)],
           names=['a', 'b', 'dti_1', 'dti_2', 'dti_3'])"""
        assert result == expected

        result = mi.__repr__()
        expected = """\
MultiIndex([(  'a',  9, '2000-01-01 00:00:00', '2000-01-01 00:00:00', ...),
            (  'a',  9, '2000-01-01 00:00:01', '2000-01-01 00:00:01', ...),
            (  'a',  9, '2000-01-01 00:00:02', '2000-01-01 00:00:02', ...),
            (  'a',  9, '2000-01-01 00:00:03', '2000-01-01 00:00:03', ...),
            (  'a',  9, '2000-01-01 00:00:04', '2000-01-01 00:00:04', ...),
            (  'a',  9, '2000-01-01 00:00:05', '2000-01-01 00:00:05', ...),
            (  'a',  9, '2000-01-01 00:00:06', '2000-01-01 00:00:06', ...),
            (  'a',  9, '2000-01-01 00:00:07', '2000-01-01 00:00:07', ...),
            (  'a',  9, '2000-01-01 00:00:08', '2000-01-01 00:00:08', ...),
            (  'a',  9, '2000-01-01 00:00:09', '2000-01-01 00:00:09', ...),
            ...
            ('abc', 10, '2000-01-01 00:33:10', '2000-01-01 00:33:10', ...),
            ('abc', 10, '2000-01-01 00:33:11', '2000-01-01 00:33:11', ...),
            ('abc', 10, '2000-01-01 00:33:12', '2000-01-01 00:33:12', ...),
            ('abc', 10, '2000-01-01 00:33:13', '2000-01-01 00:33:13', ...),
            ('abc', 10, '2000-01-01 00:33:14', '2000-01-01 00:33:14', ...),
            ('abc', 10, '2000-01-01 00:33:15', '2000-01-01 00:33:15', ...),
            ('abc', 10, '2000-01-01 00:33:16', '2000-01-01 00:33:16', ...),
            ('abc', 10, '2000-01-01 00:33:17', '2000-01-01 00:33:17', ...),
            ('abc', 10, '2000-01-01 00:33:18', '2000-01-01 00:33:18', ...),
            ('abc', 10, '2000-01-01 00:33:19', '2000-01-01 00:33:19', ...)],
           names=['a', 'b', 'dti_1', 'dti_2', 'dti_3'], length=2000)"""
        assert result == expected

    def test_multiindex_long_element(self):
        # Non-regression test towards GH#52960
        data = MultiIndex.from_tuples([("c" * 62,)])

        expected = (
            "MultiIndex([('cccccccccccccccccccccccccccccccccccccccc"
            "cccccccccccccccccccccc',)],\n           )"
        )
        assert str(data) == expected
