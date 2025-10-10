"""
Tests parsers ability to read and parse non-local files
and hence require a network connection to be read.
"""
from io import BytesIO
import logging
import re

import numpy as np
import pytest

import pandas.util._test_decorators as td

from pandas import DataFrame
import pandas._testing as tm

from pandas.io.feather_format import read_feather
from pandas.io.parsers import read_csv

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)


@pytest.mark.network
@pytest.mark.single_cpu
@pytest.mark.parametrize("mode", ["explicit", "infer"])
@pytest.mark.parametrize("engine", ["python", "c"])
def test_compressed_urls(
    httpserver,
    datapath,
    salaries_table,
    mode,
    engine,
    compression_only,
    compression_to_extension,
):
    # test reading compressed urls with various engines and
    # extension inference
    if compression_only == "tar":
        pytest.skip("TODO: Add tar salaraies.csv to pandas/io/parsers/data")

    extension = compression_to_extension[compression_only]
    with open(datapath("io", "parser", "data", "salaries.csv" + extension), "rb") as f:
        httpserver.serve_content(content=f.read())

    url = httpserver.url + "/salaries.csv" + extension

    if mode != "explicit":
        compression_only = mode

    url_table = read_csv(url, sep="\t", compression=compression_only, engine=engine)
    tm.assert_frame_equal(url_table, salaries_table)


@pytest.mark.network
@pytest.mark.single_cpu
def test_url_encoding_csv(httpserver, datapath):
    """
    read_csv should honor the requested encoding for URLs.

    GH 10424
    """
    with open(datapath("io", "parser", "data", "unicode_series.csv"), "rb") as f:
        httpserver.serve_content(content=f.read())
        df = read_csv(httpserver.url, encoding="latin-1", header=None)
    assert df.loc[15, 1] == "Á köldum klaka (Cold Fever) (1994)"


@pytest.fixture
def tips_df(datapath):
    """DataFrame with the tips dataset."""
    return read_csv(datapath("io", "data", "csv", "tips.csv"))


