import copy

import matplotlib.pyplot as plt
from matplotlib.scale import (
    AsinhScale, AsinhTransform,
    LogTransform, InvertedLogTransform,
    SymmetricalLogTransform)
import matplotlib.scale as mscale
from matplotlib.ticker import AsinhLocator, LogFormatterSciNotation
from matplotlib.testing.decorators import check_figures_equal, image_comparison

import numpy as np
from numpy.testing import assert_allclose
import io
import pytest


@check_figures_equal(extensions=['png'])
def test_log_scales(fig_test, fig_ref):
    ax_test = fig_test.add_subplot(122, yscale='log', xscale='symlog')
    ax_test.axvline(24.1)
    ax_test.axhline(24.1)
    xlim = ax_test.get_xlim()
    ylim = ax_test.get_ylim()
    ax_ref = fig_ref.add_subplot(122, yscale='log', xscale='symlog')
    ax_ref.set(xlim=xlim, ylim=ylim)
    ax_ref.plot([24.1, 24.1], ylim, 'b')
    ax_ref.plot(xlim, [24.1, 24.1], 'b')


def test_symlog_mask_nan():
    # Use a transform round-trip to verify that the forward and inverse
    # transforms work, and that they respect nans and/or masking.
    slt = SymmetricalLogTransform(10, 2, 1)
    slti = slt.inverted()

    x = np.arange(-1.5, 5, 0.5)
    out = slti.transform_non_affine(slt.transform_non_affine(x))
    assert_allclose(out, x)
    assert type(out) is type(x)

    x[4] = np.nan
    out = slti.transform_non_affine(slt.transform_non_affine(x))
    assert_allclose(out, x)
    assert type(out) is type(x)

    x = np.ma.array(x)
    out = slti.transform_non_affine(slt.transform_non_affine(x))
    assert_allclose(out, x)
    assert type(out) is type(x)

    x[3] = np.ma.masked
    out = slti.transform_non_affine(slt.transform_non_affine(x))
    assert_allclose(out, x)
    assert type(out) is type(x)


@image_comparison(['logit_scales.png'], remove_text=True)
def test_logit_scales():
    fig, ax = plt.subplots()

    # Typical extinction curve for logit
    x = np.array([0.001, 0.003, 0.01, 0.03, 0.1, 0.2, 0.3, 0.4, 0.5,
                  0.6, 0.7, 0.8, 0.9, 0.97, 0.99, 0.997, 0.999])
    y = 1.0 / x

    ax.plot(x, y)
    ax.set_xscale('logit')
    ax.grid(True)
    bbox = ax.get_tightbbox(fig.canvas.get_renderer())
    assert np.isfinite(bbox.x0)
    assert np.isfinite(bbox.y0)


def test_log_scatter():
    """Issue #1799"""
    fig, ax = plt.subplots(1)

    x = np.arange(10)
    y = np.arange(10) - 1

    ax.scatter(x, y)

    buf = io.BytesIO()
    fig.savefig(buf, format='pdf')

    buf = io.BytesIO()
    fig.savefig(buf, format='eps')

    buf = io.BytesIO()
    fig.savefig(buf, format='svg')


def test_logscale_subs():
    fig, ax = plt.subplots()
    ax.set_yscale('log', subs=np.array([2, 3, 4]))
    # force draw
    fig.canvas.draw()


@image_comparison(['logscale_mask.png'], remove_text=True)
def test_logscale_mask():
    # Check that zero values are masked correctly on log scales.
    # See github issue 8045
    xs = np.linspace(0, 50, 1001)

    fig, ax = plt.subplots()
    ax.plot(np.exp(-xs**2))
    fig.canvas.draw()
    ax.set(yscale="log")


def test_extra_kwargs_raise():
    fig, ax = plt.subplots()

    for scale in ['linear', 'log', 'symlog']:
        with pytest.raises(TypeError):
            ax.set_yscale(scale, foo='mask')


def test_logscale_invert_transform():
    fig, ax = plt.subplots()
    ax.set_yscale('log')
    # get transformation from data to axes
    tform = (ax.transAxes + ax.transData.inverted()).inverted()

    # direct test of log transform inversion
    inverted_transform = LogTransform(base=2).inverted()
    assert isinstance(inverted_transform, InvertedLogTransform)
    assert inverted_transform.base == 2


def test_logscale_transform_repr():
    fig, ax = plt.subplots()
    ax.set_yscale('log')
    repr(ax.transData)
    repr(LogTransform(10, nonpositive='clip'))


@image_comparison(['logscale_nonpos_values.png'],
                  remove_text=True, tol=0.02, style='mpl20')
