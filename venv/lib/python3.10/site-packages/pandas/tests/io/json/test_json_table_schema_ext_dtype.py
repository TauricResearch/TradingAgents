"""Tests for ExtensionDtype Table Schema integration."""

from collections import OrderedDict
import datetime as dt
import decimal
from io import StringIO
import json

import pytest

from pandas import (
    NA,
    DataFrame,
    Index,
    array,
    read_json,
)
import pandas._testing as tm
from pandas.core.arrays.integer import Int64Dtype
from pandas.core.arrays.string_ import StringDtype
from pandas.core.series import Series
from pandas.tests.extension.date import (
    DateArray,
    DateDtype,
)
from pandas.tests.extension.decimal.array import (
    DecimalArray,
    DecimalDtype,
)

from pandas.io.json._table_schema import (
    as_json_table_type,
    build_table_schema,
)


class TestBuildSchema:
    def test_build_table_schema(self):
        df = DataFrame(
            {
                "A": DateArray([dt.date(2021, 10, 10)]),
                "B": DecimalArray([decimal.Decimal(10)]),
                "C": array(["pandas"], dtype="string"),
                "D": array([10], dtype="Int64"),
            }
        )
        result = build_table_schema(df, version=False)
        expected = {
            "fields": [
                {"name": "index", "type": "integer"},
                {"name": "A", "type": "any", "extDtype": "DateDtype"},
                {"name": "B", "type": "number", "extDtype": "decimal"},
                {"name": "C", "type": "string", "extDtype": "string"},
                {"name": "D", "type": "integer", "extDtype": "Int64"},
            ],
            "primaryKey": ["index"],
        }
        assert result == expected
        result = build_table_schema(df)
        assert "pandas_version" in result


class TestTableSchemaType:
    @pytest.mark.parametrize(
        "date_data",
        [
            DateArray([dt.date(2021, 10, 10)]),
            DateArray(dt.date(2021, 10, 10)),
            Series(DateArray(dt.date(2021, 10, 10))),
        ],
    )
    def test_as_json_table_type_ext_date_array_dtype(self, date_data):
        assert as_json_table_type(date_data.dtype) == "any"

    def test_as_json_table_type_ext_date_dtype(self):
        assert as_json_table_type(DateDtype()) == "any"

    @pytest.mark.parametrize(
        "decimal_data",
        [
            DecimalArray([decimal.Decimal(10)]),
            Series(DecimalArray([decimal.Decimal(10)])),
        ],
    )
    def test_as_json_table_type_ext_decimal_array_dtype(self, decimal_data):
        assert as_json_table_type(decimal_data.dtype) == "number"

    def test_as_json_table_type_ext_decimal_dtype(self):
        assert as_json_table_type(DecimalDtype()) == "number"

    @pytest.mark.parametrize(
        "string_data",
        [
            array(["pandas"], dtype="string"),
            Series(array(["pandas"], dtype="string")),
        ],
    )
    def test_as_json_table_type_ext_string_array_dtype(self, string_data):
        assert as_json_table_type(string_data.dtype) == "string"

    def test_as_json_table_type_ext_string_dtype(self):
        assert as_json_table_type(StringDtype()) == "string"

    @pytest.mark.parametrize(
        "integer_data",
        [
            array([10], dtype="Int64"),
            Series(array([10], dtype="Int64")),
        ],
    )
    def test_as_json_table_type_ext_integer_array_dtype(self, integer_data):
        assert as_json_table_type(integer_data.dtype) == "integer"

    def test_as_json_table_type_ext_integer_dtype(self):
        assert as_json_table_type(Int64Dtype()) == "integer"