@pytest.mark.single_cpu
@pytest.mark.usefixtures("s3_resource")
@td.skip_if_not_us_locale()
class TestS3:
    def test_parse_public_s3_bucket(self, s3_public_bucket_with_data, tips_df, s3so):
        # more of an integration test due to the not-public contents portion
        # can probably mock this though.
        pytest.importorskip("s3fs")
        for ext, comp in [("", None), (".gz", "gzip"), (".bz2", "bz2")]:
            df = read_csv(
                f"s3://{s3_public_bucket_with_data.name}/tips.csv" + ext,
                compression=comp,
                storage_options=s3so,
            )
            assert isinstance(df, DataFrame)
            assert not df.empty
            tm.assert_frame_equal(df, tips_df)

    def test_parse_private_s3_bucket(self, s3_private_bucket_with_data, tips_df, s3so):
        # Read public file from bucket with not-public contents
        pytest.importorskip("s3fs")
        df = read_csv(
            f"s3://{s3_private_bucket_with_data.name}/tips.csv", storage_options=s3so
        )
        assert isinstance(df, DataFrame)
        assert not df.empty
        tm.assert_frame_equal(df, tips_df)

    def test_parse_public_s3n_bucket(self, s3_public_bucket_with_data, tips_df, s3so):
        # Read from AWS s3 as "s3n" URL
        df = read_csv(
            f"s3n://{s3_public_bucket_with_data.name}/tips.csv",
            nrows=10,
            storage_options=s3so,
        )
        assert isinstance(df, DataFrame)
        assert not df.empty
        tm.assert_frame_equal(tips_df.iloc[:10], df)

    def test_parse_public_s3a_bucket(self, s3_public_bucket_with_data, tips_df, s3so):
        # Read from AWS s3 as "s3a" URL
        df = read_csv(
            f"s3a://{s3_public_bucket_with_data.name}/tips.csv",
            nrows=10,
            storage_options=s3so,
        )
        assert isinstance(df, DataFrame)
        assert not df.empty
        tm.assert_frame_equal(tips_df.iloc[:10], df)

    def test_parse_public_s3_bucket_nrows(
        self, s3_public_bucket_with_data, tips_df, s3so
    ):
        for ext, comp in [("", None), (".gz", "gzip"), (".bz2", "bz2")]:
            df = read_csv(
                f"s3://{s3_public_bucket_with_data.name}/tips.csv" + ext,
                nrows=10,
                compression=comp,
                storage_options=s3so,
            )
            assert isinstance(df, DataFrame)
            assert not df.empty
            tm.assert_frame_equal(tips_df.iloc[:10], df)

    def test_parse_public_s3_bucket_chunked(
        self, s3_public_bucket_with_data, tips_df, s3so
    ):
        # Read with a chunksize
        chunksize = 5
        for ext, comp in [("", None), (".gz", "gzip"), (".bz2", "bz2")]:
            with read_csv(
                f"s3://{s3_public_bucket_with_data.name}/tips.csv" + ext,
                chunksize=chunksize,
                compression=comp,
                storage_options=s3so,
            ) as df_reader:
                assert df_reader.chunksize == chunksize
                for i_chunk in [0, 1, 2]:
                    # Read a couple of chunks and make sure we see them
                    # properly.
                    df = df_reader.get_chunk()
                    assert isinstance(df, DataFrame)
                    assert not df.empty
                    true_df = tips_df.iloc[
                        chunksize * i_chunk : chunksize * (i_chunk + 1)
                    ]
                    tm.assert_frame_equal(true_df, df)

    def test_parse_public_s3_bucket_chunked_python(
        self, s3_public_bucket_with_data, tips_df, s3so
    ):
        # Read with a chunksize using the Python parser
        chunksize = 5
        for ext, comp in [("", None), (".gz", "gzip"), (".bz2", "bz2")]:
            with read_csv(
                f"s3://{s3_public_bucket_with_data.name}/tips.csv" + ext,
                chunksize=chunksize,
                compression=comp,
                engine="python",
                storage_options=s3so,
            ) as df_reader:
                assert df_reader.chunksize == chunksize
                for i_chunk in [0, 1, 2]:
                    # Read a couple of chunks and make sure we see them properly.
                    df = df_reader.get_chunk()
                    assert isinstance(df, DataFrame)
                    assert not df.empty
                    true_df = tips_df.iloc[
                        chunksize * i_chunk : chunksize * (i_chunk + 1)
                    ]
                    tm.assert_frame_equal(true_df, df)

    def test_parse_public_s3_bucket_python(
        self, s3_public_bucket_with_data, tips_df, s3so
    ):
        for ext, comp in [("", None), (".gz", "gzip"), (".bz2", "bz2")]:
            df = read_csv(
                f"s3://{s3_public_bucket_with_data.name}/tips.csv" + ext,
                engine="python",
                compression=comp,
                storage_options=s3so,
            )
            assert isinstance(df, DataFrame)
            assert not df.empty
            tm.assert_frame_equal(df, tips_df)

    def test_infer_s3_compression(self, s3_public_bucket_with_data, tips_df, s3so):
        for ext in ["", ".gz", ".bz2"]:
            df = read_csv(
                f"s3://{s3_public_bucket_with_data.name}/tips.csv" + ext,
                engine="python",
                compression="infer",
                storage_options=s3so,
            )
            assert isinstance(df, DataFrame)
            assert not df.empty
            tm.assert_frame_equal(df, tips_df)

    def test_parse_public_s3_bucket_nrows_python(
        self, s3_public_bucket_with_data, tips_df, s3so
    ):
        for ext, comp in [("", None), (".gz", "gzip"), (".bz2", "bz2")]:
            df = read_csv(
                f"s3://{s3_public_bucket_with_data.name}/tips.csv" + ext,
                engine="python",
                nrows=10,
                compression=comp,
                storage_options=s3so,
            )
            assert isinstance(df, DataFrame)
            assert not df.empty
            tm.assert_frame_equal(tips_df.iloc[:10], df)

    def test_read_s3_fails(self, s3so):
        msg = "The specified bucket does not exist"
        with pytest.raises(OSError, match=msg):
            read_csv("s3://nyqpug/asdf.csv", storage_options=s3so)

    def test_read_s3_fails_private(self, s3_private_bucket, s3so):
        msg = "The specified bucket does not exist"
        # Receive a permission error when trying to read a private bucket.
        # It's irrelevant here that this isn't actually a table.
        with pytest.raises(OSError, match=msg):
            read_csv(f"s3://{s3_private_bucket.name}/file.csv")

    @pytest.mark.xfail(reason="GH#39155 s3fs upgrade", strict=False)
    def test_write_s3_csv_fails(self, tips_df, s3so):
        # GH 32486
        # Attempting to write to an invalid S3 path should raise
        import botocore

        # GH 34087
        # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/error-handling.html
        # Catch a ClientError since AWS Service Errors are defined dynamically
        error = (FileNotFoundError, botocore.exceptions.ClientError)

        with pytest.raises(error, match="The specified bucket does not exist"):
            tips_df.to_csv(
                "s3://an_s3_bucket_data_doesnt_exit/not_real.csv", storage_options=s3so
            )

    @pytest.mark.xfail(reason="GH#39155 s3fs upgrade", strict=False)
    def test_write_s3_parquet_fails(self, tips_df, s3so):
        # GH 27679
        # Attempting to write to an invalid S3 path should raise
        pytest.importorskip("pyarrow")
        import botocore

        # GH 34087
        # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/error-handling.html
        # Catch a ClientError since AWS Service Errors are defined dynamically
        error = (FileNotFoundError, botocore.exceptions.ClientError)

        with pytest.raises(error, match="The specified bucket does not exist"):
            tips_df.to_parquet(
                "s3://an_s3_bucket_data_doesnt_exit/not_real.parquet",
                storage_options=s3so,
            )

    @pytest.mark.single_cpu
    def test_read_csv_handles_boto_s3_object(
        self, s3_public_bucket_with_data, tips_file
    ):
        # see gh-16135

        s3_object = s3_public_bucket_with_data.Object("tips.csv")

        with BytesIO(s3_object.get()["Body"].read()) as buffer:
            result = read_csv(buffer, encoding="utf8")
        assert isinstance(result, DataFrame)
        assert not result.empty

        expected = read_csv(tips_file)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.single_cpu
    def test_read_csv_chunked_download(self, s3_public_bucket, caplog, s3so):
        # 8 MB, S3FS uses 5MB chunks
        df = DataFrame(np.zeros((100000, 4)), columns=list("abcd"))
        with BytesIO(df.to_csv().encode("utf-8")) as buf:
            s3_public_bucket.put_object(Key="large-file.csv", Body=buf)
            uri = f"{s3_public_bucket.name}/large-file.csv"
            match_re = re.compile(rf"^Fetch: {uri}, 0-(?P<stop>\d+)$")
            with caplog.at_level(logging.DEBUG, logger="s3fs"):
                read_csv(
                    f"s3://{uri}",
                    nrows=5,
                    storage_options=s3so,
                )
                for log in caplog.messages:
                    if match := re.match(match_re, log):
                        # Less than 8 MB
                        assert int(match.group("stop")) < 8000000

    def test_read_s3_with_hash_in_key(self, s3_public_bucket_with_data, tips_df, s3so):
        # GH 25945
        result = read_csv(
            f"s3://{s3_public_bucket_with_data.name}/tips#1.csv", storage_options=s3so
        )
        tm.assert_frame_equal(tips_df, result)

    def test_read_feather_s3_file_path(
        self, s3_public_bucket_with_data, feather_file, s3so
    ):
        # GH 29055
        pytest.importorskip("pyarrow")
        expected = read_feather(feather_file)
        res = read_feather(
            f"s3://{s3_public_bucket_with_data.name}/simple_dataset.feather",
            storage_options=s3so,
        )
        tm.assert_frame_equal(expected, res)
