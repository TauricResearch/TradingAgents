from __future__ import annotations

import itertools
import pathlib
import pickle
import sys

from typing import Any
from unittest.mock import patch, Mock

from datetime import datetime, date, timedelta

import numpy as np
from numpy.testing import (assert_array_equal, assert_approx_equal,
                           assert_array_almost_equal)
import pytest

from matplotlib import _api, cbook
import matplotlib.colors as mcolors
from matplotlib.cbook import delete_masked_points, strip_math
from types import ModuleType


class Test_delete_masked_points:
    def test_bad_first_arg(self):
        with pytest.raises(ValueError):
            delete_masked_points('a string', np.arange(1.0, 7.0))

    def test_string_seq(self):
        a1 = ['a', 'b', 'c', 'd', 'e', 'f']
        a2 = [1, 2, 3, np.nan, np.nan, 6]
        result1, result2 = delete_masked_points(a1, a2)
        ind = [0, 1, 2, 5]
        assert_array_equal(result1, np.array(a1)[ind])
        assert_array_equal(result2, np.array(a2)[ind])

    def test_datetime(self):
        dates = [datetime(2008, 1, 1), datetime(2008, 1, 2),
                 datetime(2008, 1, 3), datetime(2008, 1, 4),
                 datetime(2008, 1, 5), datetime(2008, 1, 6)]
        a_masked = np.ma.array([1, 2, 3, np.nan, np.nan, 6],
                               mask=[False, False, True, True, False, False])
        actual = delete_masked_points(dates, a_masked)
        ind = [0, 1, 5]
        assert_array_equal(actual[0], np.array(dates)[ind])
        assert_array_equal(actual[1], a_masked[ind].compressed())

    def test_rgba(self):
        a_masked = np.ma.array([1, 2, 3, np.nan, np.nan, 6],
                               mask=[False, False, True, True, False, False])
        a_rgba = mcolors.to_rgba_array(['r', 'g', 'b', 'c', 'm', 'y'])
        actual = delete_masked_points(a_masked, a_rgba)
        ind = [0, 1, 5]
        assert_array_equal(actual[0], a_masked[ind].compressed())
        assert_array_equal(actual[1], a_rgba[ind])


class Test_boxplot_stats:
    def setup_method(self):
        np.random.seed(937)
        self.nrows = 37
        self.ncols = 4
        self.data = np.random.lognormal(size=(self.nrows, self.ncols),
                                        mean=1.5, sigma=1.75)
        self.known_keys = sorted([
            'mean', 'med', 'q1', 'q3', 'iqr',
            'cilo', 'cihi', 'whislo', 'whishi',
            'fliers', 'label'
        ])
        self.std_results = cbook.boxplot_stats(self.data)

        self.known_nonbootstrapped_res = {
            'cihi': 6.8161283264444847,
            'cilo': -0.1489815330368689,
            'iqr': 13.492709959447094,
            'mean': 13.00447442387868,
            'med': 3.3335733967038079,
            'fliers': np.array([
                92.55467075,  87.03819018,  42.23204914,  39.29390996
            ]),
            'q1': 1.3597529879465153,
            'q3': 14.85246294739361,
            'whishi': 27.899688243699629,
            'whislo': 0.042143774965502923
        }

        self.known_bootstrapped_ci = {
            'cihi': 8.939577523357828,
            'cilo': 1.8692703958676578,
        }

        self.known_whis3_res = {
            'whishi': 42.232049135969874,
            'whislo': 0.042143774965502923,
            'fliers': np.array([92.55467075, 87.03819018]),
        }

        self.known_res_percentiles = {
            'whislo':   0.1933685896907924,
            'whishi':  42.232049135969874
        }

        self.known_res_range = {
            'whislo': 0.042143774965502923,
            'whishi': 92.554670752188699

        }

    def test_form_main_list(self):
        assert isinstance(self.std_results, list)

    def test_form_each_dict(self):
        for res in self.std_results:
            assert isinstance(res, dict)

    def test_form_dict_keys(self):
        for res in self.std_results:
            assert set(res) <= set(self.known_keys)

    def test_results_baseline(self):
        res = self.std_results[0]
        for key, value in self.known_nonbootstrapped_res.items():
            assert_array_almost_equal(res[key], value)

    def test_results_bootstrapped(self):
        results = cbook.boxplot_stats(self.data, bootstrap=10000)
        res = results[0]
        for key, value in self.known_bootstrapped_ci.items():
            assert_approx_equal(res[key], value)

    def test_results_whiskers_float(self):
        results = cbook.boxplot_stats(self.data, whis=3)
        res = results[0]
        for key, value in self.known_whis3_res.items():
            assert_array_almost_equal(res[key], value)

    def test_results_whiskers_range(self):
        results = cbook.boxplot_stats(self.data, whis=[0, 100])
        res = results[0]
        for key, value in self.known_res_range.items():
            assert_array_almost_equal(res[key], value)

    def test_results_whiskers_percentiles(self):
        results = cbook.boxplot_stats(self.data, whis=[5, 95])
        res = results[0]
        for key, value in self.known_res_percentiles.items():
            assert_array_almost_equal(res[key], value)

    def test_results_withlabels(self):
        labels = ['Test1', 2, 'Aardvark', 4]
        results = cbook.boxplot_stats(self.data, labels=labels)
        for lab, res in zip(labels, results):
            assert res['label'] == lab

        results = cbook.boxplot_stats(self.data)
        for res in results:
            assert 'label' not in res

    def test_label_error(self):
        labels = [1, 2]
        with pytest.raises(ValueError):
            cbook.boxplot_stats(self.data, labels=labels)

    def test_bad_dims(self):
        data = np.random.normal(size=(34, 34, 34))
        with pytest.raises(ValueError):
            cbook.boxplot_stats(data)

    def test_boxplot_stats_autorange_false(self):
        x = np.zeros(shape=140)
        x = np.hstack([-25, x, 25])
        bstats_false = cbook.boxplot_stats(x, autorange=False)
        bstats_true = cbook.boxplot_stats(x, autorange=True)

        assert bstats_false[0]['whislo'] == 0
        assert bstats_false[0]['whishi'] == 0
        assert_array_almost_equal(bstats_false[0]['fliers'], [-25, 25])

        assert bstats_true[0]['whislo'] == -25
        assert bstats_true[0]['whishi'] == 25
        assert_array_almost_equal(bstats_true[0]['fliers'], [])