class TestTableOrient:
    @pytest.fixture
    def da(self):
        return DateArray([dt.date(2021, 10, 10)])

    @pytest.fixture
    def dc(self):
        return DecimalArray([decimal.Decimal(10)])

    @pytest.fixture
    def sa(self):
        return array(["pandas"], dtype="string")

    @pytest.fixture
    def ia(self):
        return array([10], dtype="Int64")

    @pytest.fixture
    def df(self, da, dc, sa, ia):
        return DataFrame(
            {
                "A": da,
                "B": dc,
                "C": sa,
                "D": ia,
            }
        )

    def test_build_date_series(self, da):
        s = Series(da, name="a")
        s.index.name = "id"
        result = s.to_json(orient="table", date_format="iso")
        result = json.loads(result, object_pairs_hook=OrderedDict)

        assert "pandas_version" in result["schema"]
        result["schema"].pop("pandas_version")

        fields = [
            {"name": "id", "type": "integer"},
            {"name": "a", "type": "any", "extDtype": "DateDtype"},
        ]

        schema = {"fields": fields, "primaryKey": ["id"]}

        expected = OrderedDict(
            [
                ("schema", schema),
                ("data", [OrderedDict([("id", 0), ("a", "2021-10-10T00:00:00.000")])]),
            ]
        )

        assert result == expected

    def test_build_decimal_series(self, dc):
        s = Series(dc, name="a")
        s.index.name = "id"
        result = s.to_json(orient="table", date_format="iso")
        result = json.loads(result, object_pairs_hook=OrderedDict)

        assert "pandas_version" in result["schema"]
        result["schema"].pop("pandas_version")

        fields = [
            {"name": "id", "type": "integer"},
            {"name": "a", "type": "number", "extDtype": "decimal"},
        ]

        schema = {"fields": fields, "primaryKey": ["id"]}

        expected = OrderedDict(
            [
                ("schema", schema),
                ("data", [OrderedDict([("id", 0), ("a", 10.0)])]),
            ]
        )

        assert result == expected

    def test_build_string_series(self, sa):
        s = Series(sa, name="a")
        s.index.name = "id"
        result = s.to_json(orient="table", date_format="iso")
        result = json.loads(result, object_pairs_hook=OrderedDict)

        assert "pandas_version" in result["schema"]
        result["schema"].pop("pandas_version")

        fields = [
            {"name": "id", "type": "integer"},
            {"name": "a", "type": "string", "extDtype": "string"},
        ]

        schema = {"fields": fields, "primaryKey": ["id"]}

        expected = OrderedDict(
            [
                ("schema", schema),
                ("data", [OrderedDict([("id", 0), ("a", "pandas")])]),
            ]
        )

        assert result == expected

    def test_build_int64_series(self, ia):
        s = Series(ia, name="a")
        s.index.name = "id"
        result = s.to_json(orient="table", date_format="iso")
        result = json.loads(result, object_pairs_hook=OrderedDict)

        assert "pandas_version" in result["schema"]
        result["schema"].pop("pandas_version")

        fields = [
            {"name": "id", "type": "integer"},
            {"name": "a", "type": "integer", "extDtype": "Int64"},
        ]

        schema = {"fields": fields, "primaryKey": ["id"]}

        expected = OrderedDict(
            [
                ("schema", schema),
                ("data", [OrderedDict([("id", 0), ("a", 10)])]),
            ]
        )

        assert result == expected

    def test_to_json(self, df):
        df = df.copy()
        df.index.name = "idx"
        result = df.to_json(orient="table", date_format="iso")
        result = json.loads(result, object_pairs_hook=OrderedDict)

        assert "pandas_version" in result["schema"]
        result["schema"].pop("pandas_version")

        fields = [
            OrderedDict({"name": "idx", "type": "integer"}),
            OrderedDict({"name": "A", "type": "any", "extDtype": "DateDtype"}),
            OrderedDict({"name": "B", "type": "number", "extDtype": "decimal"}),
            OrderedDict({"name": "C", "type": "string", "extDtype": "string"}),
            OrderedDict({"name": "D", "type": "integer", "extDtype": "Int64"}),
        ]

        schema = OrderedDict({"fields": fields, "primaryKey": ["idx"]})
        data = [
            OrderedDict(
                [
                    ("idx", 0),
                    ("A", "2021-10-10T00:00:00.000"),
                    ("B", 10.0),
                    ("C", "pandas"),
                    ("D", 10),
                ]
            )
        ]
        expected = OrderedDict([("schema", schema), ("data", data)])

        assert result == expected

    def test_json_ext_dtype_reading_roundtrip(self):
        # GH#40255
        df = DataFrame(
            {
                "a": Series([2, NA], dtype="Int64"),
                "b": Series([1.5, NA], dtype="Float64"),
                "c": Series([True, NA], dtype="boolean"),
            },
            index=Index([1, NA], dtype="Int64"),
        )
        expected = df.copy()
        data_json = df.to_json(orient="table", indent=4)
        result = read_json(StringIO(data_json), orient="table")
        tm.assert_frame_equal(result, expected)

    def test_json_ext_dtype_reading(self):
        # GH#40255
        data_json = """{
            "schema":{
                "fields":[
                    {
                        "name":"a",
                        "type":"integer",
                        "extDtype":"Int64"
                    }
                ],
            },
            "data":[
                {
                    "a":2
                },
                {
                    "a":null
                }
            ]
        }"""
        result = read_json(StringIO(data_json), orient="table")
        expected = DataFrame({"a": Series([2, NA], dtype="Int64")})
        tm.assert_frame_equal(result, expected)
