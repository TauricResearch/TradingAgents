import datetime

import dateutil.tz
import dateutil.rrule
import functools
import numpy as np
import pytest

from matplotlib import rc_context, style
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.testing.decorators import image_comparison
import matplotlib.ticker as mticker


def test_date_numpyx():
    # test that numpy dates work properly...
    base = datetime.datetime(2017, 1, 1)
    time = [base + datetime.timedelta(days=x) for x in range(0, 3)]
    timenp = np.array(time, dtype='datetime64[ns]')
    data = np.array([0., 2., 1.])
    fig = plt.figure(figsize=(10, 2))
    ax = fig.add_subplot(1, 1, 1)
    h, = ax.plot(time, data)
    hnp, = ax.plot(timenp, data)
    np.testing.assert_equal(h.get_xdata(orig=False), hnp.get_xdata(orig=False))
    fig = plt.figure(figsize=(10, 2))
    ax = fig.add_subplot(1, 1, 1)
    h, = ax.plot(data, time)
    hnp, = ax.plot(data, timenp)
    np.testing.assert_equal(h.get_ydata(orig=False), hnp.get_ydata(orig=False))


@pytest.mark.parametrize('t0', [datetime.datetime(2017, 1, 1, 0, 1, 1),

                                [datetime.datetime(2017, 1, 1, 0, 1, 1),
                                 datetime.datetime(2017, 1, 1, 1, 1, 1)],

                                [[datetime.datetime(2017, 1, 1, 0, 1, 1),
                                  datetime.datetime(2017, 1, 1, 1, 1, 1)],
                                 [datetime.datetime(2017, 1, 1, 2, 1, 1),
                                  datetime.datetime(2017, 1, 1, 3, 1, 1)]]])
@pytest.mark.parametrize('dtype', ['datetime64[s]',
                                   'datetime64[us]',
                                   'datetime64[ms]',
                                   'datetime64[ns]'])
def test_date_date2num_numpy(t0, dtype):
    time = mdates.date2num(t0)
    tnp = np.array(t0, dtype=dtype)
    nptime = mdates.date2num(tnp)
    np.testing.assert_equal(time, nptime)


@pytest.mark.parametrize('dtype', ['datetime64[s]',
                                   'datetime64[us]',
                                   'datetime64[ms]',
                                   'datetime64[ns]'])
def test_date2num_NaT(dtype):
    t0 = datetime.datetime(2017, 1, 1, 0, 1, 1)
    tmpl = [mdates.date2num(t0), np.nan]
    tnp = np.array([t0, 'NaT'], dtype=dtype)
    nptime = mdates.date2num(tnp)
    np.testing.assert_array_equal(tmpl, nptime)


@pytest.mark.parametrize('units', ['s', 'ms', 'us', 'ns'])
def test_date2num_NaT_scalar(units):
    tmpl = mdates.date2num(np.datetime64('NaT', units))
    assert np.isnan(tmpl)


def test_date2num_masked():
    # Without tzinfo
    base = datetime.datetime(2022, 12, 15)
    dates = np.ma.array([base + datetime.timedelta(days=(2 * i))
                         for i in range(7)], mask=[0, 1, 1, 0, 0, 0, 1])
    npdates = mdates.date2num(dates)
    np.testing.assert_array_equal(np.ma.getmask(npdates),
                                  (False, True, True, False, False, False,
                                   True))

    # With tzinfo
    base = datetime.datetime(2022, 12, 15, tzinfo=mdates.UTC)
    dates = np.ma.array([base + datetime.timedelta(days=(2 * i))
                         for i in range(7)], mask=[0, 1, 1, 0, 0, 0, 1])
    npdates = mdates.date2num(dates)
    np.testing.assert_array_equal(np.ma.getmask(npdates),
                                  (False, True, True, False, False, False,
                                   True))


def test_date_empty():
    # make sure we do the right thing when told to plot dates even
    # if no date data has been presented, cf
    # http://sourceforge.net/tracker/?func=detail&aid=2850075&group_id=80706&atid=560720
    fig, ax = plt.subplots()
    ax.xaxis_date()
    fig.draw_without_rendering()
    np.testing.assert_allclose(ax.get_xlim(),
                               [mdates.date2num(np.datetime64('1970-01-01')),
                                mdates.date2num(np.datetime64('1970-01-02'))])

    mdates._reset_epoch_test_example()
    mdates.set_epoch('0000-12-31')
    fig, ax = plt.subplots()
    ax.xaxis_date()
    fig.draw_without_rendering()
    np.testing.assert_allclose(ax.get_xlim(),
                               [mdates.date2num(np.datetime64('1970-01-01')),
                                mdates.date2num(np.datetime64('1970-01-02'))])
    mdates._reset_epoch_test_example()


def test_date_not_empty():
    fig = plt.figure()
    ax = fig.add_subplot()

    ax.plot([50, 70], [1, 2])
    ax.xaxis.axis_date()
    np.testing.assert_allclose(ax.get_xlim(), [50, 70])


def test_axhline():
    # make sure that axhline doesn't set the xlimits...
    fig, ax = plt.subplots()
    ax.axhline(1.5)
    ax.plot([np.datetime64('2016-01-01'), np.datetime64('2016-01-02')], [1, 2])
    np.testing.assert_allclose(ax.get_xlim(),
                               [mdates.date2num(np.datetime64('2016-01-01')),
                                mdates.date2num(np.datetime64('2016-01-02'))])

    mdates._reset_epoch_test_example()
    mdates.set_epoch('0000-12-31')
    fig, ax = plt.subplots()
    ax.axhline(1.5)
    ax.plot([np.datetime64('2016-01-01'), np.datetime64('2016-01-02')], [1, 2])
    np.testing.assert_allclose(ax.get_xlim(),
                               [mdates.date2num(np.datetime64('2016-01-01')),
                                mdates.date2num(np.datetime64('2016-01-02'))])
    mdates._reset_epoch_test_example()


@image_comparison(['date_axhspan.png'])
def test_date_axhspan():
    # test axhspan with date inputs
    t0 = datetime.datetime(2009, 1, 20)
    tf = datetime.datetime(2009, 1, 21)
    fig, ax = plt.subplots()
    ax.axhspan(t0, tf, facecolor="blue", alpha=0.25)
    ax.set_ylim(t0 - datetime.timedelta(days=5),
                tf + datetime.timedelta(days=5))
    fig.subplots_adjust(left=0.25)


@image_comparison(['date_axvspan.png'])
def test_date_axvspan():
    # test axvspan with date inputs
    t0 = datetime.datetime(2000, 1, 20)
    tf = datetime.datetime(2010, 1, 21)
    fig, ax = plt.subplots()
    ax.axvspan(t0, tf, facecolor="blue", alpha=0.25)
    ax.set_xlim(t0 - datetime.timedelta(days=720),
                tf + datetime.timedelta(days=720))
    fig.autofmt_xdate()


@image_comparison(['date_axhline.png'])
def test_date_axhline():
    # test axhline with date inputs
    t0 = datetime.datetime(2009, 1, 20)
    tf = datetime.datetime(2009, 1, 31)
    fig, ax = plt.subplots()
    ax.axhline(t0, color="blue", lw=3)
    ax.set_ylim(t0 - datetime.timedelta(days=5),
                tf + datetime.timedelta(days=5))
    fig.subplots_adjust(left=0.25)


@image_comparison(['date_axvline.png'])
def test_date_axvline():
    # test axvline with date inputs
    t0 = datetime.datetime(2000, 1, 20)
    tf = datetime.datetime(2000, 1, 21)
    fig, ax = plt.subplots()
    ax.axvline(t0, color="red", lw=3)
    ax.set_xlim(t0 - datetime.timedelta(days=5),
                tf + datetime.timedelta(days=5))
    fig.autofmt_xdate()