class Hashable:
    def dummy(self): pass


class Unhashable:
    __hash__ = None  # type: ignore[assignment]
    def dummy(self): pass


class Test_callback_registry:
    def setup_method(self):
        self.signal = 'test'
        self.callbacks = cbook.CallbackRegistry()

    def connect(self, s, func, pickle):
        if pickle:
            return self.callbacks.connect(s, func)
        else:
            return self.callbacks._connect_picklable(s, func)

    def disconnect(self, cid):
        return self.callbacks.disconnect(cid)

    def count(self):
        count1 = sum(s == self.signal for s, p in self.callbacks._func_cid_map)
        count2 = len(self.callbacks.callbacks.get(self.signal))
        assert count1 == count2
        return count1

    def is_empty(self):
        np.testing.break_cycles()
        assert [*self.callbacks._func_cid_map] == []
        assert self.callbacks.callbacks == {}
        assert self.callbacks._pickled_cids == set()

    def is_not_empty(self):
        np.testing.break_cycles()
        assert [*self.callbacks._func_cid_map] != []
        assert self.callbacks.callbacks != {}

    def test_cid_restore(self):
        cb = cbook.CallbackRegistry()
        cb.connect('a', lambda: None)
        cb2 = pickle.loads(pickle.dumps(cb))
        cid = cb2.connect('c', lambda: None)
        assert cid == 1

    @pytest.mark.parametrize('pickle', [True, False])
    @pytest.mark.parametrize('cls', [Hashable, Unhashable])
    def test_callback_complete(self, pickle, cls):
        # ensure we start with an empty registry
        self.is_empty()

        # create a class for testing
        mini_me = cls()

        # test that we can add a callback
        cid1 = self.connect(self.signal, mini_me.dummy, pickle)
        assert type(cid1) is int
        self.is_not_empty()

        # test that we don't add a second callback
        cid2 = self.connect(self.signal, mini_me.dummy, pickle)
        assert cid1 == cid2
        self.is_not_empty()
        assert len([*self.callbacks._func_cid_map]) == 1
        assert len(self.callbacks.callbacks) == 1

        del mini_me

        # check we now have no callbacks registered
        self.is_empty()

    @pytest.mark.parametrize('pickle', [True, False])
    @pytest.mark.parametrize('cls', [Hashable, Unhashable])
    def test_callback_disconnect(self, pickle, cls):
        # ensure we start with an empty registry
        self.is_empty()

        # create a class for testing
        mini_me = cls()

        # test that we can add a callback
        cid1 = self.connect(self.signal, mini_me.dummy, pickle)
        assert type(cid1) is int
        self.is_not_empty()

        self.disconnect(cid1)

        # check we now have no callbacks registered
        self.is_empty()

    @pytest.mark.parametrize('pickle', [True, False])
    @pytest.mark.parametrize('cls', [Hashable, Unhashable])
    def test_callback_wrong_disconnect(self, pickle, cls):
        # ensure we start with an empty registry
        self.is_empty()

        # create a class for testing
        mini_me = cls()

        # test that we can add a callback
        cid1 = self.connect(self.signal, mini_me.dummy, pickle)
        assert type(cid1) is int
        self.is_not_empty()

        self.disconnect("foo")

        # check we still have callbacks registered
        self.is_not_empty()

    @pytest.mark.parametrize('pickle', [True, False])
    @pytest.mark.parametrize('cls', [Hashable, Unhashable])
    def test_registration_on_non_empty_registry(self, pickle, cls):
        # ensure we start with an empty registry
        self.is_empty()

        # setup the registry with a callback
        mini_me = cls()
        self.connect(self.signal, mini_me.dummy, pickle)

        # Add another callback
        mini_me2 = cls()
        self.connect(self.signal, mini_me2.dummy, pickle)

        # Remove and add the second callback
        mini_me2 = cls()
        self.connect(self.signal, mini_me2.dummy, pickle)

        # We still have 2 references
        self.is_not_empty()
        assert self.count() == 2

        # Removing the last 2 references
        mini_me = None
        mini_me2 = None
        self.is_empty()

    def test_pickling(self):
        assert hasattr(pickle.loads(pickle.dumps(cbook.CallbackRegistry())),
                       "callbacks")


