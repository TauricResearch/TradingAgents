import datetime

import numpy as np
import pytest
import pytz

import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    Index,
    Timedelta,
    merge_asof,
    option_context,
    to_datetime,
)
import pandas._testing as tm
from pandas.core.reshape.merge import MergeError


@pytest.fixture(params=["s", "ms", "us", "ns"])
def unit(request):
    """
    Resolution for datetimelike dtypes.
    """
    return request.param


class TestAsOfMerge:
    def prep_data(self, df, dedupe=False):
        if dedupe:
            df = df.drop_duplicates(["time", "ticker"], keep="last").reset_index(
                drop=True
            )
        df.time = to_datetime(df.time)
        return df

    @pytest.fixture
    def trades(self):
        df = pd.DataFrame(
            [
                ["20160525 13:30:00.023", "MSFT", "51.9500", "75", "NASDAQ"],
                ["20160525 13:30:00.038", "MSFT", "51.9500", "155", "NASDAQ"],
                ["20160525 13:30:00.048", "GOOG", "720.7700", "100", "NASDAQ"],
                ["20160525 13:30:00.048", "GOOG", "720.9200", "100", "NASDAQ"],
                ["20160525 13:30:00.048", "GOOG", "720.9300", "200", "NASDAQ"],
                ["20160525 13:30:00.048", "GOOG", "720.9300", "300", "NASDAQ"],
                ["20160525 13:30:00.048", "GOOG", "720.9300", "600", "NASDAQ"],
                ["20160525 13:30:00.048", "GOOG", "720.9300", "44", "NASDAQ"],
                ["20160525 13:30:00.074", "AAPL", "98.6700", "478343", "NASDAQ"],
                ["20160525 13:30:00.075", "AAPL", "98.6700", "478343", "NASDAQ"],
                ["20160525 13:30:00.075", "AAPL", "98.6600", "6", "NASDAQ"],
                ["20160525 13:30:00.075", "AAPL", "98.6500", "30", "NASDAQ"],
                ["20160525 13:30:00.075", "AAPL", "98.6500", "75", "NASDAQ"],
                ["20160525 13:30:00.075", "AAPL", "98.6500", "20", "NASDAQ"],
                ["20160525 13:30:00.075", "AAPL", "98.6500", "35", "NASDAQ"],
                ["20160525 13:30:00.075", "AAPL", "98.6500", "10", "NASDAQ"],
                ["20160525 13:30:00.075", "AAPL", "98.5500", "6", "ARCA"],
                ["20160525 13:30:00.075", "AAPL", "98.5500", "6", "ARCA"],
                ["20160525 13:30:00.076", "AAPL", "98.5600", "1000", "ARCA"],
                ["20160525 13:30:00.076", "AAPL", "98.5600", "200", "ARCA"],
                ["20160525 13:30:00.076", "AAPL", "98.5600", "300", "ARCA"],
                ["20160525 13:30:00.076", "AAPL", "98.5600", "400", "ARCA"],
                ["20160525 13:30:00.076", "AAPL", "98.5600", "600", "ARCA"],
                ["20160525 13:30:00.076", "AAPL", "98.5600", "200", "ARCA"],
                ["20160525 13:30:00.078", "MSFT", "51.9500", "783", "NASDAQ"],
                ["20160525 13:30:00.078", "MSFT", "51.9500", "100", "NASDAQ"],
                ["20160525 13:30:00.078", "MSFT", "51.9500", "100", "NASDAQ"],
            ],
            columns="time,ticker,price,quantity,marketCenter".split(","),
        )
        df["price"] = df["price"].astype("float64")
        df["quantity"] = df["quantity"].astype("int64")
        return self.prep_data(df)

    @pytest.fixture
    def quotes(self):
        df = pd.DataFrame(
            [
                ["20160525 13:30:00.023", "GOOG", "720.50", "720.93"],
                ["20160525 13:30:00.023", "MSFT", "51.95", "51.95"],
                ["20160525 13:30:00.041", "MSFT", "51.95", "51.95"],
                ["20160525 13:30:00.048", "GOOG", "720.50", "720.93"],
                ["20160525 13:30:00.048", "GOOG", "720.50", "720.93"],
                ["20160525 13:30:00.048", "GOOG", "720.50", "720.93"],
                ["20160525 13:30:00.048", "GOOG", "720.50", "720.93"],
                ["20160525 13:30:00.072", "GOOG", "720.50", "720.88"],
                ["20160525 13:30:00.075", "AAPL", "98.55", "98.56"],
                ["20160525 13:30:00.076", "AAPL", "98.55", "98.56"],
                ["20160525 13:30:00.076", "AAPL", "98.55", "98.56"],
                ["20160525 13:30:00.076", "AAPL", "98.55", "98.56"],
                ["20160525 13:30:00.078", "MSFT", "51.95", "51.95"],
                ["20160525 13:30:00.078", "MSFT", "51.95", "51.95"],
                ["20160525 13:30:00.078", "MSFT", "51.95", "51.95"],
                ["20160525 13:30:00.078", "MSFT", "51.92", "51.95"],
            ],
            columns="time,ticker,bid,ask".split(","),
        )
        df["bid"] = df["bid"].astype("float64")
        df["ask"] = df["ask"].astype("float64")
        return self.prep_data(df, dedupe=True)

    @pytest.fixture
    def asof(self):
        df = pd.DataFrame(
            [
                [
                    "20160525 13:30:00.023",
                    "MSFT",
                    "51.95",
                    "75",
                    "NASDAQ",
                    "51.95",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.038",
                    "MSFT",
                    "51.95",
                    "155",
                    "NASDAQ",
                    "51.95",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.77",
                    "100",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.92",
                    "100",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "200",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "300",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "600",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "44",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.074",
                    "AAPL",
                    "98.67",
                    "478343",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.67",
                    "478343",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.66",
                    "6",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "30",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "75",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "20",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "35",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "10",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.55",
                    "6",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.55",
                    "6",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "1000",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "200",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "300",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "400",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "600",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "200",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.078",
                    "MSFT",
                    "51.95",
                    "783",
                    "NASDAQ",
                    "51.92",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.078",
                    "MSFT",
                    "51.95",
                    "100",
                    "NASDAQ",
                    "51.92",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.078",
                    "MSFT",
                    "51.95",
                    "100",
                    "NASDAQ",
                    "51.92",
                    "51.95",
                ],
            ],
            columns="time,ticker,price,quantity,marketCenter,bid,ask".split(","),
        )
        df["price"] = df["price"].astype("float64")
        df["quantity"] = df["quantity"].astype("int64")
        df["bid"] = df["bid"].astype("float64")
        df["ask"] = df["ask"].astype("float64")
        return self.prep_data(df)

    @pytest.fixture
    def tolerance(self):
        df = pd.DataFrame(
            [
                [
                    "20160525 13:30:00.023",
                    "MSFT",
                    "51.95",
                    "75",
                    "NASDAQ",
                    "51.95",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.038",
                    "MSFT",
                    "51.95",
                    "155",
                    "NASDAQ",
                    "51.95",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.77",
                    "100",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.92",
                    "100",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "200",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "300",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "600",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "44",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.074",
                    "AAPL",
                    "98.67",
                    "478343",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.67",
                    "478343",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.66",
                    "6",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "30",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "75",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "20",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "35",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "10",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.55",
                    "6",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.55",
                    "6",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "1000",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "200",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "300",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "400",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "600",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "200",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.078",
                    "MSFT",
                    "51.95",
                    "783",
                    "NASDAQ",
                    "51.92",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.078",
                    "MSFT",
                    "51.95",
                    "100",
                    "NASDAQ",
                    "51.92",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.078",
                    "MSFT",
                    "51.95",
                    "100",
                    "NASDAQ",
                    "51.92",
                    "51.95",
                ],
            ],
            columns="time,ticker,price,quantity,marketCenter,bid,ask".split(","),
        )
        df["price"] = df["price"].astype("float64")
        df["quantity"] = df["quantity"].astype("int64")
        df["bid"] = df["bid"].astype("float64")
        df["ask"] = df["ask"].astype("float64")
        return self.prep_data(df)

    @pytest.fixture
    def allow_exact_matches(self, datapath):
        df = pd.DataFrame(
            [
                [
                    "20160525 13:30:00.023",
                    "MSFT",
                    "51.95",
                    "75",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.038",
                    "MSFT",
                    "51.95",
                    "155",
                    "NASDAQ",
                    "51.95",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.77",
                    "100",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.92",
                    "100",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "200",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "300",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "600",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "44",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.074",
                    "AAPL",
                    "98.67",
                    "478343",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.67",
                    "478343",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.66",
                    "6",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "30",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "75",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "20",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "35",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "10",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                ["20160525 13:30:00.075", "AAPL", "98.55", "6", "ARCA", np.nan, np.nan],
                ["20160525 13:30:00.075", "AAPL", "98.55", "6", "ARCA", np.nan, np.nan],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "1000",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "200",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "300",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "400",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "600",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "200",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.078",
                    "MSFT",
                    "51.95",
                    "783",
                    "NASDAQ",
                    "51.95",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.078",
                    "MSFT",
                    "51.95",
                    "100",
                    "NASDAQ",
                    "51.95",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.078",
                    "MSFT",
                    "51.95",
                    "100",
                    "NASDAQ",
                    "51.95",
                    "51.95",
                ],
            ],
            columns="time,ticker,price,quantity,marketCenter,bid,ask".split(","),
        )
        df["price"] = df["price"].astype("float64")
        df["quantity"] = df["quantity"].astype("int64")
        df["bid"] = df["bid"].astype("float64")
        df["ask"] = df["ask"].astype("float64")
        return self.prep_data(df)

    @pytest.fixture
    def allow_exact_matches_and_tolerance(self):
        df = pd.DataFrame(
            [
                [
                    "20160525 13:30:00.023",
                    "MSFT",
                    "51.95",
                    "75",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.038",
                    "MSFT",
                    "51.95",
                    "155",
                    "NASDAQ",
                    "51.95",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.77",
                    "100",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.92",
                    "100",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "200",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "300",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "600",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "44",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.074",
                    "AAPL",
                    "98.67",
                    "478343",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.67",
                    "478343",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.66",
                    "6",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "30",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "75",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "20",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "35",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "10",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                ["20160525 13:30:00.075", "AAPL", "98.55", "6", "ARCA", np.nan, np.nan],
                ["20160525 13:30:00.075", "AAPL", "98.55", "6", "ARCA", np.nan, np.nan],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "1000",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "200",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "300",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "400",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "600",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "200",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.078",
                    "MSFT",
                    "51.95",
                    "783",
                    "NASDAQ",
                    "51.95",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.078",
                    "MSFT",
                    "51.95",
                    "100",
                    "NASDAQ",
                    "51.95",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.078",
                    "MSFT",
                    "51.95",
                    "100",
                    "NASDAQ",
                    "51.95",
                    "51.95",
                ],
            ],
            columns="time,ticker,price,quantity,marketCenter,bid,ask".split(","),
        )
        df["price"] = df["price"].astype("float64")
        df["quantity"] = df["quantity"].astype("int64")
        df["bid"] = df["bid"].astype("float64")
        df["ask"] = df["ask"].astype("float64")
        return self.prep_data(df)

    def test_examples1(self):
        """doc-string examples"""
        left = pd.DataFrame({"a": [1, 5, 10], "left_val": ["a", "b", "c"]})
        right = pd.DataFrame({"a": [1, 2, 3, 6, 7], "right_val": [1, 2, 3, 6, 7]})

        expected = pd.DataFrame(
            {"a": [1, 5, 10], "left_val": ["a", "b", "c"], "right_val": [1, 3, 7]}
        )

        result = merge_asof(left, right, on="a")
        tm.assert_frame_equal(result, expected)

    def test_examples2(self, unit):
        """doc-string examples"""
        if unit == "s":
            pytest.skip(
                "This test is invalid for unit='s' because that would "
                "round the trades['time']]"
            )
        trades = pd.DataFrame(
            {
                "time": to_datetime(
                    [
                        "20160525 13:30:00.023",
                        "20160525 13:30:00.038",
                        "20160525 13:30:00.048",
                        "20160525 13:30:00.048",
                        "20160525 13:30:00.048",
                    ]
                ).astype(f"M8[{unit}]"),
                "ticker": ["MSFT", "MSFT", "GOOG", "GOOG", "AAPL"],
                "price": [51.95, 51.95, 720.77, 720.92, 98.00],
                "quantity": [75, 155, 100, 100, 100],
            },
            columns=["time", "ticker", "price", "quantity"],
        )

        quotes = pd.DataFrame(
            {
                "time": to_datetime(
                    [
                        "20160525 13:30:00.023",
                        "20160525 13:30:00.023",
                        "20160525 13:30:00.030",
                        "20160525 13:30:00.041",
                        "20160525 13:30:00.048",
                        "20160525 13:30:00.049",
                        "20160525 13:30:00.072",
                        "20160525 13:30:00.075",
                    ]
                ).astype(f"M8[{unit}]"),
                "ticker": [
                    "GOOG",
                    "MSFT",
                    "MSFT",
                    "MSFT",
                    "GOOG",
                    "AAPL",
                    "GOOG",
                    "MSFT",
                ],
                "bid": [720.50, 51.95, 51.97, 51.99, 720.50, 97.99, 720.50, 52.01],
                "ask": [720.93, 51.96, 51.98, 52.00, 720.93, 98.01, 720.88, 52.03],
            },
            columns=["time", "ticker", "bid", "ask"],
        )

        merge_asof(trades, quotes, on="time", by="ticker")

        merge_asof(trades, quotes, on="time", by="ticker", tolerance=Timedelta("2ms"))

        expected = pd.DataFrame(
            {
                "time": to_datetime(
                    [
                        "20160525 13:30:00.023",
                        "20160525 13:30:00.038",
                        "20160525 13:30:00.048",
                        "20160525 13:30:00.048",
                        "20160525 13:30:00.048",
                    ]
                ).astype(f"M8[{unit}]"),
                "ticker": ["MSFT", "MSFT", "GOOG", "GOOG", "AAPL"],
                "price": [51.95, 51.95, 720.77, 720.92, 98.00],
                "quantity": [75, 155, 100, 100, 100],
                "bid": [np.nan, 51.97, np.nan, np.nan, np.nan],
                "ask": [np.nan, 51.98, np.nan, np.nan, np.nan],
            },
            columns=["time", "ticker", "price", "quantity", "bid", "ask"],
        )

        result = merge_asof(
            trades,
            quotes,
            on="time",
            by="ticker",
            tolerance=Timedelta("10ms"),
            allow_exact_matches=False,
        )
        tm.assert_frame_equal(result, expected)

    def test_examples3(self):
        """doc-string examples"""
        # GH14887

        left = pd.DataFrame({"a": [1, 5, 10], "left_val": ["a", "b", "c"]})
        right = pd.DataFrame({"a": [1, 2, 3, 6, 7], "right_val": [1, 2, 3, 6, 7]})

        expected = pd.DataFrame(
            {"a": [1, 5, 10], "left_val": ["a", "b", "c"], "right_val": [1, 6, np.nan]}
        )

        result = merge_asof(left, right, on="a", direction="forward")
        tm.assert_frame_equal(result, expected)

    def test_examples4(self):
        """doc-string examples"""
        # GH14887

        left = pd.DataFrame({"a": [1, 5, 10], "left_val": ["a", "b", "c"]})
        right = pd.DataFrame({"a": [1, 2, 3, 6, 7], "right_val": [1, 2, 3, 6, 7]})

        expected = pd.DataFrame(
            {"a": [1, 5, 10], "left_val": ["a", "b", "c"], "right_val": [1, 6, 7]}
        )

        result = merge_asof(left, right, on="a", direction="nearest")
        tm.assert_frame_equal(result, expected)

    def test_basic(self, trades, asof, quotes):
        expected = asof

        result = merge_asof(trades, quotes, on="time", by="ticker")
        tm.assert_frame_equal(result, expected)

    def test_basic_categorical(self, trades, asof, quotes):
        expected = asof
        trades.ticker = trades.ticker.astype("category")
        quotes.ticker = quotes.ticker.astype("category")
        expected.ticker = expected.ticker.astype("category")

        result = merge_asof(trades, quotes, on="time", by="ticker")
        tm.assert_frame_equal(result, expected)

    def test_basic_left_index(self, trades, asof, quotes):
        # GH14253
        expected = asof
        trades = trades.set_index("time")

        result = merge_asof(
            trades, quotes, left_index=True, right_on="time", by="ticker"
        )
        # left-only index uses right"s index, oddly
        expected.index = result.index
        # time column appears after left"s columns
        expected = expected[result.columns]
        tm.assert_frame_equal(result, expected)

    def test_basic_right_index(self, trades, asof, quotes):
        expected = asof
        quotes = quotes.set_index("time")

        result = merge_asof(
            trades, quotes, left_on="time", right_index=True, by="ticker"
        )
        tm.assert_frame_equal(result, expected)

    def test_basic_left_index_right_index(self, trades, asof, quotes):
        expected = asof.set_index("time")
        trades = trades.set_index("time")
        quotes = quotes.set_index("time")

        result = merge_asof(
            trades, quotes, left_index=True, right_index=True, by="ticker"
        )
        tm.assert_frame_equal(result, expected)

    def test_multi_index_left(self, trades, quotes):
        # MultiIndex is prohibited
        trades = trades.set_index(["time", "price"])
        quotes = quotes.set_index("time")
        with pytest.raises(MergeError, match="left can only have one index"):
            merge_asof(trades, quotes, left_index=True, right_index=True)

    def test_multi_index_right(self, trades, quotes):
        # MultiIndex is prohibited
        trades = trades.set_index("time")
        quotes = quotes.set_index(["time", "bid"])
        with pytest.raises(MergeError, match="right can only have one index"):
            merge_asof(trades, quotes, left_index=True, right_index=True)

    def test_on_and_index_left_on(self, trades, quotes):
        # "on" parameter and index together is prohibited
        trades = trades.set_index("time")
        quotes = quotes.set_index("time")
        msg = 'Can only pass argument "left_on" OR "left_index" not both.'
        with pytest.raises(MergeError, match=msg):
            merge_asof(
                trades, quotes, left_on="price", left_index=True, right_index=True
            )

    def test_on_and_index_right_on(self, trades, quotes):
        trades = trades.set_index("time")
        quotes = quotes.set_index("time")
        msg = 'Can only pass argument "right_on" OR "right_index" not both.'
        with pytest.raises(MergeError, match=msg):
            merge_asof(
                trades, quotes, right_on="bid", left_index=True, right_index=True
            )

    def test_basic_left_by_right_by(self, trades, asof, quotes):
        # GH14253
        expected = asof

        result = merge_asof(
            trades, quotes, on="time", left_by="ticker", right_by="ticker"
        )
        tm.assert_frame_equal(result, expected)

    def test_missing_right_by(self, trades, asof, quotes):
        expected = asof

        q = quotes[quotes.ticker != "MSFT"]
        result = merge_asof(trades, q, on="time", by="ticker")
        expected.loc[expected.ticker == "MSFT", ["bid", "ask"]] = np.nan
        tm.assert_frame_equal(result, expected)

    def test_multiby(self):
        # GH13936
        trades = pd.DataFrame(
            {
                "time": to_datetime(
                    [
                        "20160525 13:30:00.023",
                        "20160525 13:30:00.023",
                        "20160525 13:30:00.046",
                        "20160525 13:30:00.048",
                        "20160525 13:30:00.050",
                    ]
                ),
                "ticker": ["MSFT", "MSFT", "GOOG", "GOOG", "AAPL"],
                "exch": ["ARCA", "NSDQ", "NSDQ", "BATS", "NSDQ"],
                "price": [51.95, 51.95, 720.77, 720.92, 98.00],
                "quantity": [75, 155, 100, 100, 100],
            },
            columns=["time", "ticker", "exch", "price", "quantity"],
        )

        quotes = pd.DataFrame(
            {
                "time": to_datetime(
                    [
                        "20160525 13:30:00.023",
                        "20160525 13:30:00.023",
                        "20160525 13:30:00.030",
                        "20160525 13:30:00.041",
                        "20160525 13:30:00.045",
                        "20160525 13:30:00.049",
                    ]
                ),
                "ticker": ["GOOG", "MSFT", "MSFT", "MSFT", "GOOG", "AAPL"],
                "exch": ["BATS", "NSDQ", "ARCA", "ARCA", "NSDQ", "ARCA"],
                "bid": [720.51, 51.95, 51.97, 51.99, 720.50, 97.99],
                "ask": [720.92, 51.96, 51.98, 52.00, 720.93, 98.01],
            },
            columns=["time", "ticker", "exch", "bid", "ask"],
        )

        expected = pd.DataFrame(
            {
                "time": to_datetime(
                    [
                        "20160525 13:30:00.023",
                        "20160525 13:30:00.023",
                        "20160525 13:30:00.046",
                        "20160525 13:30:00.048",
                        "20160525 13:30:00.050",
                    ]
                ),
                "ticker": ["MSFT", "MSFT", "GOOG", "GOOG", "AAPL"],
                "exch": ["ARCA", "NSDQ", "NSDQ", "BATS", "NSDQ"],
                "price": [51.95, 51.95, 720.77, 720.92, 98.00],
                "quantity": [75, 155, 100, 100, 100],
                "bid": [np.nan, 51.95, 720.50, 720.51, np.nan],
                "ask": [np.nan, 51.96, 720.93, 720.92, np.nan],
            },
            columns=["time", "ticker", "exch", "price", "quantity", "bid", "ask"],
        )

        result = merge_asof(trades, quotes, on="time", by=["ticker", "exch"])
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("dtype", ["object", "string"])
    def test_multiby_heterogeneous_types(self, dtype):
        # GH13936
        trades = pd.DataFrame(
            {
                "time": to_datetime(
                    [
                        "20160525 13:30:00.023",
                        "20160525 13:30:00.023",
                        "20160525 13:30:00.046",
                        "20160525 13:30:00.048",
                        "20160525 13:30:00.050",
                    ]
                ),
                "ticker": [0, 0, 1, 1, 2],
                "exch": ["ARCA", "NSDQ", "NSDQ", "BATS", "NSDQ"],
                "price": [51.95, 51.95, 720.77, 720.92, 98.00],
                "quantity": [75, 155, 100, 100, 100],
            },
            columns=["time", "ticker", "exch", "price", "quantity"],
        )
        trades = trades.astype({"ticker": dtype, "exch": dtype})

        quotes = pd.DataFrame(
            {
                "time": to_datetime(
                    [
                        "20160525 13:30:00.023",
                        "20160525 13:30:00.023",
                        "20160525 13:30:00.030",
                        "20160525 13:30:00.041",
                        "20160525 13:30:00.045",
                        "20160525 13:30:00.049",
                    ]
                ),
                "ticker": [1, 0, 0, 0, 1, 2],
                "exch": ["BATS", "NSDQ", "ARCA", "ARCA", "NSDQ", "ARCA"],
                "bid": [720.51, 51.95, 51.97, 51.99, 720.50, 97.99],
                "ask": [720.92, 51.96, 51.98, 52.00, 720.93, 98.01],
            },
            columns=["time", "ticker", "exch", "bid", "ask"],
        )
        quotes = quotes.astype({"ticker": dtype, "exch": dtype})

        expected = pd.DataFrame(
            {
                "time": to_datetime(
                    [
                        "20160525 13:30:00.023",
                        "20160525 13:30:00.023",
                        "20160525 13:30:00.046",
                        "20160525 13:30:00.048",
                        "20160525 13:30:00.050",
                    ]
                ),
                "ticker": [0, 0, 1, 1, 2],
                "exch": ["ARCA", "NSDQ", "NSDQ", "BATS", "NSDQ"],
                "price": [51.95, 51.95, 720.77, 720.92, 98.00],
                "quantity": [75, 155, 100, 100, 100],
                "bid": [np.nan, 51.95, 720.50, 720.51, np.nan],
                "ask": [np.nan, 51.96, 720.93, 720.92, np.nan],
            },
            columns=["time", "ticker", "exch", "price", "quantity", "bid", "ask"],
        )
        expected = expected.astype({"ticker": dtype, "exch": dtype})

        result = merge_asof(trades, quotes, on="time", by=["ticker", "exch"])
        tm.assert_frame_equal(result, expected)

    def test_mismatched_index_dtype(self):
        # similar to test_multiby_indexed, but we change the dtype on left.index
        left = pd.DataFrame(
            [
                [to_datetime("20160602"), 1, "a"],
                [to_datetime("20160602"), 2, "a"],
                [to_datetime("20160603"), 1, "b"],
                [to_datetime("20160603"), 2, "b"],
            ],
            columns=["time", "k1", "k2"],
        ).set_index("time")
        # different dtype for the index
        left.index = left.index - pd.Timestamp(0)

        right = pd.DataFrame(
            [
                [to_datetime("20160502"), 1, "a", 1.0],
                [to_datetime("20160502"), 2, "a", 2.0],
                [to_datetime("20160503"), 1, "b", 3.0],
                [to_datetime("20160503"), 2, "b", 4.0],
            ],
            columns=["time", "k1", "k2", "value"],
        ).set_index("time")

        msg = "incompatible merge keys"
        with pytest.raises(MergeError, match=msg):
            merge_asof(left, right, left_index=True, right_index=True, by=["k1", "k2"])

    def test_multiby_indexed(self):
        # GH15676
        left = pd.DataFrame(
            [
                [to_datetime("20160602"), 1, "a"],
                [to_datetime("20160602"), 2, "a"],
                [to_datetime("20160603"), 1, "b"],
                [to_datetime("20160603"), 2, "b"],
            ],
            columns=["time", "k1", "k2"],
        ).set_index("time")

        right = pd.DataFrame(
            [
                [to_datetime("20160502"), 1, "a", 1.0],
                [to_datetime("20160502"), 2, "a", 2.0],
                [to_datetime("20160503"), 1, "b", 3.0],
                [to_datetime("20160503"), 2, "b", 4.0],
            ],
            columns=["time", "k1", "k2", "value"],
        ).set_index("time")

        expected = pd.DataFrame(
            [
                [to_datetime("20160602"), 1, "a", 1.0],
                [to_datetime("20160602"), 2, "a", 2.0],
                [to_datetime("20160603"), 1, "b", 3.0],
                [to_datetime("20160603"), 2, "b", 4.0],
            ],
            columns=["time", "k1", "k2", "value"],
        ).set_index("time")

        result = merge_asof(
            left, right, left_index=True, right_index=True, by=["k1", "k2"]
        )

        tm.assert_frame_equal(expected, result)

        with pytest.raises(
            MergeError, match="left_by and right_by must be the same length"
        ):
            merge_asof(
                left,
                right,
                left_index=True,
                right_index=True,
                left_by=["k1", "k2"],
                right_by=["k1"],
            )

    def test_basic2(self, datapath):
        expected = pd.DataFrame(
            [
                [
                    "20160525 13:30:00.023",
                    "MSFT",
                    "51.95",
                    "75",
                    "NASDAQ",
                    "51.95",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.038",
                    "MSFT",
                    "51.95",
                    "155",
                    "NASDAQ",
                    "51.95",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.77",
                    "100",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.92",
                    "100",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "200",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "300",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "600",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.048",
                    "GOOG",
                    "720.93",
                    "44",
                    "NASDAQ",
                    "720.5",
                    "720.93",
                ],
                [
                    "20160525 13:30:00.074",
                    "AAPL",
                    "98.67",
                    "478343",
                    "NASDAQ",
                    np.nan,
                    np.nan,
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.67",
                    "478343",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.66",
                    "6",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "30",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "75",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "20",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "35",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.65",
                    "10",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.55",
                    "6",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.075",
                    "AAPL",
                    "98.55",
                    "6",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "1000",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "200",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "300",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "400",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "600",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.076",
                    "AAPL",
                    "98.56",
                    "200",
                    "ARCA",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.078",
                    "MSFT",
                    "51.95",
                    "783",
                    "NASDAQ",
                    "51.92",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.078",
                    "MSFT",
                    "51.95",
                    "100",
                    "NASDAQ",
                    "51.92",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.078",
                    "MSFT",
                    "51.95",
                    "100",
                    "NASDAQ",
                    "51.92",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.084",
                    "AAPL",
                    "98.64",
                    "40",
                    "NASDAQ",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.084",
                    "AAPL",
                    "98.55",
                    "149",
                    "EDGX",
                    "98.55",
                    "98.56",
                ],
                [
                    "20160525 13:30:00.086",
                    "AAPL",
                    "98.56",
                    "500",
                    "ARCA",
                    "98.55",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.104",
                    "AAPL",
                    "98.63",
                    "647",
                    "EDGX",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.104",
                    "AAPL",
                    "98.63",
                    "300",
                    "EDGX",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.104",
                    "AAPL",
                    "98.63",
                    "50",
                    "NASDAQ",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.104",
                    "AAPL",
                    "98.63",
                    "50",
                    "NASDAQ",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.104",
                    "AAPL",
                    "98.63",
                    "70",
                    "NASDAQ",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.104",
                    "AAPL",
                    "98.63",
                    "70",
                    "NASDAQ",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.104",
                    "AAPL",
                    "98.63",
                    "1",
                    "NASDAQ",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.104",
                    "AAPL",
                    "98.63",
                    "62",
                    "NASDAQ",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.104",
                    "AAPL",
                    "98.63",
                    "10",
                    "NASDAQ",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.104",
                    "AAPL",
                    "98.63",
                    "100",
                    "ARCA",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.105",
                    "AAPL",
                    "98.63",
                    "100",
                    "ARCA",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.105",
                    "AAPL",
                    "98.63",
                    "700",
                    "ARCA",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.106",
                    "AAPL",
                    "98.63",
                    "61",
                    "EDGX",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.107",
                    "AAPL",
                    "98.63",
                    "100",
                    "ARCA",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.107",
                    "AAPL",
                    "98.63",
                    "53",
                    "ARCA",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.108",
                    "AAPL",
                    "98.63",
                    "100",
                    "ARCA",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.108",
                    "AAPL",
                    "98.63",
                    "839",
                    "ARCA",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.115",
                    "AAPL",
                    "98.63",
                    "5",
                    "EDGX",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.118",
                    "AAPL",
                    "98.63",
                    "295",
                    "EDGX",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.118",
                    "AAPL",
                    "98.63",
                    "5",
                    "EDGX",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.128",
                    "AAPL",
                    "98.63",
                    "100",
                    "NASDAQ",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.128",
                    "AAPL",
                    "98.63",
                    "100",
                    "NASDAQ",
                    "98.62",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.128",
                    "MSFT",
                    "51.92",
                    "100",
                    "ARCA",
                    "51.92",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.129",
                    "AAPL",
                    "98.62",
                    "100",
                    "NASDAQ",
                    "98.61",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.129",
                    "AAPL",
                    "98.62",
                    "10",
                    "NASDAQ",
                    "98.61",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.129",
                    "AAPL",
                    "98.62",
                    "59",
                    "NASDAQ",
                    "98.61",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.129",
                    "AAPL",
                    "98.62",
                    "31",
                    "NASDAQ",
                    "98.61",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.129",
                    "AAPL",
                    "98.62",
                    "69",
                    "NASDAQ",
                    "98.61",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.129",
                    "AAPL",
                    "98.62",
                    "12",
                    "NASDAQ",
                    "98.61",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.129",
                    "AAPL",
                    "98.62",
                    "12",
                    "EDGX",
                    "98.61",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.129",
                    "AAPL",
                    "98.62",
                    "100",
                    "ARCA",
                    "98.61",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.129",
                    "AAPL",
                    "98.62",
                    "100",
                    "ARCA",
                    "98.61",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.130",
                    "MSFT",
                    "51.95",
                    "317",
                    "ARCA",
                    "51.93",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.130",
                    "MSFT",
                    "51.95",
                    "283",
                    "ARCA",
                    "51.93",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.135",
                    "MSFT",
                    "51.93",
                    "100",
                    "EDGX",
                    "51.92",
                    "51.95",
                ],
                [
                    "20160525 13:30:00.135",
                    "AAPL",
                    "98.62",
                    "100",
                    "ARCA",
                    "98.61",
                    "98.62",
                ],
                [
                    "20160525 13:30:00.144",
                    "AAPL",
                    "98.62",
                    "12",
                    "NASDAQ",
                    "98.61",
                    "98.62",
                ],
                [
                    "20160525 13:30:00.144",
                    "AAPL",
                    "98.62",
                    "88",
                    "NASDAQ",
                    "98.61",
                    "98.62",
                ],
                [
                    "20160525 13:30:00.144",
                    "AAPL",
                    "98.62",
                    "162",
                    "NASDAQ",
                    "98.61",
                    "98.62",
                ],
                [
                    "20160525 13:30:00.144",
                    "AAPL",
                    "98.61",
                    "100",
                    "BATS",
                    "98.61",
                    "98.62",
                ],
                [
                    "20160525 13:30:00.144",
                    "AAPL",
                    "98.62",
                    "61",
                    "ARCA",
                    "98.61",
                    "98.62",
                ],
                [
                    "20160525 13:30:00.144",
                    "AAPL",
                    "98.62",
                    "25",
                    "ARCA",
                    "98.61",
                    "98.62",
                ],
                [
                    "20160525 13:30:00.144",
                    "AAPL",
                    "98.62",
                    "14",
                    "ARCA",
                    "98.61",
                    "98.62",
                ],
                [
                    "20160525 13:30:00.145",
                    "AAPL",
                    "98.62",
                    "12",
                    "ARCA",
                    "98.6",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.145",
                    "AAPL",
                    "98.62",
                    "100",
                    "ARCA",
                    "98.6",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.145",
                    "AAPL",
                    "98.63",
                    "100",
                    "NASDAQ",
                    "98.6",
                    "98.63",
                ],
                [
                    "20160525 13:30:00.145",
                    "AAPL",
                    "98.63",
                    "100",
                    "NASDAQ",
                    "98.6",
                    "98.63",
                ],
            ],
            columns="time,ticker,price,quantity,marketCenter,bid,ask".split(","),
        )
        expected["price"] = expected["price"].astype("float64")
        expected["quantity"] = expected["quantity"].astype("int64")
        expected["bid"] = expected["bid"].astype("float64")
        expected["ask"] = expected["ask"].astype("float64")
        expected = self.prep_data(expected)

        trades = pd.DataFrame(
            [
                ["20160525 13:30:00.023", "MSFT", "51.9500", "75", "NASDAQ"],
                ["20160525 13:30:00.038", "MSFT", "51.9500", "155", "NASDAQ"],
                ["20160525 13:30:00.048", "GOOG", "720.7700", "100", "NASDAQ"],
                ["20160525 13:30:00.048", "GOOG", "720.9200", "100", "NASDAQ"],
                ["20160525 13:30:00.048", "GOOG", "720.9300", "200", "NASDAQ"],
                ["20160525 13:30:00.048", "GOOG", "720.9300", "300", "NASDAQ"],
                ["20160525 13:30:00.048", "GOOG", "720.9300", "600", "NASDAQ"],
                ["20160525 13:30:00.048", "GOOG", "720.9300", "44", "NASDAQ"],
                ["20160525 13:30:00.074", "AAPL", "98.6700", "478343", "NASDAQ"],
                ["20160525 13:30:00.075", "AAPL", "98.6700", "478343", "NASDAQ"],
                ["20160525 13:30:00.075", "AAPL", "98.6600", "6", "NASDAQ"],
                ["20160525 13:30:00.075", "AAPL", "98.6500", "30", "NASDAQ"],
                ["20160525 13:30:00.075", "AAPL", "98.6500", "75", "NASDAQ"],
                ["20160525 13:30:00.075", "AAPL", "98.6500", "20", "NASDAQ"],
                ["20160525 13:30:00.075", "AAPL", "98.6500", "35", "NASDAQ"],
                ["20160525 13:30:00.075", "AAPL", "98.6500", "10", "NASDAQ"],
                ["20160525 13:30:00.075", "AAPL", "98.5500", "6", "ARCA"],
                ["20160525 13:30:00.075", "AAPL", "98.5500", "6", "ARCA"],
                ["20160525 13:30:00.076", "AAPL", "98.5600", "1000", "ARCA"],
                ["20160525 13:30:00.076", "AAPL", "98.5600", "200", "ARCA"],
                ["20160525 13:30:00.076", "AAPL", "98.5600", "300", "ARCA"],
                ["20160525 13:30:00.076", "AAPL", "98.5600", "400", "ARCA"],
                ["20160525 13:30:00.076", "AAPL", "98.5600", "600", "ARCA"],
                ["20160525 13:30:00.076", "AAPL", "98.5600", "200", "ARCA"],
                ["20160525 13:30:00.078", "MSFT", "51.9500", "783", "NASDAQ"],
                ["20160525 13:30:00.078", "MSFT", "51.9500", "100", "NASDAQ"],
                ["20160525 13:30:00.078", "MSFT", "51.9500", "100", "NASDAQ"],
                ["20160525 13:30:00.084", "AAPL", "98.6400", "40", "NASDAQ"],
                ["20160525 13:30:00.084", "AAPL", "98.5500", "149", "EDGX"],
                ["20160525 13:30:00.086", "AAPL", "98.5600", "500", "ARCA"],
                ["20160525 13:30:00.104", "AAPL", "98.6300", "647", "EDGX"],
                ["20160525 13:30:00.104", "AAPL", "98.6300", "300", "EDGX"],
                ["20160525 13:30:00.104", "AAPL", "98.6300", "50", "NASDAQ"],
                ["20160525 13:30:00.104", "AAPL", "98.6300", "50", "NASDAQ"],
                ["20160525 13:30:00.104", "AAPL", "98.6300", "70", "NASDAQ"],
                ["20160525 13:30:00.104", "AAPL", "98.6300", "70", "NASDAQ"],
                ["20160525 13:30:00.104", "AAPL", "98.6300", "1", "NASDAQ"],
                ["20160525 13:30:00.104", "AAPL", "98.6300", "62", "NASDAQ"],
                ["20160525 13:30:00.104", "AAPL", "98.6300", "10", "NASDAQ"],
                ["20160525 13:30:00.104", "AAPL", "98.6300", "100", "ARCA"],
                ["20160525 13:30:00.105", "AAPL", "98.6300", "100", "ARCA"],
                ["20160525 13:30:00.105", "AAPL", "98.6300", "700", "ARCA"],
                ["20160525 13:30:00.106", "AAPL", "98.6300", "61", "EDGX"],
                ["20160525 13:30:00.107", "AAPL", "98.6300", "100", "ARCA"],
                ["20160525 13:30:00.107", "AAPL", "98.6300", "53", "ARCA"],
                ["20160525 13:30:00.108", "AAPL", "98.6300", "100", "ARCA"],
                ["20160525 13:30:00.108", "AAPL", "98.6300", "839", "ARCA"],
                ["20160525 13:30:00.115", "AAPL", "98.6300", "5", "EDGX"],
                ["20160525 13:30:00.118", "AAPL", "98.6300", "295", "EDGX"],
                ["20160525 13:30:00.118", "AAPL", "98.6300", "5", "EDGX"],
                ["20160525 13:30:00.128", "AAPL", "98.6300", "100", "NASDAQ"],
                ["20160525 13:30:00.128", "AAPL", "98.6300", "100", "NASDAQ"],
                ["20160525 13:30:00.128", "MSFT", "51.9200", "100", "ARCA"],
                ["20160525 13:30:00.129", "AAPL", "98.6200", "100", "NASDAQ"],
                ["20160525 13:30:00.129", "AAPL", "98.6200", "10", "NASDAQ"],
                ["20160525 13:30:00.129", "AAPL", "98.6200", "59", "NASDAQ"],
                ["20160525 13:30:00.129", "AAPL", "98.6200", "31", "NASDAQ"],
                ["20160525 13:30:00.129", "AAPL", "98.6200", "69", "NASDAQ"],
                ["20160525 13:30:00.129", "AAPL", "98.6200", "12", "NASDAQ"],
                ["20160525 13:30:00.129", "AAPL", "98.6200", "12", "EDGX"],
                ["20160525 13:30:00.129", "AAPL", "98.6200", "100", "ARCA"],
                ["20160525 13:30:00.129", "AAPL", "98.6200", "100", "ARCA"],
                ["20160525 13:30:00.130", "MSFT", "51.9500", "317", "ARCA"],
                ["20160525 13:30:00.130", "MSFT", "51.9500", "283", "ARCA"],
                ["20160525 13:30:00.135", "MSFT", "51.9300", "100", "EDGX"],
                ["20160525 13:30:00.135", "AAPL", "98.6200", "100", "ARCA"],
                ["20160525 13:30:00.144", "AAPL", "98.6200", "12", "NASDAQ"],
                ["20160525 13:30:00.144", "AAPL", "98.6200", "88", "NASDAQ"],
                ["20160525 13:30:00.144", "AAPL", "98.6200", "162", "NASDAQ"],
                ["20160525 13:30:00.144", "AAPL", "98.6100", "100", "BATS"],
                ["20160525 13:30:00.144", "AAPL", "98.6200", "61", "ARCA"],
                ["20160525 13:30:00.144", "AAPL", "98.6200", "25", "ARCA"],
                ["20160525 13:30:00.144", "AAPL", "98.6200", "14", "ARCA"],
                ["20160525 13:30:00.145", "AAPL", "98.6200", "12", "ARCA"],
                ["20160525 13:30:00.145", "AAPL", "98.6200", "100", "ARCA"],
                ["20160525 13:30:00.145", "AAPL", "98.6300", "100", "NASDAQ"],
                ["20160525 13:30:00.145", "AAPL", "98.6300", "100", "NASDAQ"],
            ],
            columns="time,ticker,price,quantity,marketCenter".split(","),
        )
        trades["price"] = trades["price"].astype("float64")
        trades["quantity"] = trades["quantity"].astype("int64")
        trades = self.prep_data(trades)

        quotes = pd.DataFrame(
            [
                ["20160525 13:30:00.023", "GOOG", "720.50", "720.93"],
                ["20160525 13:30:00.023", "MSFT", "51.95", "51.95"],
                ["20160525 13:30:00.041", "MSFT", "51.95", "51.95"],
                ["20160525 13:30:00.048", "GOOG", "720.50", "720.93"],
                ["20160525 13:30:00.048", "GOOG", "720.50", "720.93"],
                ["20160525 13:30:00.048", "GOOG", "720.50", "720.93"],
                ["20160525 13:30:00.048", "GOOG", "720.50", "720.93"],
                ["20160525 13:30:00.072", "GOOG", "720.50", "720.88"],
                ["20160525 13:30:00.075", "AAPL", "98.55", "98.56"],
                ["20160525 13:30:00.076", "AAPL", "98.55", "98.56"],
                ["20160525 13:30:00.076", "AAPL", "98.55", "98.56"],
                ["20160525 13:30:00.076", "AAPL", "98.55", "98.56"],
                ["20160525 13:30:00.078", "MSFT", "51.95", "51.95"],
                ["20160525 13:30:00.078", "MSFT", "51.95", "51.95"],
                ["20160525 13:30:00.078", "MSFT", "51.95", "51.95"],
                ["20160525 13:30:00.078", "MSFT", "51.92", "51.95"],
                ["20160525 13:30:00.079", "MSFT", "51.92", "51.95"],
                ["20160525 13:30:00.080", "AAPL", "98.55", "98.56"],
                ["20160525 13:30:00.084", "AAPL", "98.55", "98.56"],
                ["20160525 13:30:00.086", "AAPL", "98.55", "98.63"],
                ["20160525 13:30:00.088", "AAPL", "98.65", "98.63"],
                ["20160525 13:30:00.089", "AAPL", "98.63", "98.63"],
                ["20160525 13:30:00.104", "AAPL", "98.63", "98.63"],
                ["20160525 13:30:00.104", "AAPL", "98.63", "98.63"],
                ["20160525 13:30:00.104", "AAPL", "98.63", "98.63"],
                ["20160525 13:30:00.104", "AAPL", "98.63", "98.63"],
                ["20160525 13:30:00.104", "AAPL", "98.62", "98.63"],
                ["20160525 13:30:00.105", "AAPL", "98.62", "98.63"],
                ["20160525 13:30:00.107", "AAPL", "98.62", "98.63"],
                ["20160525 13:30:00.115", "AAPL", "98.62", "98.63"],
                ["20160525 13:30:00.115", "AAPL", "98.62", "98.63"],
                ["20160525 13:30:00.118", "AAPL", "98.62", "98.63"],
                ["20160525 13:30:00.128", "AAPL", "98.62", "98.63"],
                ["20160525 13:30:00.128", "AAPL", "98.62", "98.63"],
                ["20160525 13:30:00.129", "AAPL", "98.62", "98.63"],
                ["20160525 13:30:00.129", "AAPL", "98.61", "98.63"],
                ["20160525 13:30:00.129", "AAPL", "98.62", "98.63"],
                ["20160525 13:30:00.129", "AAPL", "98.62", "98.63"],
                ["20160525 13:30:00.129", "AAPL", "98.61", "98.63"],
                ["20160525 13:30:00.130", "MSFT", "51.93", "51.95"],
                ["20160525 13:30:00.130", "MSFT", "51.93", "51.95"],
                ["20160525 13:30:00.130", "AAPL", "98.61", "98.63"],
                ["20160525 13:30:00.131", "AAPL", "98.61", "98.62"],
                ["20160525 13:30:00.131", "AAPL", "98.61", "98.62"],
                ["20160525 13:30:00.135", "MSFT", "51.92", "51.95"],
                ["20160525 13:30:00.135", "AAPL", "98.61", "98.62"],
                ["20160525 13:30:00.136", "AAPL", "98.61", "98.62"],
                ["20160525 13:30:00.136", "AAPL", "98.61", "98.62"],
                ["20160525 13:30:00.144", "AAPL", "98.61", "98.62"],
                ["20160525 13:30:00.144", "AAPL", "98.61", "98.62"],
                ["20160525 13:30:00.145", "AAPL", "98.61", "98.62"],
                ["20160525 13:30:00.145", "AAPL", "98.61", "98.63"],
                ["20160525 13:30:00.145", "AAPL", "98.61", "98.63"],
                ["20160525 13:30:00.145", "AAPL", "98.60", "98.63"],
                ["20160525 13:30:00.145", "AAPL", "98.61", "98.63"],
                ["20160525 13:30:00.145", "AAPL", "98.60", "98.63"],
            ],
            columns="time,ticker,bid,ask".split(","),
        )
        quotes["bid"] = quotes["bid"].astype("float64")
        quotes["ask"] = quotes["ask"].astype("float64")
        quotes = self.prep_data(quotes, dedupe=True)

        result = merge_asof(trades, quotes, on="time", by="ticker")
        tm.assert_frame_equal(result, expected)

    def test_basic_no_by(self, trades, asof, quotes):
        f = (
            lambda x: x[x.ticker == "MSFT"]
            .drop("ticker", axis=1)
            .reset_index(drop=True)
        )

        # just use a single ticker
        expected = f(asof)
        trades = f(trades)
        quotes = f(quotes)

        result = merge_asof(trades, quotes, on="time")
        tm.assert_frame_equal(result, expected)

    def test_valid_join_keys(self, trades, quotes):
        msg = r"incompatible merge keys \[1\] .* must be the same type"

        with pytest.raises(MergeError, match=msg):
            merge_asof(trades, quotes, left_on="time", right_on="bid", by="ticker")

        with pytest.raises(MergeError, match="can only asof on a key for left"):
            merge_asof(trades, quotes, on=["time", "ticker"], by="ticker")

        with pytest.raises(MergeError, match="can only asof on a key for left"):
            merge_asof(trades, quotes, by="ticker")

    def test_with_duplicates(self, datapath, trades, quotes, asof):
        q = (
            pd.concat([quotes, quotes])
            .sort_values(["time", "ticker"])
            .reset_index(drop=True)
        )
        result = merge_asof(trades, q, on="time", by="ticker")
        expected = self.prep_data(asof)
        tm.assert_frame_equal(result, expected)

    def test_with_duplicates_no_on(self):
        df1 = pd.DataFrame({"key": [1, 1, 3], "left_val": [1, 2, 3]})
        df2 = pd.DataFrame({"key": [1, 2, 2], "right_val": [1, 2, 3]})
        result = merge_asof(df1, df2, on="key")
        expected = pd.DataFrame(
            {"key": [1, 1, 3], "left_val": [1, 2, 3], "right_val": [1, 1, 3]}
        )
        tm.assert_frame_equal(result, expected)

    def test_valid_allow_exact_matches(self, trades, quotes):
        msg = "allow_exact_matches must be boolean, passed foo"

        with pytest.raises(MergeError, match=msg):
            merge_asof(
                trades, quotes, on="time", by="ticker", allow_exact_matches="foo"
            )

    def test_valid_tolerance(self, trades, quotes):
        # dti
        merge_asof(trades, quotes, on="time", by="ticker", tolerance=Timedelta("1s"))

        # integer
        merge_asof(
            trades.reset_index(),
            quotes.reset_index(),
            on="index",
            by="ticker",
            tolerance=1,
        )

        msg = r"incompatible tolerance .*, must be compat with type .*"

        # incompat
        with pytest.raises(MergeError, match=msg):
            merge_asof(trades, quotes, on="time", by="ticker", tolerance=1)

        # invalid
        with pytest.raises(MergeError, match=msg):
            merge_asof(
                trades.reset_index(),
                quotes.reset_index(),
                on="index",
                by="ticker",
                tolerance=1.0,
            )

        msg = "tolerance must be positive"

        # invalid negative
        with pytest.raises(MergeError, match=msg):
            merge_asof(
                trades, quotes, on="time", by="ticker", tolerance=-Timedelta("1s")
            )

        with pytest.raises(MergeError, match=msg):
            merge_asof(
                trades.reset_index(),
                quotes.reset_index(),
                on="index",
                by="ticker",
                tolerance=-1,
            )

    def test_non_sorted(self, trades, quotes):
        trades = trades.sort_values("time", ascending=False)
        quotes = quotes.sort_values("time", ascending=False)

        # we require that we are already sorted on time & quotes
        assert not trades.time.is_monotonic_increasing
        assert not quotes.time.is_monotonic_increasing
        with pytest.raises(ValueError, match="left keys must be sorted"):
            merge_asof(trades, quotes, on="time", by="ticker")

        trades = trades.sort_values("time")
        assert trades.time.is_monotonic_increasing
        assert not quotes.time.is_monotonic_increasing
        with pytest.raises(ValueError, match="right keys must be sorted"):
            merge_asof(trades, quotes, on="time", by="ticker")

        quotes = quotes.sort_values("time")
        assert trades.time.is_monotonic_increasing
        assert quotes.time.is_monotonic_increasing

        # ok, though has dupes
        merge_asof(trades, quotes, on="time", by="ticker")

    @pytest.mark.parametrize(
        "tolerance_ts",
        [Timedelta("1day"), datetime.timedelta(days=1)],
        ids=["Timedelta", "datetime.timedelta"],
    )
    def test_tolerance(self, tolerance_ts, trades, quotes, tolerance):
        result = merge_asof(
            trades, quotes, on="time", by="ticker", tolerance=tolerance_ts
        )
        expected = tolerance
        tm.assert_frame_equal(result, expected)

    def test_tolerance_forward(self):
        # GH14887

        left = pd.DataFrame({"a": [1, 5, 10], "left_val": ["a", "b", "c"]})
        right = pd.DataFrame({"a": [1, 2, 3, 7, 11], "right_val": [1, 2, 3, 7, 11]})

        expected = pd.DataFrame(
            {"a": [1, 5, 10], "left_val": ["a", "b", "c"], "right_val": [1, np.nan, 11]}
        )

        result = merge_asof(left, right, on="a", direction="forward", tolerance=1)
        tm.assert_frame_equal(result, expected)

    def test_tolerance_nearest(self):
        # GH14887

        left = pd.DataFrame({"a": [1, 5, 10], "left_val": ["a", "b", "c"]})
        right = pd.DataFrame({"a": [1, 2, 3, 7, 11], "right_val": [1, 2, 3, 7, 11]})

        expected = pd.DataFrame(
            {"a": [1, 5, 10], "left_val": ["a", "b", "c"], "right_val": [1, np.nan, 11]}
        )

        result = merge_asof(left, right, on="a", direction="nearest", tolerance=1)
        tm.assert_frame_equal(result, expected)

    def test_tolerance_tz(self, unit):
        # GH 14844
        left = pd.DataFrame(
            {
                "date": pd.date_range(
                    start=to_datetime("2016-01-02"),
                    freq="D",
                    periods=5,
                    tz=pytz.timezone("UTC"),
                    unit=unit,
                ),
                "value1": np.arange(5),
            }
        )
        right = pd.DataFrame(
            {
                "date": pd.date_range(
                    start=to_datetime("2016-01-01"),
                    freq="D",
                    periods=5,
                    tz=pytz.timezone("UTC"),
                    unit=unit,
                ),
                "value2": list("ABCDE"),
            }
        )
        result = merge_asof(left, right, on="date", tolerance=Timedelta("1 day"))

        expected = pd.DataFrame(
            {
                "date": pd.date_range(
                    start=to_datetime("2016-01-02"),
                    freq="D",
                    periods=5,
                    tz=pytz.timezone("UTC"),
                    unit=unit,
                ),
                "value1": np.arange(5),
                "value2": list("BCDEE"),
            }
        )
        tm.assert_frame_equal(result, expected)

    def test_tolerance_float(self):
        # GH22981
        left = pd.DataFrame({"a": [1.1, 3.5, 10.9], "left_val": ["a", "b", "c"]})
        right = pd.DataFrame(
            {"a": [1.0, 2.5, 3.3, 7.5, 11.5], "right_val": [1.0, 2.5, 3.3, 7.5, 11.5]}
        )

        expected = pd.DataFrame(
            {
                "a": [1.1, 3.5, 10.9],
                "left_val": ["a", "b", "c"],
                "right_val": [1, 3.3, np.nan],
            }
        )

        result = merge_asof(left, right, on="a", direction="nearest", tolerance=0.5)
        tm.assert_frame_equal(result, expected)

    def test_index_tolerance(self, trades, quotes, tolerance):
        # GH 15135
        expected = tolerance.set_index("time")
        trades = trades.set_index("time")
        quotes = quotes.set_index("time")

        result = merge_asof(
            trades,
            quotes,
            left_index=True,
            right_index=True,
            by="ticker",
            tolerance=Timedelta("1day"),
        )
        tm.assert_frame_equal(result, expected)

    def test_allow_exact_matches(self, trades, quotes, allow_exact_matches):
        result = merge_asof(
            trades, quotes, on="time", by="ticker", allow_exact_matches=False
        )
        expected = allow_exact_matches
        tm.assert_frame_equal(result, expected)

    def test_allow_exact_matches_forward(self):
        # GH14887

        left = pd.DataFrame({"a": [1, 5, 10], "left_val": ["a", "b", "c"]})
        right = pd.DataFrame({"a": [1, 2, 3, 7, 11], "right_val": [1, 2, 3, 7, 11]})

        expected = pd.DataFrame(
            {"a": [1, 5, 10], "left_val": ["a", "b", "c"], "right_val": [2, 7, 11]}
        )

        result = merge_asof(
            left, right, on="a", direction="forward", allow_exact_matches=False
        )
        tm.assert_frame_equal(result, expected)

    def test_allow_exact_matches_nearest(self):
        # GH14887

        left = pd.DataFrame({"a": [1, 5, 10], "left_val": ["a", "b", "c"]})
        right = pd.DataFrame({"a": [1, 2, 3, 7, 11], "right_val": [1, 2, 3, 7, 11]})

        expected = pd.DataFrame(
            {"a": [1, 5, 10], "left_val": ["a", "b", "c"], "right_val": [2, 3, 11]}
        )

        result = merge_asof(
            left, right, on="a", direction="nearest", allow_exact_matches=False
        )
        tm.assert_frame_equal(result, expected)

    def test_allow_exact_matches_and_tolerance(
        self, trades, quotes, allow_exact_matches_and_tolerance
    ):
        result = merge_asof(
            trades,
            quotes,
            on="time",
            by="ticker",
            tolerance=Timedelta("100ms"),
            allow_exact_matches=False,
        )
        expected = allow_exact_matches_and_tolerance
        tm.assert_frame_equal(result, expected)

    def test_allow_exact_matches_and_tolerance2(self):
        # GH 13695
        df1 = pd.DataFrame(
            {"time": to_datetime(["2016-07-15 13:30:00.030"]), "username": ["bob"]}
        )
        df2 = pd.DataFrame(
            {
                "time": to_datetime(
                    ["2016-07-15 13:30:00.000", "2016-07-15 13:30:00.030"]
                ),
                "version": [1, 2],
            }
        )

        result = merge_asof(df1, df2, on="time")
        expected = pd.DataFrame(
            {
                "time": to_datetime(["2016-07-15 13:30:00.030"]),
                "username": ["bob"],
                "version": [2],
            }
        )
        tm.assert_frame_equal(result, expected)

        result = merge_asof(df1, df2, on="time", allow_exact_matches=False)
        expected = pd.DataFrame(
            {
                "time": to_datetime(["2016-07-15 13:30:00.030"]),
                "username": ["bob"],
                "version": [1],
            }
        )
        tm.assert_frame_equal(result, expected)

        result = merge_asof(
            df1,
            df2,
            on="time",
            allow_exact_matches=False,
            tolerance=Timedelta("10ms"),
        )
        expected = pd.DataFrame(
            {
                "time": to_datetime(["2016-07-15 13:30:00.030"]),
                "username": ["bob"],
                "version": [np.nan],
            }
        )
        tm.assert_frame_equal(result, expected)

    def test_allow_exact_matches_and_tolerance3(self):
        # GH 13709
        df1 = pd.DataFrame(
            {
                "time": to_datetime(
                    ["2016-07-15 13:30:00.030", "2016-07-15 13:30:00.030"]
                ),
                "username": ["bob", "charlie"],
            }
        )
        df2 = pd.DataFrame(
            {
                "time": to_datetime(
                    ["2016-07-15 13:30:00.000", "2016-07-15 13:30:00.030"]
                ),
                "version": [1, 2],
            }
        )

        result = merge_asof(
            df1,
            df2,
            on="time",
            allow_exact_matches=False,
            tolerance=Timedelta("10ms"),
        )
        expected = pd.DataFrame(
            {
                "time": to_datetime(
                    ["2016-07-15 13:30:00.030", "2016-07-15 13:30:00.030"]
                ),
                "username": ["bob", "charlie"],
                "version": [np.nan, np.nan],
            }
        )
        tm.assert_frame_equal(result, expected)

    def test_allow_exact_matches_and_tolerance_forward(self):
        # GH14887

        left = pd.DataFrame({"a": [1, 5, 10], "left_val": ["a", "b", "c"]})
        right = pd.DataFrame({"a": [1, 3, 4, 6, 11], "right_val": [1, 3, 4, 6, 11]})

        expected = pd.DataFrame(
            {"a": [1, 5, 10], "left_val": ["a", "b", "c"], "right_val": [np.nan, 6, 11]}
        )

        result = merge_asof(
            left,
            right,
            on="a",
            direction="forward",
            allow_exact_matches=False,
            tolerance=1,
        )
        tm.assert_frame_equal(result, expected)

    def test_allow_exact_matches_and_tolerance_nearest(self):
        # GH14887

        left = pd.DataFrame({"a": [1, 5, 10], "left_val": ["a", "b", "c"]})
        right = pd.DataFrame({"a": [1, 3, 4, 6, 11], "right_val": [1, 3, 4, 7, 11]})

        expected = pd.DataFrame(
            {"a": [1, 5, 10], "left_val": ["a", "b", "c"], "right_val": [np.nan, 4, 11]}
        )

        result = merge_asof(
            left,
            right,
            on="a",
            direction="nearest",
            allow_exact_matches=False,
            tolerance=1,
        )
        tm.assert_frame_equal(result, expected)

    def test_forward_by(self):
        # GH14887

        left = pd.DataFrame(
            {
                "a": [1, 5, 10, 12, 15],
                "b": ["X", "X", "Y", "Z", "Y"],
                "left_val": ["a", "b", "c", "d", "e"],
            }
        )
        right = pd.DataFrame(
            {
                "a": [1, 6, 11, 15, 16],
                "b": ["X", "Z", "Y", "Z", "Y"],
                "right_val": [1, 6, 11, 15, 16],
            }
        )

        expected = pd.DataFrame(
            {
                "a": [1, 5, 10, 12, 15],
                "b": ["X", "X", "Y", "Z", "Y"],
                "left_val": ["a", "b", "c", "d", "e"],
                "right_val": [1, np.nan, 11, 15, 16],
            }
        )

        result = merge_asof(left, right, on="a", by="b", direction="forward")
        tm.assert_frame_equal(result, expected)

    def test_nearest_by(self):
        # GH14887

        left = pd.DataFrame(
            {
                "a": [1, 5, 10, 12, 15],
                "b": ["X", "X", "Z", "Z", "Y"],
                "left_val": ["a", "b", "c", "d", "e"],
            }
        )
        right = pd.DataFrame(
            {
                "a": [1, 6, 11, 15, 16],
                "b": ["X", "Z", "Z", "Z", "Y"],
                "right_val": [1, 6, 11, 15, 16],
            }
        )

        expected = pd.DataFrame(
            {
                "a": [1, 5, 10, 12, 15],
                "b": ["X", "X", "Z", "Z", "Y"],
                "left_val": ["a", "b", "c", "d", "e"],
                "right_val": [1, 1, 11, 11, 16],
            }
        )

        result = merge_asof(left, right, on="a", by="b", direction="nearest")
        tm.assert_frame_equal(result, expected)

    def test_by_int(self):
        # we specialize by type, so test that this is correct
        df1 = pd.DataFrame(
            {
                "time": to_datetime(
                    [
                        "20160525 13:30:00.020",
                        "20160525 13:30:00.030",
                        "20160525 13:30:00.040",
                        "20160525 13:30:00.050",
                        "20160525 13:30:00.060",
                    ]
                ),
                "key": [1, 2, 1, 3, 2],
                "value1": [1.1, 1.2, 1.3, 1.4, 1.5],
            },
            columns=["time", "key", "value1"],
        )

        df2 = pd.DataFrame(
            {
                "time": to_datetime(
                    [
                        "20160525 13:30:00.015",
                        "20160525 13:30:00.020",
                        "20160525 13:30:00.025",
                        "20160525 13:30:00.035",
                        "20160525 13:30:00.040",
                        "20160525 13:30:00.055",
                        "20160525 13:30:00.060",
                        "20160525 13:30:00.065",
                    ]
                ),
                "key": [2, 1, 1, 3, 2, 1, 2, 3],
                "value2": [2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8],
            },
            columns=["time", "key", "value2"],
        )

        result = merge_asof(df1, df2, on="time", by="key")

        expected = pd.DataFrame(
            {
                "time": to_datetime(
                    [
                        "20160525 13:30:00.020",
                        "20160525 13:30:00.030",
                        "20160525 13:30:00.040",
                        "20160525 13:30:00.050",
                        "20160525 13:30:00.060",
                    ]
                ),
                "key": [1, 2, 1, 3, 2],
                "value1": [1.1, 1.2, 1.3, 1.4, 1.5],
                "value2": [2.2, 2.1, 2.3, 2.4, 2.7],
            },
            columns=["time", "key", "value1", "value2"],
        )

        tm.assert_frame_equal(result, expected)

    def test_on_float(self):
        # mimics how to determine the minimum-price variation
        df1 = pd.DataFrame(
            {
                "price": [5.01, 0.0023, 25.13, 340.05, 30.78, 1040.90, 0.0078],
                "symbol": list("ABCDEFG"),
            },
            columns=["symbol", "price"],
        )

        df2 = pd.DataFrame(
            {"price": [0.0, 1.0, 100.0], "mpv": [0.0001, 0.01, 0.05]},
            columns=["price", "mpv"],
        )

        df1 = df1.sort_values("price").reset_index(drop=True)

        result = merge_asof(df1, df2, on="price")

        expected = pd.DataFrame(
            {
                "symbol": list("BGACEDF"),
                "price": [0.0023, 0.0078, 5.01, 25.13, 30.78, 340.05, 1040.90],
                "mpv": [0.0001, 0.0001, 0.01, 0.01, 0.01, 0.05, 0.05],
            },
            columns=["symbol", "price", "mpv"],
        )

        tm.assert_frame_equal(result, expected)

    def test_on_specialized_type(self, any_real_numpy_dtype):
        # see gh-13936
        dtype = np.dtype(any_real_numpy_dtype).type

        df1 = pd.DataFrame(
            {"value": [5, 2, 25, 100, 78, 120, 79], "symbol": list("ABCDEFG")},
            columns=["symbol", "value"],
        )
        df1.value = dtype(df1.value)

        df2 = pd.DataFrame(
            {"value": [0, 80, 120, 125], "result": list("xyzw")},
            columns=["value", "result"],
        )
        df2.value = dtype(df2.value)

        df1 = df1.sort_values("value").reset_index(drop=True)
        result = merge_asof(df1, df2, on="value")

        expected = pd.DataFrame(
            {
                "symbol": list("BACEGDF"),
                "value": [2, 5, 25, 78, 79, 100, 120],
                "result": list("xxxxxyz"),
            },
            columns=["symbol", "value", "result"],
        )
        expected.value = dtype(expected.value)

        tm.assert_frame_equal(result, expected)

    def test_on_specialized_type_by_int(self, any_real_numpy_dtype):
        # see gh-13936
        dtype = np.dtype(any_real_numpy_dtype).type

        df1 = pd.DataFrame(
            {
                "value": [5, 2, 25, 100, 78, 120, 79],
                "key": [1, 2, 3, 2, 3, 1, 2],
                "symbol": list("ABCDEFG"),
            },
            columns=["symbol", "key", "value"],
        )
        df1.value = dtype(df1.value)

        df2 = pd.DataFrame(
            {"value": [0, 80, 120, 125], "key": [1, 2, 2, 3], "result": list("xyzw")},
            columns=["value", "key", "result"],
        )
        df2.value = dtype(df2.value)

        df1 = df1.sort_values("value").reset_index(drop=True)
        result = merge_asof(df1, df2, on="value", by="key")

        expected = pd.DataFrame(
            {
                "symbol": list("BACEGDF"),
                "key": [2, 1, 3, 3, 2, 2, 1],
                "value": [2, 5, 25, 78, 79, 100, 120],
                "result": [np.nan, "x", np.nan, np.nan, np.nan, "y", "x"],
            },
            columns=["symbol", "key", "value", "result"],
        )
        expected.value = dtype(expected.value)

        tm.assert_frame_equal(result, expected)

    def test_on_float_by_int(self):
        # type specialize both "by" and "on" parameters
        df1 = pd.DataFrame(
            {
                "symbol": list("AAABBBCCC"),
                "exch": [1, 2, 3, 1, 2, 3, 1, 2, 3],
                "price": [
                    3.26,
                    3.2599,
                    3.2598,
                    12.58,
                    12.59,
                    12.5,
                    378.15,
                    378.2,
                    378.25,
                ],
            },
            columns=["symbol", "exch", "price"],
        )

        df2 = pd.DataFrame(
            {
                "exch": [1, 1, 1, 2, 2, 2, 3, 3, 3],
                "price": [0.0, 1.0, 100.0, 0.0, 5.0, 100.0, 0.0, 5.0, 1000.0],
                "mpv": [0.0001, 0.01, 0.05, 0.0001, 0.01, 0.1, 0.0001, 0.25, 1.0],
            },
            columns=["exch", "price", "mpv"],
        )

        df1 = df1.sort_values("price").reset_index(drop=True)
        df2 = df2.sort_values("price").reset_index(drop=True)

        result = merge_asof(df1, df2, on="price", by="exch")

        expected = pd.DataFrame(
            {
                "symbol": list("AAABBBCCC"),
                "exch": [3, 2, 1, 3, 1, 2, 1, 2, 3],
                "price": [
                    3.2598,
                    3.2599,
                    3.26,
                    12.5,
                    12.58,
                    12.59,
                    378.15,
                    378.2,
                    378.25,
                ],
                "mpv": [0.0001, 0.0001, 0.01, 0.25, 0.01, 0.01, 0.05, 0.1, 0.25],
            },
            columns=["symbol", "exch", "price", "mpv"],
        )

        tm.assert_frame_equal(result, expected)

    def test_merge_datatype_error_raises(self):
        msg = r"Incompatible merge dtype, .*, both sides must have numeric dtype"

        left = pd.DataFrame({"left_val": [1, 5, 10], "a": ["a", "b", "c"]})
        right = pd.DataFrame({"right_val": [1, 2, 3, 6, 7], "a": [1, 2, 3, 6, 7]})

        with pytest.raises(MergeError, match=msg):
            merge_asof(left, right, on="a")

    def test_merge_datatype_categorical_error_raises(self):
        msg = (
            r"incompatible merge keys \[0\] .* both sides category, "
            "but not equal ones"
        )

        left = pd.DataFrame(
            {"left_val": [1, 5, 10], "a": pd.Categorical(["a", "b", "c"])}
        )
        right = pd.DataFrame(
            {
                "right_val": [1, 2, 3, 6, 7],
                "a": pd.Categorical(["a", "X", "c", "X", "b"]),
            }
        )

        with pytest.raises(MergeError, match=msg):
            merge_asof(left, right, on="a")

    def test_merge_groupby_multiple_column_with_categorical_column(self):
        # GH 16454
        df = pd.DataFrame({"x": [0], "y": [0], "z": pd.Categorical([0])})
        result = merge_asof(df, df, on="x", by=["y", "z"])
        expected = pd.DataFrame({"x": [0], "y": [0], "z": pd.Categorical([0])})
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "func", [lambda x: x, lambda x: to_datetime(x)], ids=["numeric", "datetime"]
    )
    @pytest.mark.parametrize("side", ["left", "right"])
    def test_merge_on_nans(self, func, side):
        # GH 23189
        msg = f"Merge keys contain null values on {side} side"
        nulls = func([1.0, 5.0, np.nan])
        non_nulls = func([1.0, 5.0, 10.0])
        df_null = pd.DataFrame({"a": nulls, "left_val": ["a", "b", "c"]})
        df = pd.DataFrame({"a": non_nulls, "right_val": [1, 6, 11]})

        with pytest.raises(ValueError, match=msg):
            if side == "left":
                merge_asof(df_null, df, on="a")
            else:
                merge_asof(df, df_null, on="a")

    def test_by_nullable(self, any_numeric_ea_dtype, using_infer_string):
        # Note: this test passes if instead of using pd.array we use
        #  np.array([np.nan, 1]).  Other than that, I (@jbrockmendel)
        #  have NO IDEA what the expected behavior is.
        # TODO(GH#32306): may be relevant to the expected behavior here.

        arr = pd.array([pd.NA, 0, 1], dtype=any_numeric_ea_dtype)
        if arr.dtype.kind in ["i", "u"]:
            max_val = np.iinfo(arr.dtype.numpy_dtype).max
        else:
            max_val = np.finfo(arr.dtype.numpy_dtype).max
        # set value s.t. (at least for integer dtypes) arr._values_for_argsort
        #  is not an injection
        arr[2] = max_val

        left = pd.DataFrame(
            {
                "by_col1": arr,
                "by_col2": ["HELLO", "To", "You"],
                "on_col": [2, 4, 6],
                "value": ["a", "c", "e"],
            }
        )
        right = pd.DataFrame(
            {
                "by_col1": arr,
                "by_col2": ["WORLD", "Wide", "Web"],
                "on_col": [1, 2, 6],
                "value": ["b", "d", "f"],
            }
        )

        result = merge_asof(left, right, by=["by_col1", "by_col2"], on="on_col")
        expected = pd.DataFrame(
            {
                "by_col1": arr,
                "by_col2": ["HELLO", "To", "You"],
                "on_col": [2, 4, 6],
                "value_x": ["a", "c", "e"],
            }
        )
        expected["value_y"] = np.array([np.nan, np.nan, np.nan], dtype=object)
        if using_infer_string:
            expected["value_y"] = expected["value_y"].astype("str")
        tm.assert_frame_equal(result, expected)

    def test_merge_by_col_tz_aware(self):
        # GH 21184
        left = pd.DataFrame(
            {
                "by_col": pd.DatetimeIndex(["2018-01-01"]).tz_localize("UTC"),
                "on_col": [2],
                "values": ["a"],
            }
        )
        right = pd.DataFrame(
            {
                "by_col": pd.DatetimeIndex(["2018-01-01"]).tz_localize("UTC"),
                "on_col": [1],
                "values": ["b"],
            }
        )
        result = merge_asof(left, right, by="by_col", on="on_col")
        expected = pd.DataFrame(
            [[pd.Timestamp("2018-01-01", tz="UTC"), 2, "a", "b"]],
            columns=["by_col", "on_col", "values_x", "values_y"],
        )
        tm.assert_frame_equal(result, expected)

    def test_by_mixed_tz_aware(self, using_infer_string):
        # GH 26649
        left = pd.DataFrame(
            {
                "by_col1": pd.DatetimeIndex(["2018-01-01"]).tz_localize("UTC"),
                "by_col2": ["HELLO"],
                "on_col": [2],
                "value": ["a"],
            }
        )
        right = pd.DataFrame(
            {
                "by_col1": pd.DatetimeIndex(["2018-01-01"]).tz_localize("UTC"),
                "by_col2": ["WORLD"],
                "on_col": [1],
                "value": ["b"],
            }
        )
        result = merge_asof(left, right, by=["by_col1", "by_col2"], on="on_col")
        expected = pd.DataFrame(
            [[pd.Timestamp("2018-01-01", tz="UTC"), "HELLO", 2, "a"]],
            columns=["by_col1", "by_col2", "on_col", "value_x"],
        )
        expected["value_y"] = np.array([np.nan], dtype=object)
        if using_infer_string:
            expected["value_y"] = expected["value_y"].astype("str")
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("dtype", ["float64", "int16", "m8[ns]", "M8[us]"])
    def test_by_dtype(self, dtype):
        # GH 55453, GH 22794
        left = pd.DataFrame(
            {
                "by_col": np.array([1], dtype=dtype),
                "on_col": [2],
                "value": ["a"],
            }
        )
        right = pd.DataFrame(
            {
                "by_col": np.array([1], dtype=dtype),
                "on_col": [1],
                "value": ["b"],
            }
        )
        result = merge_asof(left, right, by="by_col", on="on_col")
        expected = pd.DataFrame(
            {
                "by_col": np.array([1], dtype=dtype),
                "on_col": [2],
                "value_x": ["a"],
                "value_y": ["b"],
            }
        )
        tm.assert_frame_equal(result, expected)

    def test_timedelta_tolerance_nearest(self, unit):
        # GH 27642
        if unit == "s":
            pytest.skip(
                "This test is invalid with unit='s' because that would "
                "round left['time']"
            )

        left = pd.DataFrame(
            list(zip([0, 5, 10, 15, 20, 25], [0, 1, 2, 3, 4, 5])),
            columns=["time", "left"],
        )

        left["time"] = pd.to_timedelta(left["time"], "ms").astype(f"m8[{unit}]")

        right = pd.DataFrame(
            list(zip([0, 3, 9, 12, 15, 18], [0, 1, 2, 3, 4, 5])),
            columns=["time", "right"],
        )

        right["time"] = pd.to_timedelta(right["time"], "ms").astype(f"m8[{unit}]")

        expected = pd.DataFrame(
            list(
                zip(
                    [0, 5, 10, 15, 20, 25],
                    [0, 1, 2, 3, 4, 5],
                    [0, np.nan, 2, 4, np.nan, np.nan],
                )
            ),
            columns=["time", "left", "right"],
        )

        expected["time"] = pd.to_timedelta(expected["time"], "ms").astype(f"m8[{unit}]")

        result = merge_asof(
            left, right, on="time", tolerance=Timedelta("1ms"), direction="nearest"
        )

        tm.assert_frame_equal(result, expected)

    def test_int_type_tolerance(self, any_int_dtype):
        # GH #28870

        left = pd.DataFrame({"a": [0, 10, 20], "left_val": [1, 2, 3]})
        right = pd.DataFrame({"a": [5, 15, 25], "right_val": [1, 2, 3]})
        left["a"] = left["a"].astype(any_int_dtype)
        right["a"] = right["a"].astype(any_int_dtype)

        expected = pd.DataFrame(
            {"a": [0, 10, 20], "left_val": [1, 2, 3], "right_val": [np.nan, 1.0, 2.0]}
        )
        expected["a"] = expected["a"].astype(any_int_dtype)

        result = merge_asof(left, right, on="a", tolerance=10)
        tm.assert_frame_equal(result, expected)

    def test_merge_index_column_tz(self):
        # GH 29864
        index = pd.date_range("2019-10-01", freq="30min", periods=5, tz="UTC")
        left = pd.DataFrame([0.9, 0.8, 0.7, 0.6], columns=["xyz"], index=index[1:])
        right = pd.DataFrame({"from_date": index, "abc": [2.46] * 4 + [2.19]})
        result = merge_asof(
            left=left, right=right, left_index=True, right_on=["from_date"]
        )
        expected = pd.DataFrame(
            {
                "xyz": [0.9, 0.8, 0.7, 0.6],
                "from_date": index[1:],
                "abc": [2.46] * 3 + [2.19],
            },
            index=pd.date_range(
                "2019-10-01 00:30:00", freq="30min", periods=4, tz="UTC"
            ),
        )
        tm.assert_frame_equal(result, expected)

        result = merge_asof(
            left=right, right=left, right_index=True, left_on=["from_date"]
        )
        expected = pd.DataFrame(
            {
                "from_date": index,
                "abc": [2.46] * 4 + [2.19],
                "xyz": [np.nan, 0.9, 0.8, 0.7, 0.6],
            },
            index=Index([0, 1, 2, 3, 4]),
        )
        tm.assert_frame_equal(result, expected)

    def test_left_index_right_index_tolerance(self, unit):
        # https://github.com/pandas-dev/pandas/issues/35558
        if unit == "s":
            pytest.skip(
                "This test is invalid with unit='s' because that would round dr1"
            )

        dr1 = pd.date_range(
            start="1/1/2020", end="1/20/2020", freq="2D", unit=unit
        ) + Timedelta(seconds=0.4).as_unit(unit)
        dr2 = pd.date_range(start="1/1/2020", end="2/1/2020", unit=unit)

        df1 = pd.DataFrame({"val1": "foo"}, index=pd.DatetimeIndex(dr1))
        df2 = pd.DataFrame({"val2": "bar"}, index=pd.DatetimeIndex(dr2))

        expected = pd.DataFrame(
            {"val1": "foo", "val2": "bar"}, index=pd.DatetimeIndex(dr1)
        )
        result = merge_asof(
            df1,
            df2,
            left_index=True,
            right_index=True,
            tolerance=Timedelta(seconds=0.5),
        )
        tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "infer_string", [False, pytest.param(True, marks=td.skip_if_no("pyarrow"))]
)
@pytest.mark.parametrize(
    "kwargs", [{"on": "x"}, {"left_index": True, "right_index": True}]
)
@pytest.mark.parametrize(
    "data",
    [["2019-06-01 00:09:12", "2019-06-01 00:10:29"], [1.0, "2019-06-01 00:10:29"]],
)
def test_merge_asof_non_numerical_dtype(kwargs, data, infer_string):
    # GH#29130
    with option_context("future.infer_string", infer_string):
        left = pd.DataFrame({"x": data}, index=data)
        right = pd.DataFrame({"x": data}, index=data)
        with pytest.raises(
            MergeError,
            match=r"Incompatible merge dtype, .*, both sides must have numeric dtype",
        ):
            merge_asof(left, right, **kwargs)


