import pytest


@pytest.fixture(params=["split", "records", "index", "columns", "values"])
def orient(request):
    """
    Fixture for orients excluding the table format.
    """
    return request.param