def test_callbackregistry_default_exception_handler(capsys, monkeypatch):
    cb = cbook.CallbackRegistry()
    cb.connect("foo", lambda: None)

    monkeypatch.setattr(
        cbook, "_get_running_interactive_framework", lambda: None)
    with pytest.raises(TypeError):
        cb.process("foo", "argument mismatch")
    outerr = capsys.readouterr()
    assert outerr.out == outerr.err == ""

    monkeypatch.setattr(
        cbook, "_get_running_interactive_framework", lambda: "not-none")
    cb.process("foo", "argument mismatch")  # No error in that case.
    outerr = capsys.readouterr()
    assert outerr.out == ""
    assert "takes 0 positional arguments but 1 was given" in outerr.err


def raising_cb_reg(func):
    class TestException(Exception):
        pass

    def raise_runtime_error():
        raise RuntimeError

    def raise_value_error():
        raise ValueError

    def transformer(excp):
        if isinstance(excp, RuntimeError):
            raise TestException
        raise excp

    # old default
    cb_old = cbook.CallbackRegistry(exception_handler=None)
    cb_old.connect('foo', raise_runtime_error)

    # filter
    cb_filt = cbook.CallbackRegistry(exception_handler=transformer)
    cb_filt.connect('foo', raise_runtime_error)

    # filter
    cb_filt_pass = cbook.CallbackRegistry(exception_handler=transformer)
    cb_filt_pass.connect('foo', raise_value_error)

    return pytest.mark.parametrize('cb, excp',
                                   [[cb_old, RuntimeError],
                                    [cb_filt, TestException],
                                    [cb_filt_pass, ValueError]])(func)


@raising_cb_reg
def test_callbackregistry_custom_exception_handler(monkeypatch, cb, excp):
    monkeypatch.setattr(
        cbook, "_get_running_interactive_framework", lambda: None)
    with pytest.raises(excp):
        cb.process('foo')


def test_callbackregistry_signals():
    cr = cbook.CallbackRegistry(signals=["foo"])
    results = []
    def cb(x): results.append(x)
    cr.connect("foo", cb)
    with pytest.raises(ValueError):
        cr.connect("bar", cb)
    cr.process("foo", 1)
    with pytest.raises(ValueError):
        cr.process("bar", 1)
    assert results == [1]


def test_callbackregistry_blocking():
    # Needs an exception handler for interactive testing environments
    # that would only print this out instead of raising the exception
    def raise_handler(excp):
        raise excp
    cb = cbook.CallbackRegistry(exception_handler=raise_handler)
    def test_func1():
        raise ValueError("1 should be blocked")
    def test_func2():
        raise ValueError("2 should be blocked")
    cb.connect("test1", test_func1)
    cb.connect("test2", test_func2)

    # block all of the callbacks to make sure they aren't processed
    with cb.blocked():
        cb.process("test1")
        cb.process("test2")

    # block individual callbacks to make sure the other is still processed
    with cb.blocked(signal="test1"):
        # Blocked
        cb.process("test1")
        # Should raise
        with pytest.raises(ValueError, match="2 should be blocked"):
            cb.process("test2")

    # Make sure the original callback functions are there after blocking
    with pytest.raises(ValueError, match="1 should be blocked"):
        cb.process("test1")
    with pytest.raises(ValueError, match="2 should be blocked"):
        cb.process("test2")