def test_merge_asof_non_numerical_dtype_object():
    # GH#29130
    left = pd.DataFrame({"a": ["12", "13", "15"], "left_val1": ["a", "b", "c"]})
    right = pd.DataFrame({"a": ["a", "b", "c"], "left_val": ["d", "e", "f"]})
    with pytest.raises(
        MergeError,
        match=r"Incompatible merge dtype, .*, both sides must have numeric dtype",
    ):
        merge_asof(
            left,
            right,
            left_on="left_val1",
            right_on="a",
            left_by="a",
            right_by="left_val",
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"right_index": True, "left_index": True},
        {"left_on": "left_time", "right_index": True},
        {"left_index": True, "right_on": "right"},
    ],
)
def test_merge_asof_index_behavior(kwargs):
    # GH 33463
    index = Index([1, 5, 10], name="test")
    left = pd.DataFrame({"left": ["a", "b", "c"], "left_time": [1, 4, 10]}, index=index)
    right = pd.DataFrame({"right": [1, 2, 3, 6, 7]}, index=[1, 2, 3, 6, 7])
    result = merge_asof(left, right, **kwargs)

    expected = pd.DataFrame(
        {"left": ["a", "b", "c"], "left_time": [1, 4, 10], "right": [1, 3, 7]},
        index=index,
    )
    tm.assert_frame_equal(result, expected)