def test_too_many_date_ticks(caplog):
    # Attempt to test SF 2715172, see
    # https://sourceforge.net/tracker/?func=detail&aid=2715172&group_id=80706&atid=560720
    # setting equal datetimes triggers and expander call in
    # transforms.nonsingular which results in too many ticks in the
    # DayLocator.  This should emit a log at WARNING level.
    caplog.set_level("WARNING")
    t0 = datetime.datetime(2000, 1, 20)
    tf = datetime.datetime(2000, 1, 20)
    fig, ax = plt.subplots()
    with pytest.warns(UserWarning) as rec:
        ax.set_xlim((t0, tf), auto=True)
        assert len(rec) == 1
        assert ('Attempting to set identical low and high xlims'
                in str(rec[0].message))
    ax.plot([], [])
    ax.xaxis.set_major_locator(mdates.DayLocator())
    v = ax.xaxis.get_major_locator()()
    assert len(v) > 1000
    # The warning is emitted multiple times because the major locator is also
    # called both when placing the minor ticks (for overstriking detection) and
    # during tick label positioning.
    assert caplog.records and all(
        record.name == "matplotlib.ticker" and record.levelname == "WARNING"
        for record in caplog.records)
    assert len(caplog.records) > 0


def _new_epoch_decorator(thefunc):
    @functools.wraps(thefunc)
    def wrapper():
        mdates._reset_epoch_test_example()
        mdates.set_epoch('2000-01-01')
        thefunc()
        mdates._reset_epoch_test_example()
    return wrapper


@image_comparison(['RRuleLocator_bounds.png'])
def test_RRuleLocator():
    import matplotlib.testing.jpl_units as units
    units.register()
    # This will cause the RRuleLocator to go out of bounds when it tries
    # to add padding to the limits, so we make sure it caps at the correct
    # boundary values.
    t0 = datetime.datetime(1000, 1, 1)
    tf = datetime.datetime(6000, 1, 1)

    fig = plt.figure()
    ax = plt.subplot()
    ax.set_autoscale_on(True)
    ax.plot([t0, tf], [0.0, 1.0], marker='o')

    rrule = mdates.rrulewrapper(dateutil.rrule.YEARLY, interval=500)
    locator = mdates.RRuleLocator(rrule)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.AutoDateFormatter(locator))

    ax.autoscale_view()
    fig.autofmt_xdate()


def test_RRuleLocator_dayrange():
    loc = mdates.DayLocator()
    x1 = datetime.datetime(year=1, month=1, day=1, tzinfo=mdates.UTC)
    y1 = datetime.datetime(year=1, month=1, day=16, tzinfo=mdates.UTC)
    loc.tick_values(x1, y1)
    # On success, no overflow error shall be thrown


def test_RRuleLocator_close_minmax():
    # if d1 and d2 are very close together, rrule cannot create
    # reasonable tick intervals; ensure that this is handled properly
    rrule = mdates.rrulewrapper(dateutil.rrule.SECONDLY, interval=5)
    loc = mdates.RRuleLocator(rrule)
    d1 = datetime.datetime(year=2020, month=1, day=1)
    d2 = datetime.datetime(year=2020, month=1, day=1, microsecond=1)
    expected = ['2020-01-01 00:00:00+00:00',
                '2020-01-01 00:00:00.000001+00:00']
    assert list(map(str, mdates.num2date(loc.tick_values(d1, d2)))) == expected


@image_comparison(['DateFormatter_fractionalSeconds.png'])
def test_DateFormatter():
    import matplotlib.testing.jpl_units as units
    units.register()

    # Lets make sure that DateFormatter will allow us to have tick marks
    # at intervals of fractional seconds.

    t0 = datetime.datetime(2001, 1, 1, 0, 0, 0)
    tf = datetime.datetime(2001, 1, 1, 0, 0, 1)

    fig = plt.figure()
    ax = plt.subplot()
    ax.set_autoscale_on(True)
    ax.plot([t0, tf], [0.0, 1.0], marker='o')

    # rrule = mpldates.rrulewrapper( dateutil.rrule.YEARLY, interval=500 )
    # locator = mpldates.RRuleLocator( rrule )
    # ax.xaxis.set_major_locator( locator )
    # ax.xaxis.set_major_formatter( mpldates.AutoDateFormatter(locator) )

    ax.autoscale_view()
    fig.autofmt_xdate()


def test_locator_set_formatter():
    """
    Test if setting the locator only will update the AutoDateFormatter to use
    the new locator.
    """
    plt.rcParams["date.autoformatter.minute"] = "%d %H:%M"
    t = [datetime.datetime(2018, 9, 30, 8, 0),
         datetime.datetime(2018, 9, 30, 8, 59),
         datetime.datetime(2018, 9, 30, 10, 30)]
    x = [2, 3, 1]

    fig, ax = plt.subplots()
    ax.plot(t, x)
    ax.xaxis.set_major_locator(mdates.MinuteLocator((0, 30)))
    fig.canvas.draw()
    ticklabels = [tl.get_text() for tl in ax.get_xticklabels()]
    expected = ['30 08:00', '30 08:30', '30 09:00',
                '30 09:30', '30 10:00', '30 10:30']
    assert ticklabels == expected

    ax.xaxis.set_major_locator(mticker.NullLocator())
    ax.xaxis.set_minor_locator(mdates.MinuteLocator((5, 55)))
    decoy_loc = mdates.MinuteLocator((12, 27))
    ax.xaxis.set_minor_formatter(mdates.AutoDateFormatter(decoy_loc))

    ax.xaxis.set_minor_locator(mdates.MinuteLocator((15, 45)))
    fig.canvas.draw()
    ticklabels = [tl.get_text() for tl in ax.get_xticklabels(which="minor")]
    expected = ['30 08:15', '30 08:45', '30 09:15', '30 09:45', '30 10:15']
    assert ticklabels == expected


def test_date_formatter_callable():

    class _Locator:
        def _get_unit(self): return -11

    def callable_formatting_function(dates, _):
        return [dt.strftime('%d-%m//%Y') for dt in dates]

    formatter = mdates.AutoDateFormatter(_Locator())
    formatter.scaled[-10] = callable_formatting_function
    assert formatter([datetime.datetime(2014, 12, 25)]) == ['25-12//2014']


@pytest.mark.parametrize('delta, expected', [
    (datetime.timedelta(weeks=52 * 200),
     [r'$\mathdefault{%d}$' % year for year in range(1990, 2171, 20)]),
    (datetime.timedelta(days=30),
     [r'$\mathdefault{1990{-}01{-}%02d}$' % day for day in range(1, 32, 3)]),
    (datetime.timedelta(hours=20),
     [r'$\mathdefault{01{-}01\;%02d}$' % hour for hour in range(0, 21, 2)]),
    (datetime.timedelta(minutes=10),
     [r'$\mathdefault{01\;00{:}%02d}$' % minu for minu in range(0, 11)]),
])
def test_date_formatter_usetex(delta, expected):
    style.use("default")

    d1 = datetime.datetime(1990, 1, 1)
    d2 = d1 + delta

    locator = mdates.AutoDateLocator(interval_multiples=False)
    locator.create_dummy_axis()
    locator.axis.set_view_interval(mdates.date2num(d1), mdates.date2num(d2))

    formatter = mdates.AutoDateFormatter(locator, usetex=True)
    assert [formatter(loc) for loc in locator()] == expected


def test_drange():
    """
    This test should check if drange works as expected, and if all the
    rounding errors are fixed
    """
    start = datetime.datetime(2011, 1, 1, tzinfo=mdates.UTC)
    end = datetime.datetime(2011, 1, 2, tzinfo=mdates.UTC)
    delta = datetime.timedelta(hours=1)
    # We expect 24 values in drange(start, end, delta), because drange returns
    # dates from an half open interval [start, end)
    assert len(mdates.drange(start, end, delta)) == 24

    # Same if interval ends slightly earlier
    end = end - datetime.timedelta(microseconds=1)
    assert len(mdates.drange(start, end, delta)) == 24

    # if end is a little bit later, we expect the range to contain one element
    # more
    end = end + datetime.timedelta(microseconds=2)
    assert len(mdates.drange(start, end, delta)) == 25

    # reset end
    end = datetime.datetime(2011, 1, 2, tzinfo=mdates.UTC)

    # and tst drange with "complicated" floats:
    # 4 hours = 1/6 day, this is an "dangerous" float
    delta = datetime.timedelta(hours=4)
    daterange = mdates.drange(start, end, delta)
    assert len(daterange) == 6
    assert mdates.num2date(daterange[-1]) == (end - delta)