@pytest.mark.parametrize('line, result', [
    ('a : no_comment', 'a : no_comment'),
    ('a : "quoted str"', 'a : "quoted str"'),
    ('a : "quoted str" # comment', 'a : "quoted str"'),
    ('a : "#000000"', 'a : "#000000"'),
    ('a : "#000000" # comment', 'a : "#000000"'),
    ('a : ["#000000", "#FFFFFF"]', 'a : ["#000000", "#FFFFFF"]'),
    ('a : ["#000000", "#FFFFFF"] # comment', 'a : ["#000000", "#FFFFFF"]'),
    ('a : val  # a comment "with quotes"', 'a : val'),
    ('# only comment "with quotes" xx', ''),
])
def test_strip_comment(line, result):
    """Strip everything from the first unquoted #."""
    assert cbook._strip_comment(line) == result


def test_strip_comment_invalid():
    with pytest.raises(ValueError, match="Missing closing quote"):
        cbook._strip_comment('grid.color: "aa')


def test_sanitize_sequence():
    d = {'a': 1, 'b': 2, 'c': 3}
    k = ['a', 'b', 'c']
    v = [1, 2, 3]
    i = [('a', 1), ('b', 2), ('c', 3)]
    assert k == sorted(cbook.sanitize_sequence(d.keys()))
    assert v == sorted(cbook.sanitize_sequence(d.values()))
    assert i == sorted(cbook.sanitize_sequence(d.items()))
    assert i == cbook.sanitize_sequence(i)
    assert k == cbook.sanitize_sequence(k)


fail_mapping: tuple[tuple[dict, dict], ...] = (
    ({'a': 1, 'b': 2}, {'alias_mapping': {'a': ['b']}}),
    ({'a': 1, 'b': 2}, {'alias_mapping': {'a': ['a', 'b']}}),
)

pass_mapping: tuple[tuple[Any, dict, dict], ...] = (
    (None, {}, {}),
    ({'a': 1, 'b': 2}, {'a': 1, 'b': 2}, {}),
    ({'b': 2}, {'a': 2}, {'alias_mapping': {'a': ['a', 'b']}}),
)


@pytest.mark.parametrize('inp, kwargs_to_norm', fail_mapping)
def test_normalize_kwargs_fail(inp, kwargs_to_norm):
    with pytest.raises(TypeError), _api.suppress_matplotlib_deprecation_warning():
        cbook.normalize_kwargs(inp, **kwargs_to_norm)


@pytest.mark.parametrize('inp, expected, kwargs_to_norm',
                         pass_mapping)
def test_normalize_kwargs_pass(inp, expected, kwargs_to_norm):
    with _api.suppress_matplotlib_deprecation_warning():
        # No other warning should be emitted.
        assert expected == cbook.normalize_kwargs(inp, **kwargs_to_norm)


def test_warn_external(recwarn):
    _api.warn_external("oops")
    assert len(recwarn) == 1
    if sys.version_info[:2] >= (3, 12):
        # With Python 3.12, we let Python figure out the stacklevel using the
        # `skip_file_prefixes` argument, which cannot exempt tests, so just confirm
        # the filename is not in the package.
        basedir = pathlib.Path(__file__).parents[2]
        assert not recwarn[0].filename.startswith((str(basedir / 'matplotlib'),
                                                   str(basedir / 'mpl_toolkits')))
    else:
        # On older Python versions, we manually calculated the stacklevel, and had an
        # exception for our own tests.
        assert recwarn[0].filename == __file__


def test_warn_external_frame_embedded_python():
    with patch.object(cbook, "sys") as mock_sys:
        mock_sys._getframe = Mock(return_value=None)
        with pytest.warns(UserWarning, match=r"\Adummy\Z"):
            _api.warn_external("dummy")


