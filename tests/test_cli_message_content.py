import pytest

from cli.main import extract_content_string


@pytest.mark.unit
@pytest.mark.parametrize(
    ("input_value", "expected"),
    [
        ("0", "0"),
        ("False", "False"),
        ("None", "None"),
        ("[]", "[]"),
        ([], None),
        ({}, None),
        ("", None),
        ("   ", None),
        (0, None),
        (False, None),
    ],
)
def test_extract_content_string(input_value, expected):
    assert extract_content_string(input_value) == expected
