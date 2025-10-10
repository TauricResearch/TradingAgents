from importlib import import_module
from pkgutil import walk_packages

import matplotlib
import pytest

# Get the names of all matplotlib submodules,
# except for the unit tests and private modules.
module_names = [
    m.name
    for m in walk_packages(
        path=matplotlib.__path__, prefix=f'{matplotlib.__name__}.'
    )
    if not m.name.startswith(__package__)
    and not any(x.startswith('_') for x in m.name.split('.'))
]


@pytest.mark.parametrize('module_name', module_names)
@pytest.mark.filterwarnings('ignore::DeprecationWarning')
@pytest.mark.filterwarnings('ignore::ImportWarning')
def test_getattr(module_name):
    """
    Test that __getattr__ methods raise AttributeError for unknown keys.
    See #20822, #20855.
    """
    try:
        module = import_module(module_name)
    except (ImportError, RuntimeError, OSError) as e:
        # Skip modules that cannot be imported due to missing dependencies
        pytest.skip(f'Cannot import {module_name} due to {e}')

    key = 'THIS_SYMBOL_SHOULD_NOT_EXIST'
    if hasattr(module, key):
        delattr(module, key)
