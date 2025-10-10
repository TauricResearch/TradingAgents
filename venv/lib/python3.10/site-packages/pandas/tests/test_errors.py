import pytest

from pandas.errors import (
    AbstractMethodError,
    UndefinedVariableError,
)

import pandas as pd


@pytest.mark.parametrize(
    "exc",
    [
        "AttributeConflictWarning",
        "CSSWarning",
        "CategoricalConversionWarning",
        "ClosedFileError",
        "DataError",
        "DatabaseError",
        "DtypeWarning",
        "EmptyDataError",
        "IncompatibilityWarning",
        "IndexingError",
        "InvalidColumnName",
        "InvalidComparison",
        "InvalidVersion",
        "LossySetitemError",
        "MergeError",
        "NoBufferPresent",
        "NumExprClobberingError",
        "NumbaUtilError",
        "OptionError",
        "OutOfBoundsDatetime",
        "ParserError",
        "ParserWarning",
        "PerformanceWarning",
        "PossibleDataLossError",
        "PossiblePrecisionLoss",
        "PyperclipException",
        "SettingWithCopyError",
        "SettingWithCopyWarning",
        "SpecificationError",
        "UnsortedIndexError",
        "UnsupportedFunctionCall",
        "ValueLabelTypeMismatch",
    ],
)
def test_exception_importable(exc):
    from pandas import errors

    err = getattr(errors, exc)
    assert err is not None

    # check that we can raise on them

    msg = "^$"

    with pytest.raises(err, match=msg):
        raise err()


def test_catch_oob():
    from pandas import errors

    msg = "Cannot cast 1500-01-01 00:00:00 to unit='ns' without overflow"
    with pytest.raises(errors.OutOfBoundsDatetime, match=msg):
        pd.Timestamp("15000101").as_unit("ns")


@pytest.mark.parametrize(
    "is_local",
    [
        True,
        False,
    ],
)
def test_catch_undefined_variable_error(is_local):
    variable_name = "x"
    if is_local:
        msg = f"local variable '{variable_name}' is not defined"
    else:
        msg = f"name '{variable_name}' is not defined"

    with pytest.raises(UndefinedVariableError, match=msg):
        raise UndefinedVariableError(variable_name, is_local)


class Foo:
    @classmethod
    def classmethod(cls):
        raise AbstractMethodError(cls, methodtype="classmethod")

    @property
    def property(self):
        raise AbstractMethodError(self, methodtype="property")

    def method(self):
        raise AbstractMethodError(self)


def test_AbstractMethodError_classmethod():
    xpr = "This classmethod must be defined in the concrete class Foo"
    with pytest.raises(AbstractMethodError, match=xpr):
        Foo.classmethod()

    xpr = "This property must be defined in the concrete class Foo"
    with pytest.raises(AbstractMethodError, match=xpr):
        Foo().property

    xpr = "This method must be defined in the concrete class Foo"
    with pytest.raises(AbstractMethodError, match=xpr):
        Foo().method()