@_new_epoch_decorator
def test_auto_date_locator():
    def _create_auto_date_locator(date1, date2):
        locator = mdates.AutoDateLocator(interval_multiples=False)
        locator.create_dummy_axis()
        locator.axis.set_view_interval(*mdates.date2num([date1, date2]))
        return locator

    d1 = datetime.datetime(1990, 1, 1)
    results = ([datetime.timedelta(weeks=52 * 200),
                ['1990-01-01 00:00:00+00:00', '2010-01-01 00:00:00+00:00',
                 '2030-01-01 00:00:00+00:00', '2050-01-01 00:00:00+00:00',
                 '2070-01-01 00:00:00+00:00', '2090-01-01 00:00:00+00:00',
                 '2110-01-01 00:00:00+00:00', '2130-01-01 00:00:00+00:00',
                 '2150-01-01 00:00:00+00:00', '2170-01-01 00:00:00+00:00']
                ],
               [datetime.timedelta(weeks=52),
                ['1990-01-01 00:00:00+00:00', '1990-02-01 00:00:00+00:00',
                 '1990-03-01 00:00:00+00:00', '1990-04-01 00:00:00+00:00',
                 '1990-05-01 00:00:00+00:00', '1990-06-01 00:00:00+00:00',
                 '1990-07-01 00:00:00+00:00', '1990-08-01 00:00:00+00:00',
                 '1990-09-01 00:00:00+00:00', '1990-10-01 00:00:00+00:00',
                 '1990-11-01 00:00:00+00:00', '1990-12-01 00:00:00+00:00']
                ],
               [datetime.timedelta(days=141),
                ['1990-01-05 00:00:00+00:00', '1990-01-26 00:00:00+00:00',
                 '1990-02-16 00:00:00+00:00', '1990-03-09 00:00:00+00:00',
                 '1990-03-30 00:00:00+00:00', '1990-04-20 00:00:00+00:00',
                 '1990-05-11 00:00:00+00:00']
                ],
               [datetime.timedelta(days=40),
                ['1990-01-03 00:00:00+00:00', '1990-01-10 00:00:00+00:00',
                 '1990-01-17 00:00:00+00:00', '1990-01-24 00:00:00+00:00',
                 '1990-01-31 00:00:00+00:00', '1990-02-07 00:00:00+00:00']
                ],
               [datetime.timedelta(hours=40),
                ['1990-01-01 00:00:00+00:00', '1990-01-01 04:00:00+00:00',
                 '1990-01-01 08:00:00+00:00', '1990-01-01 12:00:00+00:00',
                 '1990-01-01 16:00:00+00:00', '1990-01-01 20:00:00+00:00',
                 '1990-01-02 00:00:00+00:00', '1990-01-02 04:00:00+00:00',
                 '1990-01-02 08:00:00+00:00', '1990-01-02 12:00:00+00:00',
                 '1990-01-02 16:00:00+00:00']
                ],
               [datetime.timedelta(minutes=20),
                ['1990-01-01 00:00:00+00:00', '1990-01-01 00:05:00+00:00',
                 '1990-01-01 00:10:00+00:00', '1990-01-01 00:15:00+00:00',
                 '1990-01-01 00:20:00+00:00']
                ],
               [datetime.timedelta(seconds=40),
                ['1990-01-01 00:00:00+00:00', '1990-01-01 00:00:05+00:00',
                 '1990-01-01 00:00:10+00:00', '1990-01-01 00:00:15+00:00',
                 '1990-01-01 00:00:20+00:00', '1990-01-01 00:00:25+00:00',
                 '1990-01-01 00:00:30+00:00', '1990-01-01 00:00:35+00:00',
                 '1990-01-01 00:00:40+00:00']
                ],
               [datetime.timedelta(microseconds=1500),
                ['1989-12-31 23:59:59.999500+00:00',
                 '1990-01-01 00:00:00+00:00',
                 '1990-01-01 00:00:00.000500+00:00',
                 '1990-01-01 00:00:00.001000+00:00',
                 '1990-01-01 00:00:00.001500+00:00',
                 '1990-01-01 00:00:00.002000+00:00']
                ],
               )

    for t_delta, expected in results:
        d2 = d1 + t_delta
        locator = _create_auto_date_locator(d1, d2)
        assert list(map(str, mdates.num2date(locator()))) == expected

    locator = mdates.AutoDateLocator(interval_multiples=False)
    assert locator.maxticks == {0: 11, 1: 12, 3: 11, 4: 12, 5: 11, 6: 11, 7: 8}

    locator = mdates.AutoDateLocator(maxticks={dateutil.rrule.MONTHLY: 5})
    assert locator.maxticks == {0: 11, 1: 5, 3: 11, 4: 12, 5: 11, 6: 11, 7: 8}

    locator = mdates.AutoDateLocator(maxticks=5)
    assert locator.maxticks == {0: 5, 1: 5, 3: 5, 4: 5, 5: 5, 6: 5, 7: 5}


@_new_epoch_decorator
def test_auto_date_locator_intmult():
    def _create_auto_date_locator(date1, date2):
        locator = mdates.AutoDateLocator(interval_multiples=True)
        locator.create_dummy_axis()
        locator.axis.set_view_interval(*mdates.date2num([date1, date2]))
        return locator

    results = ([datetime.timedelta(weeks=52 * 200),
                ['1980-01-01 00:00:00+00:00', '2000-01-01 00:00:00+00:00',
                 '2020-01-01 00:00:00+00:00', '2040-01-01 00:00:00+00:00',
                 '2060-01-01 00:00:00+00:00', '2080-01-01 00:00:00+00:00',
                 '2100-01-01 00:00:00+00:00', '2120-01-01 00:00:00+00:00',
                 '2140-01-01 00:00:00+00:00', '2160-01-01 00:00:00+00:00',
                 '2180-01-01 00:00:00+00:00', '2200-01-01 00:00:00+00:00']
                ],
               [datetime.timedelta(weeks=52),
                ['1997-01-01 00:00:00+00:00', '1997-02-01 00:00:00+00:00',
                 '1997-03-01 00:00:00+00:00', '1997-04-01 00:00:00+00:00',
                 '1997-05-01 00:00:00+00:00', '1997-06-01 00:00:00+00:00',
                 '1997-07-01 00:00:00+00:00', '1997-08-01 00:00:00+00:00',
                 '1997-09-01 00:00:00+00:00', '1997-10-01 00:00:00+00:00',
                 '1997-11-01 00:00:00+00:00', '1997-12-01 00:00:00+00:00']
                ],
               [datetime.timedelta(days=141),
                ['1997-01-01 00:00:00+00:00', '1997-01-15 00:00:00+00:00',
                 '1997-02-01 00:00:00+00:00', '1997-02-15 00:00:00+00:00',
                 '1997-03-01 00:00:00+00:00', '1997-03-15 00:00:00+00:00',
                 '1997-04-01 00:00:00+00:00', '1997-04-15 00:00:00+00:00',
                 '1997-05-01 00:00:00+00:00', '1997-05-15 00:00:00+00:00']
                ],
               [datetime.timedelta(days=40),
                ['1997-01-01 00:00:00+00:00', '1997-01-05 00:00:00+00:00',
                 '1997-01-09 00:00:00+00:00', '1997-01-13 00:00:00+00:00',
                 '1997-01-17 00:00:00+00:00', '1997-01-21 00:00:00+00:00',
                 '1997-01-25 00:00:00+00:00', '1997-01-29 00:00:00+00:00',
                 '1997-02-01 00:00:00+00:00', '1997-02-05 00:00:00+00:00',
                 '1997-02-09 00:00:00+00:00']
                ],
               [datetime.timedelta(hours=40),
                ['1997-01-01 00:00:00+00:00', '1997-01-01 04:00:00+00:00',
                 '1997-01-01 08:00:00+00:00', '1997-01-01 12:00:00+00:00',
                 '1997-01-01 16:00:00+00:00', '1997-01-01 20:00:00+00:00',
                 '1997-01-02 00:00:00+00:00', '1997-01-02 04:00:00+00:00',
                 '1997-01-02 08:00:00+00:00', '1997-01-02 12:00:00+00:00',
                 '1997-01-02 16:00:00+00:00']
                ],
               [datetime.timedelta(minutes=20),
                ['1997-01-01 00:00:00+00:00', '1997-01-01 00:05:00+00:00',
                 '1997-01-01 00:10:00+00:00', '1997-01-01 00:15:00+00:00',
                 '1997-01-01 00:20:00+00:00']
                ],
               [datetime.timedelta(seconds=40),
                ['1997-01-01 00:00:00+00:00', '1997-01-01 00:00:05+00:00',
                 '1997-01-01 00:00:10+00:00', '1997-01-01 00:00:15+00:00',
                 '1997-01-01 00:00:20+00:00', '1997-01-01 00:00:25+00:00',
                 '1997-01-01 00:00:30+00:00', '1997-01-01 00:00:35+00:00',
                 '1997-01-01 00:00:40+00:00']
                ],
               [datetime.timedelta(microseconds=1500),
                ['1996-12-31 23:59:59.999500+00:00',
                 '1997-01-01 00:00:00+00:00',
                 '1997-01-01 00:00:00.000500+00:00',
                 '1997-01-01 00:00:00.001000+00:00',
                 '1997-01-01 00:00:00.001500+00:00',
                 '1997-01-01 00:00:00.002000+00:00']
                ],
               )

    d1 = datetime.datetime(1997, 1, 1)
    for t_delta, expected in results:
        d2 = d1 + t_delta
        locator = _create_auto_date_locator(d1, d2)
        assert list(map(str, mdates.num2date(locator()))) == expected


