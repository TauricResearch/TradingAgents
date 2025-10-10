import pytest


@pytest.fixture(params=[True, False])
def sort(request):
    """Boolean sort keyword for concat and DataFrame.append."""
    return request.param
