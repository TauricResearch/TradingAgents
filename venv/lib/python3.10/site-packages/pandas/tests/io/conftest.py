import shlex
import subprocess
import time
import uuid

import pytest

from pandas.compat import (
    is_ci_environment,
    is_platform_arm,
    is_platform_mac,
    is_platform_windows,
)
import pandas.util._test_decorators as td

import pandas.io.common as icom
from pandas.io.parsers import read_csv


@pytest.fixture
def compression_to_extension():
    return {value: key for key, value in icom.extension_to_compression.items()}


@pytest.fixture
def tips_file(datapath):
    """Path to the tips dataset"""
    return datapath("io", "data", "csv", "tips.csv")


@pytest.fixture
def jsonl_file(datapath):
    """Path to a JSONL dataset"""
    return datapath("io", "parser", "data", "items.jsonl")


@pytest.fixture
def salaries_table(datapath):
    """DataFrame with the salaries dataset"""
    return read_csv(datapath("io", "parser", "data", "salaries.csv"), sep="\t")


@pytest.fixture
def feather_file(datapath):
    return datapath("io", "data", "feather", "feather-0_3_1.feather")


@pytest.fixture
def xml_file(datapath):
    return datapath("io", "data", "xml", "books.xml")


@pytest.fixture
def s3_base(worker_id, monkeypatch):
    """
    Fixture for mocking S3 interaction.

    Sets up moto server in separate process locally
    Return url for motoserver/moto CI service
    """
    pytest.importorskip("s3fs")
    pytest.importorskip("boto3")

    # temporary workaround as moto fails for botocore >= 1.11 otherwise,
    # see https://github.com/spulec/moto/issues/1924 & 1952
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "foobar_key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "foobar_secret")
    if is_ci_environment():
        if is_platform_arm() or is_platform_mac() or is_platform_windows():
            # NOT RUN on Windows/macOS, only Ubuntu
            # - subprocess in CI can cause timeouts
            # - GitHub Actions do not support
            #   container services for the above OSs
            pytest.skip(
                "S3 tests do not have a corresponding service on "
                "Windows or macOS platforms"
            )
        else:
            # set in .github/workflows/unit-tests.yml
            yield "http://localhost:5000"
    else:
        requests = pytest.importorskip("requests")
        pytest.importorskip("moto")
        pytest.importorskip("flask")  # server mode needs flask too

        # Launching moto in server mode, i.e., as a separate process
        # with an S3 endpoint on localhost

        worker_id = "5" if worker_id == "master" else worker_id.lstrip("gw")
        endpoint_port = f"555{worker_id}"
        endpoint_uri = f"http://127.0.0.1:{endpoint_port}/"

        # pipe to null to avoid logging in terminal
        with subprocess.Popen(
            shlex.split(f"moto_server s3 -p {endpoint_port}"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ) as proc:
            timeout = 5
            while timeout > 0:
                try:
                    # OK to go once server is accepting connections
                    r = requests.get(endpoint_uri)
                    if r.ok:
                        break
                except Exception:
                    pass
                timeout -= 0.1
                time.sleep(0.1)
            yield endpoint_uri

            proc.terminate()


@pytest.fixture
def s3so(s3_base):
    return {"client_kwargs": {"endpoint_url": s3_base}}


@pytest.fixture
def s3_resource(s3_base):
    import boto3

    s3 = boto3.resource("s3", endpoint_url=s3_base)
    return s3


@pytest.fixture
def s3_public_bucket(s3_resource):
    bucket = s3_resource.Bucket(f"pandas-test-{uuid.uuid4()}")
    bucket.create()
    yield bucket
    bucket.objects.delete()
    bucket.delete()


@pytest.fixture
def s3_public_bucket_with_data(
    s3_public_bucket, tips_file, jsonl_file, feather_file, xml_file
):
    """
    The following datasets
    are loaded.

    - tips.csv
    - tips.csv.gz
    - tips.csv.bz2
    - items.jsonl
    """
    test_s3_files = [
        ("tips#1.csv", tips_file),
        ("tips.csv", tips_file),
        ("tips.csv.gz", tips_file + ".gz"),
        ("tips.csv.bz2", tips_file + ".bz2"),
        ("items.jsonl", jsonl_file),
        ("simple_dataset.feather", feather_file),
        ("books.xml", xml_file),
    ]
    for s3_key, file_name in test_s3_files:
        with open(file_name, "rb") as f:
            s3_public_bucket.put_object(Key=s3_key, Body=f)
    return s3_public_bucket


@pytest.fixture
def s3_private_bucket(s3_resource):
    bucket = s3_resource.Bucket(f"cant_get_it-{uuid.uuid4()}")
    bucket.create(ACL="private")
    yield bucket
    bucket.objects.delete()
    bucket.delete()


@pytest.fixture
def s3_private_bucket_with_data(
    s3_private_bucket, tips_file, jsonl_file, feather_file, xml_file
):
    """
    The following datasets
    are loaded.

    - tips.csv
    - tips.csv.gz
    - tips.csv.bz2
    - items.jsonl
    """
    test_s3_files = [
        ("tips#1.csv", tips_file),
        ("tips.csv", tips_file),
        ("tips.csv.gz", tips_file + ".gz"),
        ("tips.csv.bz2", tips_file + ".bz2"),
        ("items.jsonl", jsonl_file),
        ("simple_dataset.feather", feather_file),
        ("books.xml", xml_file),
    ]
    for s3_key, file_name in test_s3_files:
        with open(file_name, "rb") as f:
            s3_private_bucket.put_object(Key=s3_key, Body=f)
    return s3_private_bucket


_compression_formats_params = [
    (".no_compress", None),
    ("", None),
    (".gz", "gzip"),
    (".GZ", "gzip"),
    (".bz2", "bz2"),
    (".BZ2", "bz2"),
    (".zip", "zip"),
    (".ZIP", "zip"),
    (".xz", "xz"),
    (".XZ", "xz"),
    pytest.param((".zst", "zstd"), marks=td.skip_if_no("zstandard")),
    pytest.param((".ZST", "zstd"), marks=td.skip_if_no("zstandard")),
]


@pytest.fixture(params=_compression_formats_params[1:])
def compression_format(request):
    return request.param


@pytest.fixture(params=_compression_formats_params)
def compression_ext(request):
    return request.param[0]