def test_concise_formatter_subsecond():
    locator = mdates.AutoDateLocator(interval_multiples=True)
    formatter = mdates.ConciseDateFormatter(locator)
    year_1996 = 9861.0
    strings = formatter.format_ticks([
        year_1996,
        year_1996 + 500 / mdates.MUSECONDS_PER_DAY,
        year_1996 + 900 / mdates.MUSECONDS_PER_DAY])
    assert strings == ['00:00', '00.0005', '00.0009']


def test_concise_formatter():
    def _create_auto_date_locator(date1, date2):
        fig, ax = plt.subplots()

        locator = mdates.AutoDateLocator(interval_multiples=True)
        formatter = mdates.ConciseDateFormatter(locator)
        ax.yaxis.set_major_locator(locator)
        ax.yaxis.set_major_formatter(formatter)
        ax.set_ylim(date1, date2)
        fig.canvas.draw()
        sts = [st.get_text() for st in ax.get_yticklabels()]
        return sts

    d1 = datetime.datetime(1997, 1, 1)
    results = ([datetime.timedelta(weeks=52 * 200),
                [str(t) for t in range(1980, 2201, 20)]
                ],
               [datetime.timedelta(weeks=52),
                ['1997', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug',
                 'Sep', 'Oct', 'Nov', 'Dec']
                ],
               [datetime.timedelta(days=141),
                ['Jan', '15', 'Feb', '15', 'Mar', '15', 'Apr', '15',
                 'May', '15']
                ],
               [datetime.timedelta(days=40),
                ['Jan', '05', '09', '13', '17', '21', '25', '29', 'Feb',
                 '05', '09']
                ],
               [datetime.timedelta(hours=40),
                ['Jan-01', '04:00', '08:00', '12:00', '16:00', '20:00',
                 'Jan-02', '04:00', '08:00', '12:00', '16:00']
                ],
               [datetime.timedelta(minutes=20),
                ['00:00', '00:05', '00:10', '00:15', '00:20']
                ],
               [datetime.timedelta(seconds=40),
                ['00:00', '05', '10', '15', '20', '25', '30', '35', '40']
                ],
               [datetime.timedelta(seconds=2),
                ['59.5', '00:00', '00.5', '01.0', '01.5', '02.0', '02.5']
                ],
               )
    for t_delta, expected in results:
        d2 = d1 + t_delta
        strings = _create_auto_date_locator(d1, d2)
        assert strings == expected


@pytest.mark.parametrize('t_delta, expected', [
    (datetime.timedelta(seconds=0.01), '1997-Jan-01 00:00'),
    (datetime.timedelta(minutes=1), '1997-Jan-01 00:01'),
    (datetime.timedelta(hours=1), '1997-Jan-01'),
    (datetime.timedelta(days=1), '1997-Jan-02'),
    (datetime.timedelta(weeks=1), '1997-Jan'),
    (datetime.timedelta(weeks=26), ''),
    (datetime.timedelta(weeks=520), '')
])
def test_concise_formatter_show_offset(t_delta, expected):
    d1 = datetime.datetime(1997, 1, 1)
    d2 = d1 + t_delta

    fig, ax = plt.subplots()
    locator = mdates.AutoDateLocator()
    formatter = mdates.ConciseDateFormatter(locator)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)

    ax.plot([d1, d2], [0, 0])
    fig.canvas.draw()
    assert formatter.get_offset() == expected


def test_concise_formatter_show_offset_inverted():
    # Test for github issue #28481
    d1 = datetime.datetime(1997, 1, 1)
    d2 = d1 + datetime.timedelta(days=60)

    fig, ax = plt.subplots()
    locator = mdates.AutoDateLocator()
    formatter = mdates.ConciseDateFormatter(locator)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)
    ax.invert_xaxis()

    ax.plot([d1, d2], [0, 0])
    fig.canvas.draw()
    assert formatter.get_offset() == '1997-Jan'


def test_concise_converter_stays():
    # This test demonstrates problems introduced by gh-23417 (reverted in gh-25278)
    # In particular, downstream libraries like Pandas had their designated converters
    # overridden by actions like setting xlim (or plotting additional points using
    # stdlib/numpy dates and string date representation, which otherwise work fine with
    # their date converters)
    # While this is a bit of a toy example that would be unusual to see it demonstrates
    # the same ideas (namely having a valid converter already applied that is desired)
    # without introducing additional subclasses.
    # See also discussion at gh-25219 for how Pandas was affected
    x = [datetime.datetime(2000, 1, 1), datetime.datetime(2020, 2, 20)]
    y = [0, 1]
    fig, ax = plt.subplots()
    ax.plot(x, y)
    # Bypass Switchable date converter
    conv = mdates.ConciseDateConverter()
    with pytest.warns(UserWarning, match="already has a converter"):
        ax.xaxis.set_converter(conv)
    assert ax.xaxis.units is None
    ax.set_xlim(*x)
    assert ax.xaxis.get_converter() == conv


def test_offset_changes():
    fig, ax = plt.subplots()

    d1 = datetime.datetime(1997, 1, 1)
    d2 = d1 + datetime.timedelta(weeks=520)

    locator = mdates.AutoDateLocator()
    formatter = mdates.ConciseDateFormatter(locator)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)

    ax.plot([d1, d2], [0, 0])
    fig.draw_without_rendering()
    assert formatter.get_offset() == ''
    ax.set_xlim(d1, d1 + datetime.timedelta(weeks=3))
    fig.draw_without_rendering()
    assert formatter.get_offset() == '1997-Jan'
    ax.set_xlim(d1 + datetime.timedelta(weeks=7),
                d1 + datetime.timedelta(weeks=30))
    fig.draw_without_rendering()
    assert formatter.get_offset() == '1997'
    ax.set_xlim(d1, d1 + datetime.timedelta(weeks=520))
    fig.draw_without_rendering()
    assert formatter.get_offset() == ''


