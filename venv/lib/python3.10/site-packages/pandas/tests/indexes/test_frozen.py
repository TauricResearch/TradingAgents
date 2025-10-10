import re

import pytest

from pandas.core.indexes.frozen import FrozenList


@pytest.fixture
def lst():
    return [1, 2, 3, 4, 5]


@pytest.fixture
def container(lst):
    return FrozenList(lst)


@pytest.fixture
def unicode_container():
    return FrozenList(["\u05d0", "\u05d1", "c"])


class TestFrozenList:
    def check_mutable_error(self, *args, **kwargs):
        # Pass whatever function you normally would to pytest.raises
        # (after the Exception kind).
        mutable_regex = re.compile("does not support mutable operations")
        msg = "'(_s)?re.(SRE_)?Pattern' object is not callable"
        with pytest.raises(TypeError, match=msg):
            mutable_regex(*args, **kwargs)

    def test_no_mutable_funcs(self, container):
        def setitem():
            container[0] = 5

        self.check_mutable_error(setitem)

        def setslice():
            container[1:2] = 3

        self.check_mutable_error(setslice)

        def delitem():
            del container[0]

        self.check_mutable_error(delitem)

        def delslice():
            del container[0:3]

        self.check_mutable_error(delslice)

        mutable_methods = ("extend", "pop", "remove", "insert")

        for meth in mutable_methods:
            self.check_mutable_error(getattr(container, meth))

    def test_slicing_maintains_type(self, container, lst):
        result = container[1:2]
        expected = lst[1:2]
        self.check_result(result, expected)

    def check_result(self, result, expected):
        assert isinstance(result, FrozenList)
        assert result == expected

    def test_string_methods_dont_fail(self, container):
        repr(container)
        str(container)
        bytes(container)

    def test_tricky_container(self, unicode_container):
        repr(unicode_container)
        str(unicode_container)

    def test_add(self, container, lst):
        result = container + (1, 2, 3)
        expected = FrozenList(lst + [1, 2, 3])
        self.check_result(result, expected)

        result = (1, 2, 3) + container
        expected = FrozenList([1, 2, 3] + lst)
        self.check_result(result, expected)

    def test_iadd(self, container, lst):
        q = r = container

        q += [5]
        self.check_result(q, lst + [5])

        # Other shouldn't be mutated.
        self.check_result(r, lst)

    def test_union(self, container, lst):
        result = container.union((1, 2, 3))
        expected = FrozenList(lst + [1, 2, 3])
        self.check_result(result, expected)

    def test_difference(self, container):
        result = container.difference([2])
        expected = FrozenList([1, 3, 4, 5])
        self.check_result(result, expected)

    def test_difference_dupe(self):
        result = FrozenList([1, 2, 3, 2]).difference([2])
        expected = FrozenList([1, 3])
        self.check_result(result, expected)

    def test_tricky_container_to_bytes_raises(self, unicode_container):
        # GH 26447
        msg = "^'str' object cannot be interpreted as an integer$"
        with pytest.raises(TypeError, match=msg):
            bytes(unicode_container)
