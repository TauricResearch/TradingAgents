import numpy as np
import pytest

from pandas import (
    DataFrame,
    reset_option,
    set_eng_float_format,
)

from pandas.io.formats.format import EngFormatter


@pytest.fixture(autouse=True)
def reset_float_format():
    yield
    reset_option("display.float_format")


class TestEngFormatter:
    def test_eng_float_formatter2(self, float_frame):
        df = float_frame
        df.loc[5] = 0

        set_eng_float_format()
        repr(df)

        set_eng_float_format(use_eng_prefix=True)
        repr(df)

        set_eng_float_format(accuracy=0)
        repr(df)

    def test_eng_float_formatter(self):
        df = DataFrame({"A": [1.41, 141.0, 14100, 1410000.0]})

        set_eng_float_format()
        result = df.to_string()
        expected = (
            "             A\n"
            "0    1.410E+00\n"
            "1  141.000E+00\n"
            "2   14.100E+03\n"
            "3    1.410E+06"
        )
        assert result == expected

        set_eng_float_format(use_eng_prefix=True)
        result = df.to_string()
        expected = "         A\n0    1.410\n1  141.000\n2  14.100k\n3   1.410M"
        assert result == expected

        set_eng_float_format(accuracy=0)
        result = df.to_string()
        expected = "         A\n0    1E+00\n1  141E+00\n2   14E+03\n3    1E+06"
        assert result == expected

    def compare(self, formatter, input, output):
        formatted_input = formatter(input)
        assert formatted_input == output

    def compare_all(self, formatter, in_out):
        """
        Parameters:
        -----------
        formatter: EngFormatter under test
        in_out: list of tuples. Each tuple = (number, expected_formatting)

        It is tested if 'formatter(number) == expected_formatting'.
        *number* should be >= 0 because formatter(-number) == fmt is also
        tested. *fmt* is derived from *expected_formatting*
        """
        for input, output in in_out:
            self.compare(formatter, input, output)
            self.compare(formatter, -input, "-" + output[1:])

    def test_exponents_with_eng_prefix(self):
        formatter = EngFormatter(accuracy=3, use_eng_prefix=True)
        f = np.sqrt(2)
        in_out = [
            (f * 10**-24, " 1.414y"),
            (f * 10**-23, " 14.142y"),
            (f * 10**-22, " 141.421y"),
            (f * 10**-21, " 1.414z"),
            (f * 10**-20, " 14.142z"),
            (f * 10**-19, " 141.421z"),
            (f * 10**-18, " 1.414a"),
            (f * 10**-17, " 14.142a"),
            (f * 10**-16, " 141.421a"),
            (f * 10**-15, " 1.414f"),
            (f * 10**-14, " 14.142f"),
            (f * 10**-13, " 141.421f"),
            (f * 10**-12, " 1.414p"),
            (f * 10**-11, " 14.142p"),
            (f * 10**-10, " 141.421p"),
            (f * 10**-9, " 1.414n"),
            (f * 10**-8, " 14.142n"),
            (f * 10**-7, " 141.421n"),
            (f * 10**-6, " 1.414u"),
            (f * 10**-5, " 14.142u"),
            (f * 10**-4, " 141.421u"),
            (f * 10**-3, " 1.414m"),
            (f * 10**-2, " 14.142m"),
            (f * 10**-1, " 141.421m"),
            (f * 10**0, " 1.414"),
            (f * 10**1, " 14.142"),
            (f * 10**2, " 141.421"),
            (f * 10**3, " 1.414k"),
            (f * 10**4, " 14.142k"),
            (f * 10**5, " 141.421k"),
            (f * 10**6, " 1.414M"),
            (f * 10**7, " 14.142M"),
            (f * 10**8, " 141.421M"),
            (f * 10**9, " 1.414G"),
            (f * 10**10, " 14.142G"),
            (f * 10**11, " 141.421G"),
            (f * 10**12, " 1.414T"),
            (f * 10**13, " 14.142T"),
            (f * 10**14, " 141.421T"),
            (f * 10**15, " 1.414P"),
            (f * 10**16, " 14.142P"),
            (f * 10**17, " 141.421P"),
            (f * 10**18, " 1.414E"),
            (f * 10**19, " 14.142E"),
            (f * 10**20, " 141.421E"),
            (f * 10**21, " 1.414Z"),
            (f * 10**22, " 14.142Z"),
            (f * 10**23, " 141.421Z"),
            (f * 10**24, " 1.414Y"),
            (f * 10**25, " 14.142Y"),
            (f * 10**26, " 141.421Y"),
        ]
        self.compare_all(formatter, in_out)

    def test_exponents_without_eng_prefix(self):
        formatter = EngFormatter(accuracy=4, use_eng_prefix=False)
        f = np.pi
        in_out = [
            (f * 10**-24, " 3.1416E-24"),
            (f * 10**-23, " 31.4159E-24"),
            (f * 10**-22, " 314.1593E-24"),
            (f * 10**-21, " 3.1416E-21"),
            (f * 10**-20, " 31.4159E-21"),
            (f * 10**-19, " 314.1593E-21"),
            (f * 10**-18, " 3.1416E-18"),
            (f * 10**-17, " 31.4159E-18"),
            (f * 10**-16, " 314.1593E-18"),
            (f * 10**-15, " 3.1416E-15"),
            (f * 10**-14, " 31.4159E-15"),
            (f * 10**-13, " 314.1593E-15"),
            (f * 10**-12, " 3.1416E-12"),
            (f * 10**-11, " 31.4159E-12"),
            (f * 10**-10, " 314.1593E-12"),
            (f * 10**-9, " 3.1416E-09"),
            (f * 10**-8, " 31.4159E-09"),
            (f * 10**-7, " 314.1593E-09"),
            (f * 10**-6, " 3.1416E-06"),
            (f * 10**-5, " 31.4159E-06"),
            (f * 10**-4, " 314.1593E-06"),
            (f * 10**-3, " 3.1416E-03"),
            (f * 10**-2, " 31.4159E-03"),
            (f * 10**-1, " 314.1593E-03"),
            (f * 10**0, " 3.1416E+00"),
            (f * 10**1, " 31.4159E+00"),
            (f * 10**2, " 314.1593E+00"),
            (f * 10**3, " 3.1416E+03"),
            (f * 10**4, " 31.4159E+03"),
            (f * 10**5, " 314.1593E+03"),
            (f * 10**6, " 3.1416E+06"),
            (f * 10**7, " 31.4159E+06"),
            (f * 10**8, " 314.1593E+06"),
            (f * 10**9, " 3.1416E+09"),
            (f * 10**10, " 31.4159E+09"),
            (f * 10**11, " 314.1593E+09"),
            (f * 10**12, " 3.1416E+12"),
            (f * 10**13, " 31.4159E+12"),
            (f * 10**14, " 314.1593E+12"),
            (f * 10**15, " 3.1416E+15"),
            (f * 10**16, " 31.4159E+15"),
            (f * 10**17, " 314.1593E+15"),
            (f * 10**18, " 3.1416E+18"),
            (f * 10**19, " 31.4159E+18"),
            (f * 10**20, " 314.1593E+18"),
            (f * 10**21, " 3.1416E+21"),
            (f * 10**22, " 31.4159E+21"),
            (f * 10**23, " 314.1593E+21"),
            (f * 10**24, " 3.1416E+24"),
            (f * 10**25, " 31.4159E+24"),
            (f * 10**26, " 314.1593E+24"),
        ]
        self.compare_all(formatter, in_out)

    def test_rounding(self):
        formatter = EngFormatter(accuracy=3, use_eng_prefix=True)
        in_out = [
            (5.55555, " 5.556"),
            (55.5555, " 55.556"),
            (555.555, " 555.555"),
            (5555.55, " 5.556k"),
            (55555.5, " 55.556k"),
            (555555, " 555.555k"),
        ]
        self.compare_all(formatter, in_out)

        formatter = EngFormatter(accuracy=1, use_eng_prefix=True)
        in_out = [
            (5.55555, " 5.6"),
            (55.5555, " 55.6"),
            (555.555, " 555.6"),
            (5555.55, " 5.6k"),
            (55555.5, " 55.6k"),
            (555555, " 555.6k"),
        ]
        self.compare_all(formatter, in_out)

        formatter = EngFormatter(accuracy=0, use_eng_prefix=True)
        in_out = [
            (5.55555, " 6"),
            (55.5555, " 56"),
            (555.555, " 556"),
            (5555.55, " 6k"),
            (55555.5, " 56k"),
            (555555, " 556k"),
        ]
        self.compare_all(formatter, in_out)

        formatter = EngFormatter(accuracy=3, use_eng_prefix=True)
        result = formatter(0)
        assert result == " 0.000"

    def test_nan(self):
        # Issue #11981

        formatter = EngFormatter(accuracy=1, use_eng_prefix=True)
        result = formatter(np.nan)
        assert result == "NaN"

        df = DataFrame(
            {
                "a": [1.5, 10.3, 20.5],
                "b": [50.3, 60.67, 70.12],
                "c": [100.2, 101.33, 120.33],
            }
        )
        pt = df.pivot_table(values="a", index="b", columns="c")
        set_eng_float_format(accuracy=1)
        result = pt.to_string()
        assert "NaN" in result

    def test_inf(self):
        # Issue #11981

        formatter = EngFormatter(accuracy=1, use_eng_prefix=True)
        result = formatter(np.inf)
        assert result == "inf"
