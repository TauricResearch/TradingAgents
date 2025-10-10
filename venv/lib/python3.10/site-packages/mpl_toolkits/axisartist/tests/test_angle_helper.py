import re

import numpy as np
import pytest

from mpl_toolkits.axisartist.angle_helper import (
    FormatterDMS, FormatterHMS, select_step, select_step24, select_step360)


_MS_RE = (
    r'''\$  # Mathtext
        (
            # The sign sometimes appears on a 0 when a fraction is shown.
            # Check later that there's only one.
            (?P<degree_sign>-)?
            (?P<degree>[0-9.]+)  # Degrees value
            {degree}  # Degree symbol (to be replaced by format.)
        )?
        (
            (?(degree)\\,)  # Separator if degrees are also visible.
            (?P<minute_sign>-)?
            (?P<minute>[0-9.]+)  # Minutes value
            {minute}  # Minute symbol (to be replaced by format.)
        )?
        (
            (?(minute)\\,)  # Separator if minutes are also visible.
            (?P<second_sign>-)?
            (?P<second>[0-9.]+)  # Seconds value
            {second}  # Second symbol (to be replaced by format.)
        )?
        \$  # Mathtext
    '''
)
DMS_RE = re.compile(_MS_RE.format(degree=re.escape(FormatterDMS.deg_mark),
                                  minute=re.escape(FormatterDMS.min_mark),
                                  second=re.escape(FormatterDMS.sec_mark)),
                    re.VERBOSE)
HMS_RE = re.compile(_MS_RE.format(degree=re.escape(FormatterHMS.deg_mark),
                                  minute=re.escape(FormatterHMS.min_mark),
                                  second=re.escape(FormatterHMS.sec_mark)),
                    re.VERBOSE)


def dms2float(degrees, minutes=0, seconds=0):
    return degrees + minutes / 60.0 + seconds / 3600.0


@pytest.mark.parametrize('args, kwargs, expected_levels, expected_factor', [
    ((-180, 180, 10), {'hour': False}, np.arange(-180, 181, 30), 1.0),
    ((-12, 12, 10), {'hour': True}, np.arange(-12, 13, 2), 1.0)
])
def test_select_step(args, kwargs, expected_levels, expected_factor):
    levels, n, factor = select_step(*args, **kwargs)

    assert n == len(levels)
    np.testing.assert_array_equal(levels, expected_levels)
    assert factor == expected_factor


@pytest.mark.parametrize('args, kwargs, expected_levels, expected_factor', [
    ((-180, 180, 10), {}, np.arange(-180, 181, 30), 1.0),
    ((-12, 12, 10), {}, np.arange(-750, 751, 150), 60.0)
])
def test_select_step24(args, kwargs, expected_levels, expected_factor):
    levels, n, factor = select_step24(*args, **kwargs)

    assert n == len(levels)
    np.testing.assert_array_equal(levels, expected_levels)
    assert factor == expected_factor


@pytest.mark.parametrize('args, kwargs, expected_levels, expected_factor', [
    ((dms2float(20, 21.2), dms2float(21, 33.3), 5), {},
     np.arange(1215, 1306, 15), 60.0),
    ((dms2float(20.5, seconds=21.2), dms2float(20.5, seconds=33.3), 5), {},
     np.arange(73820, 73835, 2), 3600.0),
    ((dms2float(20, 21.2), dms2float(20, 53.3), 5), {},
     np.arange(1220, 1256, 5), 60.0),
    ((21.2, 33.3, 5), {},
     np.arange(20, 35, 2), 1.0),
    ((dms2float(20, 21.2), dms2float(21, 33.3), 5), {},
     np.arange(1215, 1306, 15), 60.0),
    ((dms2float(20.5, seconds=21.2), dms2float(20.5, seconds=33.3), 5), {},
     np.arange(73820, 73835, 2), 3600.0),
    ((dms2float(20.5, seconds=21.2), dms2float(20.5, seconds=21.4), 5), {},
     np.arange(7382120, 7382141, 5), 360000.0),
    # test threshold factor
    ((dms2float(20.5, seconds=11.2), dms2float(20.5, seconds=53.3), 5),
     {'threshold_factor': 60}, np.arange(12301, 12310), 600.0),
    ((dms2float(20.5, seconds=11.2), dms2float(20.5, seconds=53.3), 5),
     {'threshold_factor': 1}, np.arange(20502, 20517, 2), 1000.0),
])
def test_select_step360(args, kwargs, expected_levels, expected_factor):
    levels, n, factor = select_step360(*args, **kwargs)

    assert n == len(levels)
    np.testing.assert_array_equal(levels, expected_levels)
    assert factor == expected_factor


@pytest.mark.parametrize('Formatter, regex',
                         [(FormatterDMS, DMS_RE),
                          (FormatterHMS, HMS_RE)],
                         ids=['Degree/Minute/Second', 'Hour/Minute/Second'])
@pytest.mark.parametrize('direction, factor, values', [
    ("left", 60, [0, -30, -60]),
    ("left", 600, [12301, 12302, 12303]),
    ("left", 3600, [0, -30, -60]),
    ("left", 36000, [738210, 738215, 738220]),
    ("left", 360000, [7382120, 7382125, 7382130]),
    ("left", 1., [45, 46, 47]),
    ("left", 10., [452, 453, 454]),
])
def test_formatters(Formatter, regex, direction, factor, values):
    fmt = Formatter()
    result = fmt(direction, factor, values)

    prev_degree = prev_minute = prev_second = None
    for tick, value in zip(result, values):
        m = regex.match(tick)
        assert m is not None, f'{tick!r} is not an expected tick format.'

        sign = sum(m.group(sign + '_sign') is not None
                   for sign in ('degree', 'minute', 'second'))
        assert sign <= 1, f'Only one element of tick {tick!r} may have a sign.'
        sign = 1 if sign == 0 else -1

        degree = float(m.group('degree') or prev_degree or 0)
        minute = float(m.group('minute') or prev_minute or 0)
        second = float(m.group('second') or prev_second or 0)
        if Formatter == FormatterHMS:
            # 360 degrees as plot range -> 24 hours as labelled range
            expected_value = pytest.approx((value // 15) / factor)
        else:
            expected_value = pytest.approx(value / factor)
        assert sign * dms2float(degree, minute, second) == expected_value, \
            f'{tick!r} does not match expected tick value.'

        prev_degree = degree
        prev_minute = minute
        prev_second = second
