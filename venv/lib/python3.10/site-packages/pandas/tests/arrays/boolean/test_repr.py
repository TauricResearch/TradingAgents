import pandas as pd


def test_repr():
    df = pd.DataFrame({"A": pd.array([True, False, None], dtype="boolean")})
    expected = "       A\n0   True\n1  False\n2   <NA>"
    assert repr(df) == expected

    expected = "0     True\n1    False\n2     <NA>\nName: A, dtype: boolean"
    assert repr(df.A) == expected

    expected = "<BooleanArray>\n[True, False, <NA>]\nLength: 3, dtype: boolean"
    assert repr(df.A.array) == expected
