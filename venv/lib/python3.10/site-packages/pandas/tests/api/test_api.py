from __future__ import annotations

import pytest

import pandas as pd
from pandas import api
import pandas._testing as tm
from pandas.api import (
    extensions as api_extensions,
    indexers as api_indexers,
    interchange as api_interchange,
    types as api_types,
    typing as api_typing,
)


class Base:
    def check(self, namespace, expected, ignored=None):
        # see which names are in the namespace, minus optional
        # ignored ones
        # compare vs the expected

        result = sorted(
            f for f in dir(namespace) if not f.startswith("__") and f != "annotations"
        )
        if ignored is not None:
            result = sorted(set(result) - set(ignored))

        expected = sorted(expected)
        tm.assert_almost_equal(result, expected)


class TestPDApi(Base):
    # these are optionally imported based on testing
    # & need to be ignored
    ignored = ["tests", "locale", "conftest", "_version_meson"]

    # top-level sub-packages
    public_lib = [
        "api",
        "arrays",
        "options",
        "test",
        "testing",
        "errors",
        "plotting",
        "io",
        "tseries",
    ]
    private_lib = ["compat", "core", "pandas", "util", "_built_with_meson"]

    # misc
    misc = ["IndexSlice", "NaT", "NA"]

    # top-level classes
    classes = [
        "ArrowDtype",
        "Categorical",
        "CategoricalIndex",
        "DataFrame",
        "DateOffset",
        "DatetimeIndex",
        "ExcelFile",
        "ExcelWriter",
        "Flags",
        "Grouper",
        "HDFStore",
        "Index",
        "MultiIndex",
        "Period",
        "PeriodIndex",
        "RangeIndex",
        "Series",
        "SparseDtype",
        "StringDtype",
        "Timedelta",
        "TimedeltaIndex",
        "Timestamp",
        "Interval",
        "IntervalIndex",
        "CategoricalDtype",
        "PeriodDtype",
        "IntervalDtype",
        "DatetimeTZDtype",
        "BooleanDtype",
        "Int8Dtype",
        "Int16Dtype",
        "Int32Dtype",
        "Int64Dtype",
        "UInt8Dtype",
        "UInt16Dtype",
        "UInt32Dtype",
        "UInt64Dtype",
        "Float32Dtype",
        "Float64Dtype",
        "NamedAgg",
    ]

    # these are already deprecated; awaiting removal
    deprecated_classes: list[str] = []

    # external modules exposed in pandas namespace
    modules: list[str] = []

    # top-level functions
    funcs = [
        "array",
        "bdate_range",
        "concat",
        "crosstab",
        "cut",
        "date_range",
        "interval_range",
        "eval",
        "factorize",
        "get_dummies",
        "from_dummies",
        "infer_freq",
        "isna",
        "isnull",
        "lreshape",
        "melt",
        "notna",
        "notnull",
        "offsets",
        "merge",
        "merge_ordered",
        "merge_asof",
        "period_range",
        "pivot",
        "pivot_table",
        "qcut",
        "show_versions",
        "timedelta_range",
        "unique",
        "value_counts",
        "wide_to_long",
    ]

    # top-level option funcs
    funcs_option = [
        "reset_option",
        "describe_option",
        "get_option",
        "option_context",
        "set_option",
        "set_eng_float_format",
    ]

    # top-level read_* funcs
    funcs_read = [
        "read_clipboard",
        "read_csv",
        "read_excel",
        "read_fwf",
        "read_gbq",
        "read_hdf",
        "read_html",
        "read_xml",
        "read_json",
        "read_pickle",
        "read_sas",
        "read_sql",
        "read_sql_query",
        "read_sql_table",
        "read_stata",
        "read_table",
        "read_feather",
        "read_parquet",
        "read_orc",
        "read_spss",
    ]

    # top-level json funcs
    funcs_json = ["json_normalize"]

    # top-level to_* funcs
    funcs_to = ["to_datetime", "to_numeric", "to_pickle", "to_timedelta"]

    # top-level to deprecate in the future
    deprecated_funcs_in_future: list[str] = []

    # these are already deprecated; awaiting removal
    deprecated_funcs: list[str] = []

    # private modules in pandas namespace
    private_modules = [
        "_config",
        "_libs",
        "_is_numpy_dev",
        "_pandas_datetime_CAPI",
        "_pandas_parser_CAPI",
        "_testing",
        "_typing",
    ]
    if not pd._built_with_meson:
        private_modules.append("_version")

    def test_api(self):
        checkthese = (
            self.public_lib
            + self.private_lib
            + self.misc
            + self.modules
            + self.classes
            + self.funcs
            + self.funcs_option
            + self.funcs_read
            + self.funcs_json
            + self.funcs_to
            + self.private_modules
        )
        self.check(namespace=pd, expected=checkthese, ignored=self.ignored)

    def test_api_all(self):
        expected = set(
            self.public_lib
            + self.misc
            + self.modules
            + self.classes
            + self.funcs
            + self.funcs_option
            + self.funcs_read
            + self.funcs_json
            + self.funcs_to
        ) - set(self.deprecated_classes)
        actual = set(pd.__all__)

        extraneous = actual - expected
        assert not extraneous

        missing = expected - actual
        assert not missing

    def test_depr(self):
        deprecated_list = (
            self.deprecated_classes
            + self.deprecated_funcs
            + self.deprecated_funcs_in_future
        )
        for depr in deprecated_list:
            with tm.assert_produces_warning(FutureWarning):
                _ = getattr(pd, depr)


