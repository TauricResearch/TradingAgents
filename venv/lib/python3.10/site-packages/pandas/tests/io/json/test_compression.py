from io import (
    BytesIO,
    StringIO,
)

import pytest

import pandas.util._test_decorators as td

import pandas as pd
import pandas._testing as tm


def test_compression_roundtrip(compression):
    df = pd.DataFrame(
        [[0.123456, 0.234567, 0.567567], [12.32112, 123123.2, 321321.2]],
        index=["A", "B"],
        columns=["X", "Y", "Z"],
    )

    with tm.ensure_clean() as path:
        df.to_json(path, compression=compression)
        tm.assert_frame_equal(df, pd.read_json(path, compression=compression))

        # explicitly ensure file was compressed.
        with tm.decompress_file(path, compression) as fh:
            result = fh.read().decode("utf8")
            data = StringIO(result)
        tm.assert_frame_equal(df, pd.read_json(data))


def test_read_zipped_json(datapath):
    uncompressed_path = datapath("io", "json", "data", "tsframe_v012.json")
    uncompressed_df = pd.read_json(uncompressed_path)

    compressed_path = datapath("io", "json", "data", "tsframe_v012.json.zip")
    compressed_df = pd.read_json(compressed_path, compression="zip")

    tm.assert_frame_equal(uncompressed_df, compressed_df)


@td.skip_if_not_us_locale
@pytest.mark.single_cpu
def test_with_s3_url(compression, s3_public_bucket, s3so):
    # Bucket created in tests/io/conftest.py
    df = pd.read_json(StringIO('{"a": [1, 2, 3], "b": [4, 5, 6]}'))

    with tm.ensure_clean() as path:
        df.to_json(path, compression=compression)
        with open(path, "rb") as f:
            s3_public_bucket.put_object(Key="test-1", Body=f)

    roundtripped_df = pd.read_json(
        f"s3://{s3_public_bucket.name}/test-1",
        compression=compression,
        storage_options=s3so,
    )
    tm.assert_frame_equal(df, roundtripped_df)


def test_lines_with_compression(compression):
    with tm.ensure_clean() as path:
        df = pd.read_json(StringIO('{"a": [1, 2, 3], "b": [4, 5, 6]}'))
        df.to_json(path, orient="records", lines=True, compression=compression)
        roundtripped_df = pd.read_json(path, lines=True, compression=compression)
        tm.assert_frame_equal(df, roundtripped_df)


def test_chunksize_with_compression(compression):
    with tm.ensure_clean() as path:
        df = pd.read_json(StringIO('{"a": ["foo", "bar", "baz"], "b": [4, 5, 6]}'))
        df.to_json(path, orient="records", lines=True, compression=compression)

        with pd.read_json(
            path, lines=True, chunksize=1, compression=compression
        ) as res:
            roundtripped_df = pd.concat(res)
        tm.assert_frame_equal(df, roundtripped_df)


def test_write_unsupported_compression_type():
    df = pd.read_json(StringIO('{"a": [1, 2, 3], "b": [4, 5, 6]}'))
    with tm.ensure_clean() as path:
        msg = "Unrecognized compression type: unsupported"
        with pytest.raises(ValueError, match=msg):
            df.to_json(path, compression="unsupported")


def test_read_unsupported_compression_type():
    with tm.ensure_clean() as path:
        msg = "Unrecognized compression type: unsupported"
        with pytest.raises(ValueError, match=msg):
            pd.read_json(path, compression="unsupported")


@pytest.mark.parametrize(
    "infer_string", [False, pytest.param(True, marks=td.skip_if_no("pyarrow"))]
)
@pytest.mark.parametrize("to_infer", [True, False])
@pytest.mark.parametrize("read_infer", [True, False])
def test_to_json_compression(
    compression_only, read_infer, to_infer, compression_to_extension, infer_string
):
    with pd.option_context("future.infer_string", infer_string):
        # see gh-15008
        compression = compression_only

        # We'll complete file extension subsequently.
        filename = "test."
        filename += compression_to_extension[compression]

        df = pd.DataFrame({"A": [1]})

        to_compression = "infer" if to_infer else compression
        read_compression = "infer" if read_infer else compression

        with tm.ensure_clean(filename) as path:
            df.to_json(path, compression=to_compression)
            result = pd.read_json(path, compression=read_compression)
            tm.assert_frame_equal(result, df)


def test_to_json_compression_mode(compression):
    # GH 39985 (read_json does not support user-provided binary files)
    expected = pd.DataFrame({"A": [1]})

    with BytesIO() as buffer:
        expected.to_json(buffer, compression=compression)
        # df = pd.read_json(buffer, compression=compression)
        # tm.assert_frame_equal(expected, df)