def test_to_prestep():
    x = np.arange(4)
    y1 = np.arange(4)
    y2 = np.arange(4)[::-1]

    xs, y1s, y2s = cbook.pts_to_prestep(x, y1, y2)

    x_target = np.asarray([0, 0, 1, 1, 2, 2, 3], dtype=float)
    y1_target = np.asarray([0, 1, 1, 2, 2, 3, 3], dtype=float)
    y2_target = np.asarray([3, 2, 2, 1, 1, 0, 0], dtype=float)

    assert_array_equal(x_target, xs)
    assert_array_equal(y1_target, y1s)
    assert_array_equal(y2_target, y2s)

    xs, y1s = cbook.pts_to_prestep(x, y1)
    assert_array_equal(x_target, xs)
    assert_array_equal(y1_target, y1s)


def test_to_prestep_empty():
    steps = cbook.pts_to_prestep([], [])
    assert steps.shape == (2, 0)


def test_to_poststep():
    x = np.arange(4)
    y1 = np.arange(4)
    y2 = np.arange(4)[::-1]

    xs, y1s, y2s = cbook.pts_to_poststep(x, y1, y2)

    x_target = np.asarray([0, 1, 1, 2, 2, 3, 3], dtype=float)
    y1_target = np.asarray([0, 0, 1, 1, 2, 2, 3], dtype=float)
    y2_target = np.asarray([3, 3, 2, 2, 1, 1, 0], dtype=float)

    assert_array_equal(x_target, xs)
    assert_array_equal(y1_target, y1s)
    assert_array_equal(y2_target, y2s)

    xs, y1s = cbook.pts_to_poststep(x, y1)
    assert_array_equal(x_target, xs)
    assert_array_equal(y1_target, y1s)


def test_to_poststep_empty():
    steps = cbook.pts_to_poststep([], [])
    assert steps.shape == (2, 0)


def test_to_midstep():
    x = np.arange(4)
    y1 = np.arange(4)
    y2 = np.arange(4)[::-1]

    xs, y1s, y2s = cbook.pts_to_midstep(x, y1, y2)

    x_target = np.asarray([0, .5, .5, 1.5, 1.5, 2.5, 2.5, 3], dtype=float)
    y1_target = np.asarray([0, 0, 1, 1, 2, 2, 3, 3], dtype=float)
    y2_target = np.asarray([3, 3, 2, 2, 1, 1, 0, 0], dtype=float)

    assert_array_equal(x_target, xs)
    assert_array_equal(y1_target, y1s)
    assert_array_equal(y2_target, y2s)

    xs, y1s = cbook.pts_to_midstep(x, y1)
    assert_array_equal(x_target, xs)
    assert_array_equal(y1_target, y1s)


def test_to_midstep_empty():
    steps = cbook.pts_to_midstep([], [])
    assert steps.shape == (2, 0)


@pytest.mark.parametrize(
    "args",
    [(np.arange(12).reshape(3, 4), 'a'),
     (np.arange(12), 'a'),
     (np.arange(12), np.arange(3))])
def test_step_fails(args):
    with pytest.raises(ValueError):
        cbook.pts_to_prestep(*args)


def test_grouper():
    class Dummy:
        pass
    a, b, c, d, e = objs = [Dummy() for _ in range(5)]
    g = cbook.Grouper()
    g.join(*objs)
    assert set(list(g)[0]) == set(objs)
    assert set(g.get_siblings(a)) == set(objs)

    for other in objs[1:]:
        assert g.joined(a, other)

    g.remove(a)
    for other in objs[1:]:
        assert not g.joined(a, other)

    for A, B in itertools.product(objs[1:], objs[1:]):
        assert g.joined(A, B)


def test_grouper_private():
    class Dummy:
        pass
    objs = [Dummy() for _ in range(5)]
    g = cbook.Grouper()
    g.join(*objs)
    # reach in and touch the internals !
    mapping = g._mapping

    for o in objs:
        assert o in mapping

    base_set = mapping[objs[0]]
    for o in objs[1:]:
        assert mapping[o] is base_set


def test_flatiter():
    x = np.arange(5)
    it = x.flat
    assert 0 == next(it)
    assert 1 == next(it)
    ret = cbook._safe_first_finite(it)
    assert ret == 0

    assert 0 == next(it)
    assert 1 == next(it)


def test__safe_first_finite_all_nan():
    arr = np.full(2, np.nan)
    ret = cbook._safe_first_finite(arr)
    assert np.isnan(ret)


def test__safe_first_finite_all_inf():
    arr = np.full(2, np.inf)
    ret = cbook._safe_first_finite(arr)
    assert np.isinf(ret)