def test_logscale_nonpos_values():
    np.random.seed(19680801)
    xs = np.random.normal(size=int(1e3))
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2)
    ax1.hist(xs, range=(-5, 5), bins=10)
    ax1.set_yscale('log')
    ax2.hist(xs, range=(-5, 5), bins=10)
    ax2.set_yscale('log', nonpositive='mask')

    xdata = np.arange(0, 10, 0.01)
    ydata = np.exp(-xdata)
    edata = 0.2*(10-xdata)*np.cos(5*xdata)*np.exp(-xdata)

    ax3.fill_between(xdata, ydata - edata, ydata + edata)
    ax3.set_yscale('log')

    x = np.logspace(-1, 1)
    y = x ** 3
    yerr = x**2
    ax4.errorbar(x, y, yerr=yerr)

    ax4.set_yscale('log')
    ax4.set_xscale('log')


def test_invalid_log_lims():
    # Check that invalid log scale limits are ignored
    fig, ax = plt.subplots()
    ax.scatter(range(0, 4), range(0, 4))

    ax.set_xscale('log')
    original_xlim = ax.get_xlim()
    with pytest.warns(UserWarning):
        ax.set_xlim(left=0)
    assert ax.get_xlim() == original_xlim
    with pytest.warns(UserWarning):
        ax.set_xlim(right=-1)
    assert ax.get_xlim() == original_xlim

    ax.set_yscale('log')
    original_ylim = ax.get_ylim()
    with pytest.warns(UserWarning):
        ax.set_ylim(bottom=0)
    assert ax.get_ylim() == original_ylim
    with pytest.warns(UserWarning):
        ax.set_ylim(top=-1)
    assert ax.get_ylim() == original_ylim


@image_comparison(['function_scales.png'], remove_text=True, style='mpl20')
def test_function_scale():
    def inverse(x):
        return x**2

    def forward(x):
        return x**(1/2)

    fig, ax = plt.subplots()

    x = np.arange(1, 1000)

    ax.plot(x, x)
    ax.set_xscale('function', functions=(forward, inverse))
    ax.set_xlim(1, 1000)


def test_pass_scale():
    # test passing a scale object works...
    fig, ax = plt.subplots()
    scale = mscale.LogScale(axis=None)
    ax.set_xscale(scale)
    scale = mscale.LogScale(axis=None)
    ax.set_yscale(scale)
    assert ax.xaxis.get_scale() == 'log'
    assert ax.yaxis.get_scale() == 'log'


def test_scale_deepcopy():
    sc = mscale.LogScale(axis='x', base=10)
    sc2 = copy.deepcopy(sc)
    assert str(sc.get_transform()) == str(sc2.get_transform())
    assert sc._transform is not sc2._transform


class TestAsinhScale:
    def test_transforms(self):
        a0 = 17.0
        a = np.linspace(-50, 50, 100)

        forward = AsinhTransform(a0)
        inverse = forward.inverted()
        invinv = inverse.inverted()

        a_forward = forward.transform_non_affine(a)
        a_inverted = inverse.transform_non_affine(a_forward)
        assert_allclose(a_inverted, a)

        a_invinv = invinv.transform_non_affine(a)
        assert_allclose(a_invinv, a0 * np.arcsinh(a / a0))

    def test_init(self):
        fig, ax = plt.subplots()

        s = AsinhScale(axis=None, linear_width=23.0)
        assert s.linear_width == 23
        assert s._base == 10
        assert s._subs == (2, 5)

        tx = s.get_transform()
        assert isinstance(tx, AsinhTransform)
        assert tx.linear_width == s.linear_width

    def test_base_init(self):
        fig, ax = plt.subplots()

        s3 = AsinhScale(axis=None, base=3)
        assert s3._base == 3
        assert s3._subs == (2,)

        s7 = AsinhScale(axis=None, base=7, subs=(2, 4))
        assert s7._base == 7
        assert s7._subs == (2, 4)

    def test_fmtloc(self):
        class DummyAxis:
            def __init__(self):
                self.fields = {}
            def set(self, **kwargs):
                self.fields.update(**kwargs)
            def set_major_formatter(self, f):
                self.fields['major_formatter'] = f

        ax0 = DummyAxis()
        s0 = AsinhScale(axis=ax0, base=0)
        s0.set_default_locators_and_formatters(ax0)
        assert isinstance(ax0.fields['major_locator'], AsinhLocator)
        assert isinstance(ax0.fields['major_formatter'], str)

        ax5 = DummyAxis()
        s7 = AsinhScale(axis=ax5, base=5)
        s7.set_default_locators_and_formatters(ax5)
        assert isinstance(ax5.fields['major_locator'], AsinhLocator)
        assert isinstance(ax5.fields['major_formatter'],
                          LogFormatterSciNotation)

    def test_bad_scale(self):
        fig, ax = plt.subplots()

        with pytest.raises(ValueError):
            AsinhScale(axis=None, linear_width=0)
        with pytest.raises(ValueError):
            AsinhScale(axis=None, linear_width=-1)
        s0 = AsinhScale(axis=None, )
        s1 = AsinhScale(axis=None, linear_width=3.0)
