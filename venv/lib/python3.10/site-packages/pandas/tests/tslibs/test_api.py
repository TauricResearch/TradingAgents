"""Tests that the tslibs API is locked down"""

from pandas._libs import tslibs


def test_namespace():
    submodules = [
        "base",
        "ccalendar",
        "conversion",
        "dtypes",
        "fields",
        "nattype",
        "np_datetime",
        "offsets",
        "parsing",
        "period",
        "strptime",
        "vectorized",
        "timedeltas",
        "timestamps",
        "timezones",
        "tzconversion",
    ]

    api = [
        "BaseOffset",
        "NaT",
        "NaTType",
        "iNaT",
        "nat_strings",
        "OutOfBoundsDatetime",
        "OutOfBoundsTimedelta",
        "Period",
        "IncompatibleFrequency",
        "Resolution",
        "Tick",
        "Timedelta",
        "dt64arr_to_periodarr",
        "Timestamp",
        "is_date_array_normalized",
        "ints_to_pydatetime",
        "normalize_i8_timestamps",
        "get_resolution",
        "delta_to_nanoseconds",
        "ints_to_pytimedelta",
        "localize_pydatetime",
        "tz_convert_from_utc",
        "tz_convert_from_utc_single",
        "to_offset",
        "tz_compare",
        "is_unitless",
        "astype_overflowsafe",
        "get_unit_from_dtype",
        "periods_per_day",
        "periods_per_second",
        "guess_datetime_format",
        "add_overflowsafe",
        "get_supported_dtype",
        "is_supported_dtype",
    ]

    expected = set(submodules + api)
    names = [x for x in dir(tslibs) if not x.startswith("__")]
    assert set(names) == expected