def test_reshape2d():

    class Dummy:
        pass

    xnew = cbook._reshape_2D([], 'x')
    assert np.shape(xnew) == (1, 0)

    x = [Dummy() for _ in range(5)]

    xnew = cbook._reshape_2D(x, 'x')
    assert np.shape(xnew) == (1, 5)

    x = np.arange(5)
    xnew = cbook._reshape_2D(x, 'x')
    assert np.shape(xnew) == (1, 5)

    x = [[Dummy() for _ in range(5)] for _ in range(3)]
    xnew = cbook._reshape_2D(x, 'x')
    assert np.shape(xnew) == (3, 5)

    # this is strange behaviour, but...
    x = np.random.rand(3, 5)
    xnew = cbook._reshape_2D(x, 'x')
    assert np.shape(xnew) == (5, 3)

    # Test a list of lists which are all of length 1
    x = [[1], [2], [3]]
    xnew = cbook._reshape_2D(x, 'x')
    assert isinstance(xnew, list)
    assert isinstance(xnew[0], np.ndarray) and xnew[0].shape == (1,)
    assert isinstance(xnew[1], np.ndarray) and xnew[1].shape == (1,)
    assert isinstance(xnew[2], np.ndarray) and xnew[2].shape == (1,)

    # Test a list of zero-dimensional arrays
    x = [np.array(0), np.array(1), np.array(2)]
    xnew = cbook._reshape_2D(x, 'x')
    assert isinstance(xnew, list)
    assert len(xnew) == 1
    assert isinstance(xnew[0], np.ndarray) and xnew[0].shape == (3,)

    # Now test with a list of lists with different lengths, which means the
    # array will internally be converted to a 1D object array of lists
    x = [[1, 2, 3], [3, 4], [2]]
    xnew = cbook._reshape_2D(x, 'x')
    assert isinstance(xnew, list)
    assert isinstance(xnew[0], np.ndarray) and xnew[0].shape == (3,)
    assert isinstance(xnew[1], np.ndarray) and xnew[1].shape == (2,)
    assert isinstance(xnew[2], np.ndarray) and xnew[2].shape == (1,)

    # We now need to make sure that this works correctly for Numpy subclasses
    # where iterating over items can return subclasses too, which may be
    # iterable even if they are scalars. To emulate this, we make a Numpy
    # array subclass that returns Numpy 'scalars' when iterating or accessing
    # values, and these are technically iterable if checking for example
    # isinstance(x, collections.abc.Iterable).

    class ArraySubclass(np.ndarray):

        def __iter__(self):
            for value in super().__iter__():
                yield np.array(value)

        def __getitem__(self, item):
            return np.array(super().__getitem__(item))

    v = np.arange(10, dtype=float)
    x = ArraySubclass((10,), dtype=float, buffer=v.data)

    xnew = cbook._reshape_2D(x, 'x')

    # We check here that the array wasn't split up into many individual
    # ArraySubclass, which is what used to happen due to a bug in _reshape_2D
    assert len(xnew) == 1
    assert isinstance(xnew[0], ArraySubclass)

    # check list of strings:
    x = ['a', 'b', 'c', 'c', 'dd', 'e', 'f', 'ff', 'f']
    xnew = cbook._reshape_2D(x, 'x')
    assert len(xnew[0]) == len(x)
    assert isinstance(xnew[0], np.ndarray)


def test_reshape2d_pandas(pd):
    # separate to allow the rest of the tests to run if no pandas...
    X = np.arange(30).reshape(10, 3)
    x = pd.DataFrame(X, columns=["a", "b", "c"])
    Xnew = cbook._reshape_2D(x, 'x')
    # Need to check each row because _reshape_2D returns a list of arrays:
    for x, xnew in zip(X.T, Xnew):
        np.testing.assert_array_equal(x, xnew)


def test_reshape2d_xarray(xr):
    # separate to allow the rest of the tests to run if no xarray...
    X = np.arange(30).reshape(10, 3)
    x = xr.DataArray(X, dims=["x", "y"])
    Xnew = cbook._reshape_2D(x, 'x')
    # Need to check each row because _reshape_2D returns a list of arrays:
    for x, xnew in zip(X.T, Xnew):
        np.testing.assert_array_equal(x, xnew)


def test_index_of_pandas(pd):
    # separate to allow the rest of the tests to run if no pandas...
    X = np.arange(30).reshape(10, 3)
    x = pd.DataFrame(X, columns=["a", "b", "c"])
    Idx, Xnew = cbook.index_of(x)
    np.testing.assert_array_equal(X, Xnew)
    IdxRef = np.arange(10)
    np.testing.assert_array_equal(Idx, IdxRef)