@pytest.mark.parametrize('t_delta, expected', [
    (datetime.timedelta(weeks=52 * 200),
     ['$\\mathdefault{%d}$' % (t, ) for t in range(1980, 2201, 20)]),
    (datetime.timedelta(days=40),
     ['Jan', '$\\mathdefault{05}$', '$\\mathdefault{09}$',
      '$\\mathdefault{13}$', '$\\mathdefault{17}$', '$\\mathdefault{21}$',
      '$\\mathdefault{25}$', '$\\mathdefault{29}$', 'Feb',
      '$\\mathdefault{05}$', '$\\mathdefault{09}$']),
    (datetime.timedelta(hours=40),
     ['Jan$\\mathdefault{{-}01}$', '$\\mathdefault{04{:}00}$',
      '$\\mathdefault{08{:}00}$', '$\\mathdefault{12{:}00}$',
      '$\\mathdefault{16{:}00}$', '$\\mathdefault{20{:}00}$',
      'Jan$\\mathdefault{{-}02}$', '$\\mathdefault{04{:}00}$',
      '$\\mathdefault{08{:}00}$', '$\\mathdefault{12{:}00}$',
      '$\\mathdefault{16{:}00}$']),
    (datetime.timedelta(seconds=2),
     ['$\\mathdefault{59.5}$', '$\\mathdefault{00{:}00}$',
      '$\\mathdefault{00.5}$', '$\\mathdefault{01.0}$',
      '$\\mathdefault{01.5}$', '$\\mathdefault{02.0}$',
      '$\\mathdefault{02.5}$']),
])
def test_concise_formatter_usetex(t_delta, expected):
    d1 = datetime.datetime(1997, 1, 1)
    d2 = d1 + t_delta

    locator = mdates.AutoDateLocator(interval_multiples=True)
    locator.create_dummy_axis()
    locator.axis.set_view_interval(mdates.date2num(d1), mdates.date2num(d2))

    formatter = mdates.ConciseDateFormatter(locator, usetex=True)
    assert formatter.format_ticks(locator()) == expected


def test_concise_formatter_formats():
    formats = ['%Y', '%m/%Y', 'day: %d',
               '%H hr %M min', '%H hr %M min', '%S.%f sec']

    def _create_auto_date_locator(date1, date2):
        fig, ax = plt.subplots()

        locator = mdates.AutoDateLocator(interval_multiples=True)
        formatter = mdates.ConciseDateFormatter(locator, formats=formats)
        ax.yaxis.set_major_locator(locator)
        ax.yaxis.set_major_formatter(formatter)
        ax.set_ylim(date1, date2)
        fig.canvas.draw()
        sts = [st.get_text() for st in ax.get_yticklabels()]
        return sts

    d1 = datetime.datetime(1997, 1, 1)
    results = (
        [datetime.timedelta(weeks=52 * 200), [str(t) for t in range(1980,
         2201, 20)]],
        [datetime.timedelta(weeks=52), [
            '1997', '02/1997', '03/1997', '04/1997', '05/1997', '06/1997',
            '07/1997', '08/1997', '09/1997', '10/1997', '11/1997', '12/1997',
            ]],
        [datetime.timedelta(days=141), [
            '01/1997', 'day: 15', '02/1997', 'day: 15', '03/1997', 'day: 15',
            '04/1997', 'day: 15', '05/1997', 'day: 15',
            ]],
        [datetime.timedelta(days=40), [
            '01/1997', 'day: 05', 'day: 09', 'day: 13', 'day: 17', 'day: 21',
            'day: 25', 'day: 29', '02/1997', 'day: 05', 'day: 09',
            ]],
        [datetime.timedelta(hours=40), [
            'day: 01', '04 hr 00 min', '08 hr 00 min', '12 hr 00 min',
            '16 hr 00 min', '20 hr 00 min', 'day: 02', '04 hr 00 min',
            '08 hr 00 min', '12 hr 00 min', '16 hr 00 min',
            ]],
        [datetime.timedelta(minutes=20), ['00 hr 00 min', '00 hr 05 min',
         '00 hr 10 min', '00 hr 15 min', '00 hr 20 min']],
        [datetime.timedelta(seconds=40), [
            '00 hr 00 min', '05.000000 sec', '10.000000 sec',
            '15.000000 sec', '20.000000 sec', '25.000000 sec',
            '30.000000 sec', '35.000000 sec', '40.000000 sec',
            ]],
        [datetime.timedelta(seconds=2), [
            '59.500000 sec', '00 hr 00 min', '00.500000 sec', '01.000000 sec',
            '01.500000 sec', '02.000000 sec', '02.500000 sec',
            ]],
        )
    for t_delta, expected in results:
        d2 = d1 + t_delta
        strings = _create_auto_date_locator(d1, d2)
        assert strings == expected


