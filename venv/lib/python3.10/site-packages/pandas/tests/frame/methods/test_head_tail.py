import numpy as np

from pandas import DataFrame
import pandas._testing as tm


def test_head_tail_generic(index, frame_or_series):
    # GH#5370

    ndim = 2 if frame_or_series is DataFrame else 1
    shape = (len(index),) * ndim
    vals = np.random.default_rng(2).standard_normal(shape)
    obj = frame_or_series(vals, index=index)

    tm.assert_equal(obj.head(), obj.iloc[:5])
    tm.assert_equal(obj.tail(), obj.iloc[-5:])

    # 0-len
    tm.assert_equal(obj.head(0), obj.iloc[0:0])
    tm.assert_equal(obj.tail(0), obj.iloc[0:0])

    # bounded
    tm.assert_equal(obj.head(len(obj) + 1), obj)
    tm.assert_equal(obj.tail(len(obj) + 1), obj)

    # neg index
    tm.assert_equal(obj.head(-3), obj.head(len(index) - 3))
    tm.assert_equal(obj.tail(-3), obj.tail(len(index) - 3))


def test_head_tail(float_frame):
    tm.assert_frame_equal(float_frame.head(), float_frame[:5])
    tm.assert_frame_equal(float_frame.tail(), float_frame[-5:])

    tm.assert_frame_equal(float_frame.head(0), float_frame[0:0])
    tm.assert_frame_equal(float_frame.tail(0), float_frame[0:0])

    tm.assert_frame_equal(float_frame.head(-1), float_frame[:-1])
    tm.assert_frame_equal(float_frame.tail(-1), float_frame[1:])
    tm.assert_frame_equal(float_frame.head(1), float_frame[:1])
    tm.assert_frame_equal(float_frame.tail(1), float_frame[-1:])
    # with a float index
    df = float_frame.copy()
    df.index = np.arange(len(float_frame)) + 0.1
    tm.assert_frame_equal(df.head(), df.iloc[:5])
    tm.assert_frame_equal(df.tail(), df.iloc[-5:])
    tm.assert_frame_equal(df.head(0), df[0:0])
    tm.assert_frame_equal(df.tail(0), df[0:0])
    tm.assert_frame_equal(df.head(-1), df.iloc[:-1])
    tm.assert_frame_equal(df.tail(-1), df.iloc[1:])


def test_head_tail_empty():
    # test empty dataframe
    empty_df = DataFrame()
    tm.assert_frame_equal(empty_df.tail(), empty_df)
    tm.assert_frame_equal(empty_df.head(), empty_df)