def test_index_of_xarray(xr):
    # separate to allow the rest of the tests to run if no xarray...
    X = np.arange(30).reshape(10, 3)
    x = xr.DataArray(X, dims=["x", "y"])
    Idx, Xnew = cbook.index_of(x)
    np.testing.assert_array_equal(X, Xnew)
    IdxRef = np.arange(10)
    np.testing.assert_array_equal(Idx, IdxRef)


def test_contiguous_regions():
    a, b, c = 3, 4, 5
    # Starts and ends with True
    mask = [True]*a + [False]*b + [True]*c
    expected = [(0, a), (a+b, a+b+c)]
    assert cbook.contiguous_regions(mask) == expected
    d, e = 6, 7
    # Starts with True ends with False
    mask = mask + [False]*e
    assert cbook.contiguous_regions(mask) == expected
    # Starts with False ends with True
    mask = [False]*d + mask[:-e]
    expected = [(d, d+a), (d+a+b, d+a+b+c)]
    assert cbook.contiguous_regions(mask) == expected
    # Starts and ends with False
    mask = mask + [False]*e
    assert cbook.contiguous_regions(mask) == expected
    # No True in mask
    assert cbook.contiguous_regions([False]*5) == []
    # Empty mask
    assert cbook.contiguous_regions([]) == []


def test_safe_first_element_pandas_series(pd):
    # deliberately create a pandas series with index not starting from 0
    s = pd.Series(range(5), index=range(10, 15))
    actual = cbook._safe_first_finite(s)
    assert actual == 0


def test_array_patch_perimeters():
    # This compares the old implementation as a reference for the
    # vectorized one.
    def check(x, rstride, cstride):
        rows, cols = x.shape
        row_inds = [*range(0, rows-1, rstride), rows-1]
        col_inds = [*range(0, cols-1, cstride), cols-1]
        polys = []
        for rs, rs_next in itertools.pairwise(row_inds):
            for cs, cs_next in itertools.pairwise(col_inds):
                # +1 ensures we share edges between polygons
                ps = cbook._array_perimeter(x[rs:rs_next+1, cs:cs_next+1]).T
                polys.append(ps)
        polys = np.asarray(polys)
        assert np.array_equal(polys,
                              cbook._array_patch_perimeters(
                                  x, rstride=rstride, cstride=cstride))

    def divisors(n):
        return [i for i in range(1, n + 1) if n % i == 0]

    for rows, cols in [(5, 5), (7, 14), (13, 9)]:
        x = np.arange(rows * cols).reshape(rows, cols)
        for rstride, cstride in itertools.product(divisors(rows - 1),
                                                  divisors(cols - 1)):
            check(x, rstride=rstride, cstride=cstride)


def test_setattr_cm():
    class A:
        cls_level = object()
        override = object()

        def __init__(self):
            self.aardvark = 'aardvark'
            self.override = 'override'
            self._p = 'p'

        def meth(self):
            ...

        @classmethod
        def classy(cls):
            ...

        @staticmethod
        def static():
            ...

        @property
        def prop(self):
            return self._p

        @prop.setter
        def prop(self, val):
            self._p = val

    class B(A):
        ...

    other = A()

    def verify_pre_post_state(obj):
        # When you access a Python method the function is bound
        # to the object at access time so you get a new instance
        # of MethodType every time.
        #
        # https://docs.python.org/3/howto/descriptor.html#functions-and-methods
        assert obj.meth is not obj.meth
        # normal attribute should give you back the same instance every time
        assert obj.aardvark is obj.aardvark
        assert a.aardvark == 'aardvark'
        # and our property happens to give the same instance every time
        assert obj.prop is obj.prop
        assert obj.cls_level is A.cls_level
        assert obj.override == 'override'
        assert not hasattr(obj, 'extra')
        assert obj.prop == 'p'
        assert obj.monkey == other.meth
        assert obj.cls_level is A.cls_level
        assert 'cls_level' not in obj.__dict__
        assert 'classy' not in obj.__dict__
        assert 'static' not in obj.__dict__

    a = B()

    a.monkey = other.meth
    verify_pre_post_state(a)
    with cbook._setattr_cm(
            a, prop='squirrel',
            aardvark='moose', meth=lambda: None,
            override='boo', extra='extra',
            monkey=lambda: None, cls_level='bob',
            classy='classy', static='static'):
        # because we have set a lambda, it is normal attribute access
        # and the same every time
        assert a.meth is a.meth
        assert a.aardvark is a.aardvark
        assert a.aardvark == 'moose'
        assert a.override == 'boo'
        assert a.extra == 'extra'
        assert a.prop == 'squirrel'
        assert a.monkey != other.meth
        assert a.cls_level == 'bob'
        assert a.classy == 'classy'
        assert a.static == 'static'

    verify_pre_post_state(a)