def test_concise_formatter_zformats():
    zero_formats = ['', "'%y", '%B', '%m-%d', '%S', '%S.%f']

    def _create_auto_date_locator(date1, date2):
        fig, ax = plt.subplots()

        locator = mdates.AutoDateLocator(interval_multiples=True)
        formatter = mdates.ConciseDateFormatter(
            locator, zero_formats=zero_formats)
        ax.yaxis.set_major_locator(locator)
        ax.yaxis.set_major_formatter(formatter)
        ax.set_ylim(date1, date2)
        fig.canvas.draw()
        sts = [st.get_text() for st in ax.get_yticklabels()]
        return sts

    d1 = datetime.datetime(1997, 1, 1)
    results = ([datetime.timedelta(weeks=52 * 200),
                [str(t) for t in range(1980, 2201, 20)]
                ],
               [datetime.timedelta(weeks=52),
                ["'97", 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                ],
               [datetime.timedelta(days=141),
                ['January', '15', 'February', '15', 'March',
                    '15', 'April', '15', 'May', '15']
                ],
               [datetime.timedelta(days=40),
                ['January', '05', '09', '13', '17', '21',
                    '25', '29', 'February', '05', '09']
                ],
               [datetime.timedelta(hours=40),
                ['01-01', '04:00', '08:00', '12:00', '16:00', '20:00',
                    '01-02', '04:00', '08:00', '12:00', '16:00']
                ],
               [datetime.timedelta(minutes=20),
                ['00', '00:05', '00:10', '00:15', '00:20']
                ],
               [datetime.timedelta(seconds=40),
                ['00', '05', '10', '15', '20', '25', '30', '35', '40']
                ],
               [datetime.timedelta(seconds=2),
                ['59.5', '00.0', '00.5', '01.0', '01.5', '02.0', '02.5']
                ],
               )
    for t_delta, expected in results:
        d2 = d1 + t_delta
        strings = _create_auto_date_locator(d1, d2)
        assert strings == expected


def test_concise_formatter_tz():
    def _create_auto_date_locator(date1, date2, tz):
        fig, ax = plt.subplots()

        locator = mdates.AutoDateLocator(interval_multiples=True)
        formatter = mdates.ConciseDateFormatter(locator, tz=tz)
        ax.yaxis.set_major_locator(locator)
        ax.yaxis.set_major_formatter(formatter)
        ax.set_ylim(date1, date2)
        fig.canvas.draw()
        sts = [st.get_text() for st in ax.get_yticklabels()]
        return sts, ax.yaxis.get_offset_text().get_text()

    d1 = datetime.datetime(1997, 1, 1).replace(tzinfo=datetime.timezone.utc)
    results = ([datetime.timedelta(hours=40),
                ['03:00', '07:00', '11:00', '15:00', '19:00', '23:00',
                 '03:00', '07:00', '11:00', '15:00', '19:00'],
                "1997-Jan-02"
                ],
               [datetime.timedelta(minutes=20),
                ['03:00', '03:05', '03:10', '03:15', '03:20'],
                "1997-Jan-01"
                ],
               [datetime.timedelta(seconds=40),
                ['03:00', '05', '10', '15', '20', '25', '30', '35', '40'],
                "1997-Jan-01 03:00"
                ],
               [datetime.timedelta(seconds=2),
                ['59.5', '03:00', '00.5', '01.0', '01.5', '02.0', '02.5'],
                "1997-Jan-01 03:00"
                ],
               )

    new_tz = datetime.timezone(datetime.timedelta(hours=3))
    for t_delta, expected_strings, expected_offset in results:
        d2 = d1 + t_delta
        strings, offset = _create_auto_date_locator(d1, d2, new_tz)
        assert strings == expected_strings
        assert offset == expected_offset


def test_auto_date_locator_intmult_tz():
    def _create_auto_date_locator(date1, date2, tz):
        locator = mdates.AutoDateLocator(interval_multiples=True, tz=tz)
        locator.create_dummy_axis()
        locator.axis.set_view_interval(*mdates.date2num([date1, date2]))
        return locator

    results = ([datetime.timedelta(weeks=52*200),
                ['1980-01-01 00:00:00-08:00', '2000-01-01 00:00:00-08:00',
                 '2020-01-01 00:00:00-08:00', '2040-01-01 00:00:00-08:00',
                 '2060-01-01 00:00:00-08:00', '2080-01-01 00:00:00-08:00',
                 '2100-01-01 00:00:00-08:00', '2120-01-01 00:00:00-08:00',
                 '2140-01-01 00:00:00-08:00', '2160-01-01 00:00:00-08:00',
                 '2180-01-01 00:00:00-08:00', '2200-01-01 00:00:00-08:00']
                ],
               [datetime.timedelta(weeks=52),
                ['1997-01-01 00:00:00-08:00', '1997-02-01 00:00:00-08:00',
                 '1997-03-01 00:00:00-08:00', '1997-04-01 00:00:00-08:00',
                 '1997-05-01 00:00:00-07:00', '1997-06-01 00:00:00-07:00',
                 '1997-07-01 00:00:00-07:00', '1997-08-01 00:00:00-07:00',
                 '1997-09-01 00:00:00-07:00', '1997-10-01 00:00:00-07:00',
                 '1997-11-01 00:00:00-08:00', '1997-12-01 00:00:00-08:00']
                ],
               [datetime.timedelta(days=141),
                ['1997-01-01 00:00:00-08:00', '1997-01-15 00:00:00-08:00',
                 '1997-02-01 00:00:00-08:00', '1997-02-15 00:00:00-08:00',
                 '1997-03-01 00:00:00-08:00', '1997-03-15 00:00:00-08:00',
                 '1997-04-01 00:00:00-08:00', '1997-04-15 00:00:00-07:00',
                 '1997-05-01 00:00:00-07:00', '1997-05-15 00:00:00-07:00']
                ],
               [datetime.timedelta(days=40),
                ['1997-01-01 00:00:00-08:00', '1997-01-05 00:00:00-08:00',
                 '1997-01-09 00:00:00-08:00', '1997-01-13 00:00:00-08:00',
                 '1997-01-17 00:00:00-08:00', '1997-01-21 00:00:00-08:00',
                 '1997-01-25 00:00:00-08:00', '1997-01-29 00:00:00-08:00',
                 '1997-02-01 00:00:00-08:00', '1997-02-05 00:00:00-08:00',
                 '1997-02-09 00:00:00-08:00']
                ],
               [datetime.timedelta(hours=40),
                ['1997-01-01 00:00:00-08:00', '1997-01-01 04:00:00-08:00',
                 '1997-01-01 08:00:00-08:00', '1997-01-01 12:00:00-08:00',
                 '1997-01-01 16:00:00-08:00', '1997-01-01 20:00:00-08:00',
                 '1997-01-02 00:00:00-08:00', '1997-01-02 04:00:00-08:00',
                 '1997-01-02 08:00:00-08:00', '1997-01-02 12:00:00-08:00',
                 '1997-01-02 16:00:00-08:00']
                ],
               [datetime.timedelta(minutes=20),
                ['1997-01-01 00:00:00-08:00', '1997-01-01 00:05:00-08:00',
                 '1997-01-01 00:10:00-08:00', '1997-01-01 00:15:00-08:00',
                 '1997-01-01 00:20:00-08:00']
                ],
               [datetime.timedelta(seconds=40),
                ['1997-01-01 00:00:00-08:00', '1997-01-01 00:00:05-08:00',
                 '1997-01-01 00:00:10-08:00', '1997-01-01 00:00:15-08:00',
                 '1997-01-01 00:00:20-08:00', '1997-01-01 00:00:25-08:00',
                 '1997-01-01 00:00:30-08:00', '1997-01-01 00:00:35-08:00',
                 '1997-01-01 00:00:40-08:00']
                ]
               )

    tz = dateutil.tz.gettz('Canada/Pacific')
    d1 = datetime.datetime(1997, 1, 1, tzinfo=tz)
    for t_delta, expected in results:
        with rc_context({'_internal.classic_mode': False}):
            d2 = d1 + t_delta
            locator = _create_auto_date_locator(d1, d2, tz)
            st = list(map(str, mdates.num2date(locator(), tz=tz)))
            assert st == expected


@image_comparison(['date_inverted_limit.png'])
def test_date_inverted_limit():
    # test ax hline with date inputs
    t0 = datetime.datetime(2009, 1, 20)
    tf = datetime.datetime(2009, 1, 31)
    fig, ax = plt.subplots()
    ax.axhline(t0, color="blue", lw=3)
    ax.set_ylim(t0 - datetime.timedelta(days=5),
                tf + datetime.timedelta(days=5))
    ax.invert_yaxis()
    fig.subplots_adjust(left=0.25)


def _test_date2num_dst(date_range, tz_convert):
    # Timezones

    BRUSSELS = dateutil.tz.gettz('Europe/Brussels')
    UTC = mdates.UTC

    # Create a list of timezone-aware datetime objects in UTC
    # Interval is 0b0.0000011 days, to prevent float rounding issues
    dtstart = datetime.datetime(2014, 3, 30, 0, 0, tzinfo=UTC)
    interval = datetime.timedelta(minutes=33, seconds=45)
    interval_days = interval.seconds / 86400
    N = 8

    dt_utc = date_range(start=dtstart, freq=interval, periods=N)
    dt_bxl = tz_convert(dt_utc, BRUSSELS)
    t0 = 735322.0 + mdates.date2num(np.datetime64('0000-12-31'))
    expected_ordinalf = [t0 + (i * interval_days) for i in range(N)]
    actual_ordinalf = list(mdates.date2num(dt_bxl))

    assert actual_ordinalf == expected_ordinalf


def test_date2num_dst():
    # Test for github issue #3896, but in date2num around DST transitions
    # with a timezone-aware pandas date_range object.

    class dt_tzaware(datetime.datetime):
        """
        This bug specifically occurs because of the normalization behavior of
        pandas Timestamp objects, so in order to replicate it, we need a
        datetime-like object that applies timezone normalization after
        subtraction.
        """

        def __sub__(self, other):
            r = super().__sub__(other)
            tzinfo = getattr(r, 'tzinfo', None)

            if tzinfo is not None:
                localizer = getattr(tzinfo, 'normalize', None)
                if localizer is not None:
                    r = tzinfo.normalize(r)

            if isinstance(r, datetime.datetime):
                r = self.mk_tzaware(r)

            return r

        def __add__(self, other):
            return self.mk_tzaware(super().__add__(other))

        def astimezone(self, tzinfo):
            dt = super().astimezone(tzinfo)
            return self.mk_tzaware(dt)

        @classmethod
        def mk_tzaware(cls, datetime_obj):
            kwargs = {}
            attrs = ('year',
                     'month',
                     'day',
                     'hour',
                     'minute',
                     'second',
                     'microsecond',
                     'tzinfo')

            for attr in attrs:
                val = getattr(datetime_obj, attr, None)
                if val is not None:
                    kwargs[attr] = val

            return cls(**kwargs)

    # Define a date_range function similar to pandas.date_range
    def date_range(start, freq, periods):
        dtstart = dt_tzaware.mk_tzaware(start)

        return [dtstart + (i * freq) for i in range(periods)]

    # Define a tz_convert function that converts a list to a new timezone.
    def tz_convert(dt_list, tzinfo):
        return [d.astimezone(tzinfo) for d in dt_list]

    _test_date2num_dst(date_range, tz_convert)


def test_date2num_dst_pandas(pd):
    # Test for github issue #3896, but in date2num around DST transitions
    # with a timezone-aware pandas date_range object.

    def tz_convert(*args):
        return pd.DatetimeIndex.tz_convert(*args).astype(object)

    _test_date2num_dst(pd.date_range, tz_convert)


def _test_rrulewrapper(attach_tz, get_tz):
    SYD = get_tz('Australia/Sydney')

    dtstart = attach_tz(datetime.datetime(2017, 4, 1, 0), SYD)
    dtend = attach_tz(datetime.datetime(2017, 4, 4, 0), SYD)

    rule = mdates.rrulewrapper(freq=dateutil.rrule.DAILY, dtstart=dtstart)

    act = rule.between(dtstart, dtend)
    exp = [datetime.datetime(2017, 4, 1, 13, tzinfo=dateutil.tz.tzutc()),
           datetime.datetime(2017, 4, 2, 14, tzinfo=dateutil.tz.tzutc())]

    assert act == exp


def test_rrulewrapper():
    def attach_tz(dt, zi):
        return dt.replace(tzinfo=zi)

    _test_rrulewrapper(attach_tz, dateutil.tz.gettz)

    SYD = dateutil.tz.gettz('Australia/Sydney')
    dtstart = datetime.datetime(2017, 4, 1, 0)
    dtend = datetime.datetime(2017, 4, 4, 0)
    rule = mdates.rrulewrapper(freq=dateutil.rrule.DAILY, dtstart=dtstart,
                               tzinfo=SYD, until=dtend)
    assert rule.after(dtstart) == datetime.datetime(2017, 4, 2, 0, 0,
                                                    tzinfo=SYD)
    assert rule.before(dtend) == datetime.datetime(2017, 4, 3, 0, 0,
                                                   tzinfo=SYD)

    # Test parts of __getattr__
    assert rule._base_tzinfo == SYD
    assert rule._interval == 1


@pytest.mark.pytz
def test_rrulewrapper_pytz():
    # Test to make sure pytz zones are supported in rrules
    pytz = pytest.importorskip("pytz")

    def attach_tz(dt, zi):
        return zi.localize(dt)

    _test_rrulewrapper(attach_tz, pytz.timezone)


@pytest.mark.pytz
def test_yearlocator_pytz():
    pytz = pytest.importorskip("pytz")

    tz = pytz.timezone('America/New_York')
    x = [tz.localize(datetime.datetime(2010, 1, 1))
         + datetime.timedelta(i) for i in range(2000)]
    locator = mdates.AutoDateLocator(interval_multiples=True, tz=tz)
    locator.create_dummy_axis()
    locator.axis.set_view_interval(mdates.date2num(x[0])-1.0,
                                   mdates.date2num(x[-1])+1.0)
    t = np.array([733408.208333, 733773.208333, 734138.208333,
                  734503.208333, 734869.208333, 735234.208333, 735599.208333])
    # convert to new epoch from old...
    t = t + mdates.date2num(np.datetime64('0000-12-31'))
    np.testing.assert_allclose(t, locator())
    expected = ['2009-01-01 00:00:00-05:00',
                '2010-01-01 00:00:00-05:00', '2011-01-01 00:00:00-05:00',
                '2012-01-01 00:00:00-05:00', '2013-01-01 00:00:00-05:00',
                '2014-01-01 00:00:00-05:00', '2015-01-01 00:00:00-05:00']
    st = list(map(str, mdates.num2date(locator(), tz=tz)))
    assert st == expected
    assert np.allclose(locator.tick_values(x[0], x[1]), np.array(
        [14610.20833333, 14610.33333333, 14610.45833333, 14610.58333333,
         14610.70833333, 14610.83333333, 14610.95833333, 14611.08333333,
         14611.20833333]))
    assert np.allclose(locator.get_locator(x[1], x[0]).tick_values(x[0], x[1]),
                       np.array(
        [14610.20833333, 14610.33333333, 14610.45833333, 14610.58333333,
         14610.70833333, 14610.83333333, 14610.95833333, 14611.08333333,
         14611.20833333]))


def test_YearLocator():
    def _create_year_locator(date1, date2, **kwargs):
        locator = mdates.YearLocator(**kwargs)
        locator.create_dummy_axis()
        locator.axis.set_view_interval(mdates.date2num(date1),
                                       mdates.date2num(date2))
        return locator

    d1 = datetime.datetime(1990, 1, 1)
    results = ([datetime.timedelta(weeks=52 * 200),
                {'base': 20, 'month': 1, 'day': 1},
                ['1980-01-01 00:00:00+00:00', '2000-01-01 00:00:00+00:00',
                 '2020-01-01 00:00:00+00:00', '2040-01-01 00:00:00+00:00',
                 '2060-01-01 00:00:00+00:00', '2080-01-01 00:00:00+00:00',
                 '2100-01-01 00:00:00+00:00', '2120-01-01 00:00:00+00:00',
                 '2140-01-01 00:00:00+00:00', '2160-01-01 00:00:00+00:00',
                 '2180-01-01 00:00:00+00:00', '2200-01-01 00:00:00+00:00']
                ],
               [datetime.timedelta(weeks=52 * 200),
                {'base': 20, 'month': 5, 'day': 16},
                ['1980-05-16 00:00:00+00:00', '2000-05-16 00:00:00+00:00',
                 '2020-05-16 00:00:00+00:00', '2040-05-16 00:00:00+00:00',
                 '2060-05-16 00:00:00+00:00', '2080-05-16 00:00:00+00:00',
                 '2100-05-16 00:00:00+00:00', '2120-05-16 00:00:00+00:00',
                 '2140-05-16 00:00:00+00:00', '2160-05-16 00:00:00+00:00',
                 '2180-05-16 00:00:00+00:00', '2200-05-16 00:00:00+00:00']
                ],
               [datetime.timedelta(weeks=52 * 5),
                {'base': 20, 'month': 9, 'day': 25},
                ['1980-09-25 00:00:00+00:00', '2000-09-25 00:00:00+00:00']
                ],
               )

    for delta, arguments, expected in results:
        d2 = d1 + delta
        locator = _create_year_locator(d1, d2, **arguments)
        assert list(map(str, mdates.num2date(locator()))) == expected


def test_DayLocator():
    with pytest.raises(ValueError):
        mdates.DayLocator(interval=-1)
    with pytest.raises(ValueError):
        mdates.DayLocator(interval=-1.5)
    with pytest.raises(ValueError):
        mdates.DayLocator(interval=0)
    with pytest.raises(ValueError):
        mdates.DayLocator(interval=1.3)
    mdates.DayLocator(interval=1.0)


def test_tz_utc():
    dt = datetime.datetime(1970, 1, 1, tzinfo=mdates.UTC)
    assert dt.tzname() == 'UTC'


@pytest.mark.parametrize("x, tdelta",
                         [(1, datetime.timedelta(days=1)),
                          ([1, 1.5], [datetime.timedelta(days=1),
                                      datetime.timedelta(days=1.5)])])
def test_num2timedelta(x, tdelta):
    dt = mdates.num2timedelta(x)
    assert dt == tdelta


def test_datetime64_in_list():
    dt = [np.datetime64('2000-01-01'), np.datetime64('2001-01-01')]
    dn = mdates.date2num(dt)
    # convert fixed values from old to new epoch
    t = (np.array([730120.,  730486.]) +
         mdates.date2num(np.datetime64('0000-12-31')))
    np.testing.assert_equal(dn, t)


def test_change_epoch():
    date = np.datetime64('2000-01-01')

    # use private method to clear the epoch and allow it to be set...
    mdates._reset_epoch_test_example()
    mdates.get_epoch()  # Set default.

    with pytest.raises(RuntimeError):
        # this should fail here because there is a sentinel on the epoch
        # if the epoch has been used then it cannot be set.
        mdates.set_epoch('0000-01-01')

    mdates._reset_epoch_test_example()
    mdates.set_epoch('1970-01-01')
    dt = (date - np.datetime64('1970-01-01')).astype('datetime64[D]')
    dt = dt.astype('int')
    np.testing.assert_equal(mdates.date2num(date), float(dt))

    mdates._reset_epoch_test_example()
    mdates.set_epoch('0000-12-31')
    np.testing.assert_equal(mdates.date2num(date), 730120.0)

    mdates._reset_epoch_test_example()
    mdates.set_epoch('1970-01-01T01:00:00')
    np.testing.assert_allclose(mdates.date2num(date), dt - 1./24.)
    mdates._reset_epoch_test_example()
    mdates.set_epoch('1970-01-01T00:00:00')
    np.testing.assert_allclose(
        mdates.date2num(np.datetime64('1970-01-01T12:00:00')),
        0.5)


def test_warn_notintervals():
    dates = np.arange('2001-01-10', '2001-03-04', dtype='datetime64[D]')
    locator = mdates.AutoDateLocator(interval_multiples=False)
    locator.intervald[3] = [2]
    locator.create_dummy_axis()
    locator.axis.set_view_interval(mdates.date2num(dates[0]),
                                   mdates.date2num(dates[-1]))
    with pytest.warns(UserWarning, match="AutoDateLocator was unable"):
        locs = locator()


def test_change_converter():
    plt.rcParams['date.converter'] = 'concise'
    dates = np.arange('2020-01-01', '2020-05-01', dtype='datetime64[D]')
    fig, ax = plt.subplots()

    ax.plot(dates, np.arange(len(dates)))
    fig.canvas.draw()
    assert ax.get_xticklabels()[0].get_text() == 'Jan'
    assert ax.get_xticklabels()[1].get_text() == '15'

    plt.rcParams['date.converter'] = 'auto'
    fig, ax = plt.subplots()

    ax.plot(dates, np.arange(len(dates)))
    fig.canvas.draw()
    assert ax.get_xticklabels()[0].get_text() == 'Jan 01 2020'
    assert ax.get_xticklabels()[1].get_text() == 'Jan 15 2020'
    with pytest.raises(ValueError):
        plt.rcParams['date.converter'] = 'boo'


def test_change_interval_multiples():
    plt.rcParams['date.interval_multiples'] = False
    dates = np.arange('2020-01-10', '2020-05-01', dtype='datetime64[D]')
    fig, ax = plt.subplots()

    ax.plot(dates, np.arange(len(dates)))
    fig.canvas.draw()
    assert ax.get_xticklabels()[0].get_text() == 'Jan 10 2020'
    assert ax.get_xticklabels()[1].get_text() == 'Jan 24 2020'

    plt.rcParams['date.interval_multiples'] = 'True'
    fig, ax = plt.subplots()

    ax.plot(dates, np.arange(len(dates)))
    fig.canvas.draw()
    assert ax.get_xticklabels()[0].get_text() == 'Jan 15 2020'
    assert ax.get_xticklabels()[1].get_text() == 'Feb 01 2020'


def test_DateLocator():
    locator = mdates.DateLocator()
    # Test nonsingular
    assert locator.nonsingular(0, np.inf) == (0, 1)
    assert locator.nonsingular(0, 1) == (0, 1)
    assert locator.nonsingular(1, 0) == (0, 1)
    assert locator.nonsingular(0, 0) == (-2, 2)
    locator.create_dummy_axis()
    # default values
    assert locator.datalim_to_dt() == (
        datetime.datetime(1970, 1, 1, 0, 0, tzinfo=datetime.timezone.utc),
        datetime.datetime(1970, 1, 2, 0, 0, tzinfo=datetime.timezone.utc))

    # Check default is UTC
    assert locator.tz == mdates.UTC
    tz_str = 'Iceland'
    iceland_tz = dateutil.tz.gettz(tz_str)
    # Check not Iceland
    assert locator.tz != iceland_tz
    # Set it to Iceland
    locator.set_tzinfo('Iceland')
    # Check now it is Iceland
    assert locator.tz == iceland_tz
    locator.create_dummy_axis()
    locator.axis.set_data_interval(*mdates.date2num(["2022-01-10",
                                                     "2022-01-08"]))
    assert locator.datalim_to_dt() == (
        datetime.datetime(2022, 1, 8, 0, 0, tzinfo=iceland_tz),
        datetime.datetime(2022, 1, 10, 0, 0, tzinfo=iceland_tz))

    # Set rcParam
    plt.rcParams['timezone'] = tz_str

    # Create a new one in a similar way
    locator = mdates.DateLocator()
    # Check now it is Iceland
    assert locator.tz == iceland_tz

    # Test invalid tz values
    with pytest.raises(ValueError, match="Aiceland is not a valid timezone"):
        mdates.DateLocator(tz="Aiceland")
    with pytest.raises(TypeError,
                       match="tz must be string or tzinfo subclass."):
        mdates.DateLocator(tz=1)


def test_datestr2num():
    assert mdates.datestr2num('2022-01-10') == 19002.0
    dt = datetime.date(year=2022, month=1, day=10)
    assert mdates.datestr2num('2022-01', default=dt) == 19002.0
    assert np.all(mdates.datestr2num(
        ['2022-01', '2022-02'], default=dt
        ) == np.array([19002., 19033.]))
    assert mdates.datestr2num([]).size == 0
    assert mdates.datestr2num([], datetime.date(year=2022,
                                                month=1, day=10)).size == 0


@pytest.mark.parametrize('kwarg',
                         ('formats', 'zero_formats', 'offset_formats'))
def test_concise_formatter_exceptions(kwarg):
    locator = mdates.AutoDateLocator()
    kwargs = {kwarg: ['', '%Y']}
    match = f"{kwarg} argument must be a list"
    with pytest.raises(ValueError, match=match):
        mdates.ConciseDateFormatter(locator, **kwargs)


def test_concise_formatter_call():
    locator = mdates.AutoDateLocator()
    formatter = mdates.ConciseDateFormatter(locator)
    assert formatter(19002.0) == '2022'
    assert formatter.format_data_short(19002.0) == '2022-01-10 00:00:00'


def test_datetime_masked():
    # make sure that all-masked data falls back to the viewlim
    # set in convert.axisinfo....
    x = np.array([datetime.datetime(2017, 1, n) for n in range(1, 6)])
    y = np.array([1, 2, 3, 4, 5])
    m = np.ma.masked_greater(y, 0)

    fig, ax = plt.subplots()
    ax.plot(x, m)
    assert ax.get_xlim() == (0, 1)


@pytest.mark.parametrize('val', (-1000000, 10000000))
def test_num2date_error(val):
    with pytest.raises(ValueError, match=f"Date ordinal {val} converts"):
        mdates.num2date(val)


def test_num2date_roundoff():
    assert mdates.num2date(100000.0000578702) == datetime.datetime(
        2243, 10, 17, 0, 0, 4, 999980, tzinfo=datetime.timezone.utc)
    # Slightly larger, steps of 20 microseconds
    assert mdates.num2date(100000.0000578703) == datetime.datetime(
        2243, 10, 17, 0, 0, 5, tzinfo=datetime.timezone.utc)


def test_DateFormatter_settz():
    time = mdates.date2num(datetime.datetime(2011, 1, 1, 0, 0,
                                             tzinfo=mdates.UTC))
    formatter = mdates.DateFormatter('%Y-%b-%d %H:%M')
    # Default UTC
    assert formatter(time) == '2011-Jan-01 00:00'

    # Set tzinfo
    formatter.set_tzinfo('Pacific/Kiritimati')
    assert formatter(time) == '2011-Jan-01 14:00'