def test_merge_asof_numeric_column_in_index():
    # GH#34488
    left = pd.DataFrame({"b": [10, 11, 12]}, index=Index([1, 2, 3], name="a"))
    right = pd.DataFrame({"c": [20, 21, 22]}, index=Index([0, 2, 3], name="a"))

    result = merge_asof(left, right, left_on="a", right_on="a")
    expected = pd.DataFrame({"a": [1, 2, 3], "b": [10, 11, 12], "c": [20, 21, 22]})
    tm.assert_frame_equal(result, expected)


def test_merge_asof_numeric_column_in_multiindex():
    # GH#34488
    left = pd.DataFrame(
        {"b": [10, 11, 12]},
        index=pd.MultiIndex.from_arrays([[1, 2, 3], ["a", "b", "c"]], names=["a", "z"]),
    )
    right = pd.DataFrame(
        {"c": [20, 21, 22]},
        index=pd.MultiIndex.from_arrays([[1, 2, 3], ["x", "y", "z"]], names=["a", "y"]),
    )

    result = merge_asof(left, right, left_on="a", right_on="a")
    expected = pd.DataFrame({"a": [1, 2, 3], "b": [10, 11, 12], "c": [20, 21, 22]})
    tm.assert_frame_equal(result, expected)


def test_merge_asof_numeri_column_in_index_object_dtype():
    # GH#34488
    left = pd.DataFrame({"b": [10, 11, 12]}, index=Index(["1", "2", "3"], name="a"))
    right = pd.DataFrame({"c": [20, 21, 22]}, index=Index(["m", "n", "o"], name="a"))

    with pytest.raises(
        MergeError,
        match=r"Incompatible merge dtype, .*, both sides must have numeric dtype",
    ):
        merge_asof(left, right, left_on="a", right_on="a")

    left = left.reset_index().set_index(["a", "b"])
    right = right.reset_index().set_index(["a", "c"])

    with pytest.raises(
        MergeError,
        match=r"Incompatible merge dtype, .*, both sides must have numeric dtype",
    ):
        merge_asof(left, right, left_on="a", right_on="a")


