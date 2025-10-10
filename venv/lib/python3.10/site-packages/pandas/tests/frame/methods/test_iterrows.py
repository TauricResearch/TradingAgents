from pandas import (
    DataFrame,
    Timedelta,
)


def test_no_overflow_of_freq_and_time_in_dataframe():
    # GH 35665
    df = DataFrame(
        {
            "some_string": ["2222Y3"],
            "time": [Timedelta("0 days 00:00:00.990000")],
        }
    )
    for _, row in df.iterrows():
        assert row.dtype == "object"