def test_format_approx():
    f = cbook._format_approx
    assert f(0, 1) == '0'
    assert f(0, 2) == '0'
    assert f(0, 3) == '0'
    assert f(-0.0123, 1) == '-0'
    assert f(1e-7, 5) == '0'
    assert f(0.0012345600001, 5) == '0.00123'
    assert f(-0.0012345600001, 5) == '-0.00123'
    assert f(0.0012345600001, 8) == f(0.0012345600001, 10) == '0.00123456'


def test_safe_first_element_with_none():
    datetime_lst = [date.today() + timedelta(days=i) for i in range(10)]
    datetime_lst[0] = None
    actual = cbook._safe_first_finite(datetime_lst)
    assert actual is not None and actual == datetime_lst[1]


def test_strip_math():
    assert strip_math(r'1 \times 2') == r'1 \times 2'
    assert strip_math(r'$1 \times 2$') == '1 x 2'
    assert strip_math(r'$\rm{hi}$') == 'hi'


@pytest.mark.parametrize('fmt, value, result', [
    ('%.2f m', 0.2, '0.20 m'),
    ('{:.2f} m', 0.2, '0.20 m'),
    ('{} m', 0.2, '0.2 m'),
    ('const', 0.2, 'const'),
    ('%d or {}', 0.2, '0 or {}'),
    ('{{{:,.0f}}}', 2e5, '{200,000}'),
    ('{:.2%}', 2/3, '66.67%'),
    ('$%g', 2.54, '$2.54'),
])
def test_auto_format_str(fmt, value, result):
    """Apply *value* to the format string *fmt*."""
    assert cbook._auto_format_str(fmt, value) == result
    assert cbook._auto_format_str(fmt, np.float64(value)) == result


def test_unpack_to_numpy_from_torch():
    """
    Test that torch tensors are converted to NumPy arrays.

    We don't want to create a dependency on torch in the test suite, so we mock it.
    """
    class Tensor:
        def __init__(self, data):
            self.data = data

        def __array__(self):
            return self.data

    torch = ModuleType('torch')
    torch.Tensor = Tensor
    sys.modules['torch'] = torch

    data = np.arange(10)
    torch_tensor = torch.Tensor(data)

    result = cbook._unpack_to_numpy(torch_tensor)
    assert isinstance(result, np.ndarray)
    # compare results, do not check for identity: the latter would fail
    # if not mocked, and the implementation does not guarantee it
    # is the same Python object, just the same values.
    assert_array_equal(result, data)


def test_unpack_to_numpy_from_jax():
    """
    Test that jax arrays are converted to NumPy arrays.

    We don't want to create a dependency on jax in the test suite, so we mock it.
    """
    class Array:
        def __init__(self, data):
            self.data = data

        def __array__(self):
            return self.data

    jax = ModuleType('jax')
    jax.Array = Array

    sys.modules['jax'] = jax

    data = np.arange(10)
    jax_array = jax.Array(data)

    result = cbook._unpack_to_numpy(jax_array)
    assert isinstance(result, np.ndarray)
    # compare results, do not check for identity: the latter would fail
    # if not mocked, and the implementation does not guarantee it
    # is the same Python object, just the same values.
    assert_array_equal(result, data)


def test_unpack_to_numpy_from_tensorflow():
    """
    Test that tensorflow arrays are converted to NumPy arrays.

    We don't want to create a dependency on tensorflow in the test suite, so we mock it.
    """
    class Tensor:
        def __init__(self, data):
            self.data = data

        def __array__(self):
            return self.data

    tensorflow = ModuleType('tensorflow')
    tensorflow.is_tensor = lambda x: isinstance(x, Tensor)
    tensorflow.Tensor = Tensor

    sys.modules['tensorflow'] = tensorflow

    data = np.arange(10)
    tf_tensor = tensorflow.Tensor(data)

    result = cbook._unpack_to_numpy(tf_tensor)
    assert isinstance(result, np.ndarray)
    # compare results, do not check for identity: the latter would fail
    # if not mocked, and the implementation does not guarantee it
    # is the same Python object, just the same values.
    assert_array_equal(result, data)