def test_merge_asof_array_as_on(unit):
    # GH#42844
    dti = pd.DatetimeIndex(
        ["2021/01/01 00:37", "2021/01/01 01:40"], dtype=f"M8[{unit}]"
    )
    right = pd.DataFrame(
        {
            "a": [2, 6],
            "ts": dti,
        }
    )
    ts_merge = pd.date_range(
        start=pd.Timestamp("2021/01/01 00:00"), periods=3, freq="1h", unit=unit
    )
    left = pd.DataFrame({"b": [4, 8, 7]})
    result = merge_asof(
        left,
        right,
        left_on=ts_merge,
        right_on="ts",
        allow_exact_matches=False,
        direction="backward",
    )
    expected = pd.DataFrame({"b": [4, 8, 7], "a": [np.nan, 2, 6], "ts": ts_merge})
    tm.assert_frame_equal(result, expected)

    result = merge_asof(
        right,
        left,
        left_on="ts",
        right_on=ts_merge,
        allow_exact_matches=False,
        direction="backward",
    )
    expected = pd.DataFrame(
        {
            "a": [2, 6],
            "ts": dti,
            "b": [4, 8],
        }
    )
    tm.assert_frame_equal(result, expected)


def test_merge_asof_raise_for_duplicate_columns():
    # GH#50102
    left = pd.DataFrame([[1, 2, "a"]], columns=["a", "a", "left_val"])
    right = pd.DataFrame([[1, 1, 1]], columns=["a", "a", "right_val"])

    with pytest.raises(ValueError, match="column label 'a'"):
        merge_asof(left, right, on="a")

    with pytest.raises(ValueError, match="column label 'a'"):
        merge_asof(left, right, left_on="a", right_on="right_val")

    with pytest.raises(ValueError, match="column label 'a'"):
        merge_asof(left, right, left_on="left_val", right_on="a")


