"""
Tests compressed data parsing functionality for all
of the parsers defined in parsers.py
"""

import os
from pathlib import Path
import tarfile
import zipfile

import pytest

from pandas import DataFrame
import pandas._testing as tm

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)


@pytest.fixture(params=[True, False])
def buffer(request):
    return request.param


@pytest.fixture
def parser_and_data(all_parsers, csv1):
    parser = all_parsers

    with open(csv1, "rb") as f:
        data = f.read()
    expected = parser.read_csv(csv1)

    return parser, data, expected


@pytest.mark.parametrize("compression", ["zip", "infer", "zip2"])
def test_zip(parser_and_data, compression):
    parser, data, expected = parser_and_data

    with tm.ensure_clean("test_file.zip") as path:
        with zipfile.ZipFile(path, mode="w") as tmp:
            tmp.writestr("test_file", data)

        if compression == "zip2":
            with open(path, "rb") as f:
                result = parser.read_csv(f, compression="zip")
        else:
            result = parser.read_csv(path, compression=compression)

        tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("compression", ["zip", "infer"])
def test_zip_error_multiple_files(parser_and_data, compression):
    parser, data, expected = parser_and_data

    with tm.ensure_clean("combined_zip.zip") as path:
        inner_file_names = ["test_file", "second_file"]

        with zipfile.ZipFile(path, mode="w") as tmp:
            for file_name in inner_file_names:
                tmp.writestr(file_name, data)

        with pytest.raises(ValueError, match="Multiple files"):
            parser.read_csv(path, compression=compression)


def test_zip_error_no_files(parser_and_data):
    parser, _, _ = parser_and_data

    with tm.ensure_clean() as path:
        with zipfile.ZipFile(path, mode="w"):
            pass

        with pytest.raises(ValueError, match="Zero files"):
            parser.read_csv(path, compression="zip")


def test_zip_error_invalid_zip(parser_and_data):
    parser, _, _ = parser_and_data

    with tm.ensure_clean() as path:
        with open(path, "rb") as f:
            with pytest.raises(zipfile.BadZipFile, match="File is not a zip file"):
                parser.read_csv(f, compression="zip")


@pytest.mark.parametrize("filename", [None, "test.{ext}"])
def test_compression(
    request,
    parser_and_data,
    compression_only,
    buffer,
    filename,
    compression_to_extension,
):
    parser, data, expected = parser_and_data
    compress_type = compression_only

    ext = compression_to_extension[compress_type]
    filename = filename if filename is None else filename.format(ext=ext)

    if filename and buffer:
        request.applymarker(
            pytest.mark.xfail(
                reason="Cannot deduce compression from buffer of compressed data."
            )
        )

    with tm.ensure_clean(filename=filename) as path:
        tm.write_to_compressed(compress_type, path, data)
        compression = "infer" if filename else compress_type

        if buffer:
            with open(path, "rb") as f:
                result = parser.read_csv(f, compression=compression)
        else:
            result = parser.read_csv(path, compression=compression)

        tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("ext", [None, "gz", "bz2"])
def test_infer_compression(all_parsers, csv1, buffer, ext):
    # see gh-9770
    parser = all_parsers
    kwargs = {"index_col": 0, "parse_dates": True}

    expected = parser.read_csv(csv1, **kwargs)
    kwargs["compression"] = "infer"

    if buffer:
        with open(csv1, encoding="utf-8") as f:
            result = parser.read_csv(f, **kwargs)
    else:
        ext = "." + ext if ext else ""
        result = parser.read_csv(csv1 + ext, **kwargs)

    tm.assert_frame_equal(result, expected)


def test_compression_utf_encoding(all_parsers, csv_dir_path, utf_value, encoding_fmt):
    # see gh-18071, gh-24130
    parser = all_parsers
    encoding = encoding_fmt.format(utf_value)
    path = os.path.join(csv_dir_path, f"utf{utf_value}_ex_small.zip")

    result = parser.read_csv(path, encoding=encoding, compression="zip", sep="\t")
    expected = DataFrame(
        {
            "Country": ["Venezuela", "Venezuela"],
            "Twitter": ["Hugo Chávez Frías", "Henrique Capriles R."],
        }
    )

    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("invalid_compression", ["sfark", "bz3", "zipper"])
def test_invalid_compression(all_parsers, invalid_compression):
    parser = all_parsers
    compress_kwargs = {"compression": invalid_compression}

    msg = f"Unrecognized compression type: {invalid_compression}"

    with pytest.raises(ValueError, match=msg):
        parser.read_csv("test_file.zip", **compress_kwargs)


def test_compression_tar_archive(all_parsers, csv_dir_path):
    parser = all_parsers
    path = os.path.join(csv_dir_path, "tar_csv.tar.gz")
    df = parser.read_csv(path)
    assert list(df.columns) == ["a"]


def test_ignore_compression_extension(all_parsers):
    parser = all_parsers
    df = DataFrame({"a": [0, 1]})
    with tm.ensure_clean("test.csv") as path_csv:
        with tm.ensure_clean("test.csv.zip") as path_zip:
            # make sure to create un-compressed file with zip extension
            df.to_csv(path_csv, index=False)
            Path(path_zip).write_text(
                Path(path_csv).read_text(encoding="utf-8"), encoding="utf-8"
            )

            tm.assert_frame_equal(parser.read_csv(path_zip, compression=None), df)


def test_writes_tar_gz(all_parsers):
    parser = all_parsers
    data = DataFrame(
        {
            "Country": ["Venezuela", "Venezuela"],
            "Twitter": ["Hugo Chávez Frías", "Henrique Capriles R."],
        }
    )
    with tm.ensure_clean("test.tar.gz") as tar_path:
        data.to_csv(tar_path, index=False)

        # test that read_csv infers .tar.gz to gzip:
        tm.assert_frame_equal(parser.read_csv(tar_path), data)

        # test that file is indeed gzipped:
        with tarfile.open(tar_path, "r:gz") as tar:
            result = parser.read_csv(
                tar.extractfile(tar.getnames()[0]), compression="infer"
            )
            tm.assert_frame_equal(result, data)
