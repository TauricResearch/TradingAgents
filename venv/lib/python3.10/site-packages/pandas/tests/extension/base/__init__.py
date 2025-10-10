"""
Base test suite for extension arrays.

These tests are intended for third-party libraries to subclass to validate
that their extension arrays and dtypes satisfy the interface. Moving or
renaming the tests should not be done lightly.

Libraries are expected to implement a few pytest fixtures to provide data
for the tests. The fixtures may be located in either

* The same module as your test class.
* A ``conftest.py`` in the same directory as your test class.

The full list of fixtures may be found in the ``conftest.py`` next to this
file.

.. code-block:: python

   import pytest
   from pandas.tests.extension.base import BaseDtypeTests


   @pytest.fixture
   def dtype():
       return MyDtype()


   class TestMyDtype(BaseDtypeTests):
       pass


Your class ``TestDtype`` will inherit all the tests defined on
``BaseDtypeTests``. pytest's fixture discover will supply your ``dtype``
wherever the test requires it. You're free to implement additional tests.

"""
from pandas.tests.extension.base.accumulate import BaseAccumulateTests
from pandas.tests.extension.base.casting import BaseCastingTests
from pandas.tests.extension.base.constructors import BaseConstructorsTests
from pandas.tests.extension.base.dim2 import (  # noqa: F401
    Dim2CompatTests,
    NDArrayBacked2DTests,
)
from pandas.tests.extension.base.dtype import BaseDtypeTests
from pandas.tests.extension.base.getitem import BaseGetitemTests
from pandas.tests.extension.base.groupby import BaseGroupbyTests
from pandas.tests.extension.base.index import BaseIndexTests
from pandas.tests.extension.base.interface import BaseInterfaceTests
from pandas.tests.extension.base.io import BaseParsingTests
from pandas.tests.extension.base.methods import BaseMethodsTests
from pandas.tests.extension.base.missing import BaseMissingTests
from pandas.tests.extension.base.ops import (  # noqa: F401
    BaseArithmeticOpsTests,
    BaseComparisonOpsTests,
    BaseOpsUtil,
    BaseUnaryOpsTests,
)
from pandas.tests.extension.base.printing import BasePrintingTests
from pandas.tests.extension.base.reduce import BaseReduceTests
from pandas.tests.extension.base.reshaping import BaseReshapingTests
from pandas.tests.extension.base.setitem import BaseSetitemTests


# One test class that you can inherit as an alternative to inheriting all the
# test classes above.
# Note 1) this excludes Dim2CompatTests and NDArrayBacked2DTests.
# Note 2) this uses BaseReduceTests and and _not_ BaseBooleanReduceTests,
#  BaseNoReduceTests, or BaseNumericReduceTests
class ExtensionTests(
    BaseAccumulateTests,
    BaseCastingTests,
    BaseConstructorsTests,
    BaseDtypeTests,
    BaseGetitemTests,
    BaseGroupbyTests,
    BaseIndexTests,
    BaseInterfaceTests,
    BaseParsingTests,
    BaseMethodsTests,
    BaseMissingTests,
    BaseArithmeticOpsTests,
    BaseComparisonOpsTests,
    BaseUnaryOpsTests,
    BasePrintingTests,
    BaseReduceTests,
    BaseReshapingTests,
    BaseSetitemTests,
    Dim2CompatTests,
):
    pass


def __getattr__(name: str):
    import warnings

    if name == "BaseNoReduceTests":
        warnings.warn(
            "BaseNoReduceTests is deprecated and will be removed in a "
            "future version. Use BaseReduceTests and override "
            "`_supports_reduction` instead.",
            FutureWarning,
        )
        from pandas.tests.extension.base.reduce import BaseNoReduceTests

        return BaseNoReduceTests

    elif name == "BaseNumericReduceTests":
        warnings.warn(
            "BaseNumericReduceTests is deprecated and will be removed in a "
            "future version. Use BaseReduceTests and override "
            "`_supports_reduction` instead.",
            FutureWarning,
        )
        from pandas.tests.extension.base.reduce import BaseNumericReduceTests

        return BaseNumericReduceTests

    elif name == "BaseBooleanReduceTests":
        warnings.warn(
            "BaseBooleanReduceTests is deprecated and will be removed in a "
            "future version. Use BaseReduceTests and override "
            "`_supports_reduction` instead.",
            FutureWarning,
        )
        from pandas.tests.extension.base.reduce import BaseBooleanReduceTests

        return BaseBooleanReduceTests

    raise AttributeError(
        f"module 'pandas.tests.extension.base' has no attribute '{name}'"
    )