@pytest.mark.parametrize(
    "dtype",
    [
        "Int64",
        pytest.param("int64[pyarrow]", marks=td.skip_if_no("pyarrow")),
        pytest.param("timestamp[s][pyarrow]", marks=td.skip_if_no("pyarrow")),
    ],
)
def test_merge_asof_extension_dtype(dtype):
    # GH 52904
    left = pd.DataFrame(
        {
            "join_col": [1, 3, 5],
            "left_val": [1, 2, 3],
        }
    )
    right = pd.DataFrame(
        {
            "join_col": [2, 3, 4],
            "right_val": [1, 2, 3],
        }
    )
    left = left.astype({"join_col": dtype})
    right = right.astype({"join_col": dtype})
    result = merge_asof(left, right, on="join_col")
    expected = pd.DataFrame(
        {
            "join_col": [1, 3, 5],
            "left_val": [1, 2, 3],
            "right_val": [np.nan, 2.0, 3.0],
        }
    )
    expected = expected.astype({"join_col": dtype})
    tm.assert_frame_equal(result, expected)


@td.skip_if_no("pyarrow")
def test_merge_asof_pyarrow_td_tolerance():
    # GH 56486
    ser = pd.Series(
        [datetime.datetime(2023, 1, 1)], dtype="timestamp[us, UTC][pyarrow]"
    )
    df = pd.DataFrame(
        {
            "timestamp": ser,
            "value": [1],
        }
    )
    result = merge_asof(df, df, on="timestamp", tolerance=Timedelta("1s"))
    expected = pd.DataFrame(
        {
            "timestamp": ser,
            "value_x": [1],
            "value_y": [1],
        }
    )
    tm.assert_frame_equal(result, expected)


