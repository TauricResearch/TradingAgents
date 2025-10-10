from io import BytesIO

import pytest

from pandas import read_csv


def test_streaming_s3_objects():
    # GH17135
    # botocore gained iteration support in 1.10.47, can now be used in read_*
    pytest.importorskip("botocore", minversion="1.10.47")
    from botocore.response import StreamingBody

    data = [b"foo,bar,baz\n1,2,3\n4,5,6\n", b"just,the,header\n"]
    for el in data:
        body = StreamingBody(BytesIO(el), content_length=len(el))
        read_csv(body)


@pytest.mark.single_cpu
def test_read_without_creds_from_pub_bucket(s3_public_bucket_with_data, s3so):
    # GH 34626
    pytest.importorskip("s3fs")
    result = read_csv(
        f"s3://{s3_public_bucket_with_data.name}/tips.csv",
        nrows=3,
        storage_options=s3so,
    )
    assert len(result) == 3


@pytest.mark.single_cpu
def test_read_with_creds_from_pub_bucket(s3_public_bucket_with_data, s3so):
    # Ensure we can read from a public bucket with credentials
    # GH 34626
    pytest.importorskip("s3fs")
    df = read_csv(
        f"s3://{s3_public_bucket_with_data.name}/tips.csv",
        nrows=5,
        header=None,
        storage_options=s3so,
    )
    assert len(df) == 5