class TestApi(Base):
    allowed_api_dirs = [
        "types",
        "extensions",
        "indexers",
        "interchange",
        "typing",
    ]
    allowed_typing = [
        "DataFrameGroupBy",
        "DatetimeIndexResamplerGroupby",
        "Expanding",
        "ExpandingGroupby",
        "ExponentialMovingWindow",
        "ExponentialMovingWindowGroupby",
        "JsonReader",
        "NaTType",
        "NAType",
        "PeriodIndexResamplerGroupby",
        "Resampler",
        "Rolling",
        "RollingGroupby",
        "SeriesGroupBy",
        "StataReader",
        "TimedeltaIndexResamplerGroupby",
        "TimeGrouper",
        "Window",
    ]
    allowed_api_types = [
        "is_any_real_numeric_dtype",
        "is_array_like",
        "is_bool",
        "is_bool_dtype",
        "is_categorical_dtype",
        "is_complex",
        "is_complex_dtype",
        "is_datetime64_any_dtype",
        "is_datetime64_dtype",
        "is_datetime64_ns_dtype",
        "is_datetime64tz_dtype",
        "is_dict_like",
        "is_dtype_equal",
        "is_extension_array_dtype",
        "is_file_like",
        "is_float",
        "is_float_dtype",
        "is_hashable",
        "is_int64_dtype",
        "is_integer",
        "is_integer_dtype",
        "is_interval",
        "is_interval_dtype",
        "is_iterator",
        "is_list_like",
        "is_named_tuple",
        "is_number",
        "is_numeric_dtype",
        "is_object_dtype",
        "is_period_dtype",
        "is_re",
        "is_re_compilable",
        "is_scalar",
        "is_signed_integer_dtype",
        "is_sparse",
        "is_string_dtype",
        "is_timedelta64_dtype",
        "is_timedelta64_ns_dtype",
        "is_unsigned_integer_dtype",
        "pandas_dtype",
        "infer_dtype",
        "union_categoricals",
        "CategoricalDtype",
        "DatetimeTZDtype",
        "IntervalDtype",
        "PeriodDtype",
    ]
    allowed_api_interchange = ["from_dataframe", "DataFrame"]
    allowed_api_indexers = [
        "check_array_indexer",
        "BaseIndexer",
        "FixedForwardWindowIndexer",
        "VariableOffsetWindowIndexer",
    ]
    allowed_api_extensions = [
        "no_default",
        "ExtensionDtype",
        "register_extension_dtype",
        "register_dataframe_accessor",
        "register_index_accessor",
        "register_series_accessor",
        "take",
        "ExtensionArray",
        "ExtensionScalarOpsMixin",
    ]

    def test_api(self):
        self.check(api, self.allowed_api_dirs)

    def test_api_typing(self):
        self.check(api_typing, self.allowed_typing)

    def test_api_types(self):
        self.check(api_types, self.allowed_api_types)

    def test_api_interchange(self):
        self.check(api_interchange, self.allowed_api_interchange)

    def test_api_indexers(self):
        self.check(api_indexers, self.allowed_api_indexers)

    def test_api_extensions(self):
        self.check(api_extensions, self.allowed_api_extensions)


class TestTesting(Base):
    funcs = [
        "assert_frame_equal",
        "assert_series_equal",
        "assert_index_equal",
        "assert_extension_array_equal",
    ]

    def test_testing(self):
        from pandas import testing

        self.check(testing, self.funcs)

    def test_util_in_top_level(self):
        with pytest.raises(AttributeError, match="foo"):
            pd.util.foo


def test_pandas_array_alias():
    msg = "PandasArray has been renamed NumpyExtensionArray"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        res = pd.arrays.PandasArray

    assert res is pd.arrays.NumpyExtensionArray