def test_merge_asof_read_only_ndarray():
    # GH 53513
    left = pd.Series([2], index=[2], name="left")
    right = pd.Series([1], index=[1], name="right")
    # set to read-only
    left.index.values.flags.writeable = False
    right.index.values.flags.writeable = False
    result = merge_asof(left, right, left_index=True, right_index=True)
    expected = pd.DataFrame({"left": [2], "right": [1]}, index=[2])
    tm.assert_frame_equal(result, expected)


def test_merge_asof_multiby_with_categorical():
    # GH 43541
    left = pd.DataFrame(
        {
            "c1": pd.Categorical(["a", "a", "b", "b"], categories=["a", "b"]),
            "c2": ["x"] * 4,
            "t": [1] * 4,
            "v": range(4),
        }
    )
    right = pd.DataFrame(
        {
            "c1": pd.Categorical(["b", "b"], categories=["b", "a"]),
            "c2": ["x"] * 2,
            "t": [1, 2],
            "v": range(2),
        }
    )
    result = merge_asof(
        left,
        right,
        by=["c1", "c2"],
        on="t",
        direction="forward",
        suffixes=["_left", "_right"],
    )
    expected = pd.DataFrame(
        {
            "c1": pd.Categorical(["a", "a", "b", "b"], categories=["a", "b"]),
            "c2": ["x"] * 4,
            "t": [1] * 4,
            "v_left": range(4),
            "v_right": [np.nan, np.nan, 0.0, 0.0],
        }
    )
    tm.assert_frame_equal(result, expected)
