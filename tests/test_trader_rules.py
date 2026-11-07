"""Spec tests for trader.rules.

Every expected value is worked out by hand from the docstrings in trader/rules.py, the
constants in trader/settings.py and the written spec, never from the function bodies.
The constants appear as literals, so a change to one fails a test instead of being followed.
"""

import pytest

from trader.rules import (
    apply_caps,
    atr,
    drawdown,
    fee,
    funding_payment,
    initial_stop,
    monthly_cap,
    needs_trade,
    slipped,
    stop_after_trade,
    stop_fill,
    target_notional,
    tighten,
    to_quantity,
    unit_notional,
)

EQUITY = 10_000.0  # coin cap 10,000 and gross cap 20,000 in the apply_caps tests

# (contract_value, lot_size, min_size). MIN5 is made up, to tell the lot floor from the minimum.
SPECS = {"BTC": (0.01, 0.01, 0.01), "SOL": (1.0, 0.01, 0.01), "MIN5": (1.0, 1.0, 5.0)}


def _flat_bars(count):
    """High 11, low 9, close 10 for every bar: each true range is 2."""
    return [11.0] * count, [9.0] * count, [10.0] * count


# ------------------------------------------------------------------ atr


def test_atr_with_exactly_days_plus_one_bars_skips_the_first_bars_own_range():
    # Bar 0 only supplies the previous close; its own range (50) must not count.
    highs = [130.0, 105.0, 112.0, 108.0]
    lows = [80.0, 95.0, 100.0, 100.0]
    closes = [100.0, 100.0, 105.0, 104.0]
    # TR1 = max(105-95, |105-100|, |95-100|) = max(10, 5, 5) = 10
    # TR2 = max(112-100, |112-100|, |100-100|) = max(12, 12, 0) = 12
    # TR3 = max(108-100, |108-105|, |100-105|) = max(8, 3, 5) = 8; mean = 30 / 3 = 10
    assert atr(highs, lows, closes, days=3) == pytest.approx(10.0)


def test_atr_ignores_bars_older_than_the_window():
    # The same four bars as above, behind two older bars with wild values. Only the last
    # days + 1 = 4 bars may count, so the answer stays 10.
    highs = [900.0, 10.0, 130.0, 105.0, 112.0, 108.0]
    lows = [1.0, 5.0, 80.0, 95.0, 100.0, 100.0]
    closes = [500.0, 7.0, 100.0, 100.0, 105.0, 104.0]
    assert atr(highs, lows, closes, days=3) == pytest.approx(10.0)


def test_atr_window_is_fourteen_days_by_default():
    highs, lows, closes = _flat_bars(15)
    assert atr(highs, lows, closes) == pytest.approx(2.0)
    highs, lows, closes = _flat_bars(14)
    with pytest.raises(ValueError):
        atr(highs, lows, closes)


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_atr_with_fewer_than_days_plus_one_bars_raises(count):
    highs, lows, closes = _flat_bars(count)
    with pytest.raises(ValueError):
        atr(highs, lows, closes, days=3)


def test_atr_true_range_reaches_up_to_a_gap_above_the_previous_close():
    # prev close 100, then a bar of 110..125: max(15, |125-100|, |110-100|) = 25
    assert atr([105.0, 125.0], [95.0, 110.0], [100.0, 120.0], days=1) == pytest.approx(25.0)


def test_atr_true_range_reaches_down_to_a_gap_below_the_previous_close():
    # prev close 108, then a bar of 78..100: max(22, |100-108|, |78-108|) = 30
    assert atr([110.0, 100.0], [100.0, 78.0], [108.0, 90.0], days=1) == pytest.approx(30.0)


def test_atr_takes_the_largest_term_for_each_bar():
    highs = [101.0, 125.0, 118.0, 130.0]
    lows = [99.0, 110.0, 112.0, 100.0]
    closes = [100.0, 120.0, 115.0, 105.0]
    # TR1 = max(15, |125-100|, |110-100|) = 25  (gap up)
    # TR2 = max(6, |118-120|, |112-120|) = 8    (gap down)
    # TR3 = max(30, |130-115|, |100-115|) = 30  (own range); mean = 63 / 3 = 21
    assert atr(highs, lows, closes, days=3) == pytest.approx(21.0)


# ------------------------------------------------------------------ unit_notional


@pytest.mark.parametrize(
    ("equity", "atr_value", "price", "expected"),
    [
        (10_000.0, 2_000.0, 80_000.0, 3_200.0),  # the worked example: 0.02 * 10000 * 80000 / 5000
        (50_000.0, 150.0, 3_000.0, 8_000.0),  # 0.02 * 50000 * 3000 / 375
        (10_000.0, 6.0, 150.0, 2_000.0),  # 0.02 * 10000 * 150 / 15
    ],
)
def test_unit_notional(equity, atr_value, price, expected):
    assert unit_notional(equity, atr_value, price) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("equity", "atr_value", "price"),
    [(10_000.0, 2_000.0, 80_000.0), (50_000.0, 150.0, 3_000.0), (8_000.0, 7.5, 140.0)],
)
def test_unit_notional_loses_two_percent_of_equity_at_the_stop(equity, atr_value, price):
    unit = unit_notional(equity, atr_value, price)
    assert unit * 2.5 * atr_value / price == pytest.approx(0.02 * equity)


# ------------------------------------------------------------------ target_notional


@pytest.mark.parametrize(
    ("rating", "expected"),
    [("Buy", 3_200.0), ("Overweight", 1_600.0), ("Underweight", -800.0), ("Sell", -1_600.0)],
)
def test_target_notional_is_the_rating_weight_times_the_unit(rating, expected):
    # unit 3200: weights 1, 0.5, -0.25, -0.5; the current notional plays no part
    assert target_notional(rating, 3_200.0, 777.0) == pytest.approx(expected)


@pytest.mark.parametrize("rating", ["Hold", "REVIEW", None])
@pytest.mark.parametrize("current", [-1_234.5, 0.0, 987.6])
def test_target_notional_keeps_the_current_notional_without_an_actionable_rating(rating, current):
    assert target_notional(rating, 3_200.0, current) == pytest.approx(current)


# ------------------------------------------------------------------ apply_caps


def test_apply_caps_leaves_targets_inside_both_caps_alone():
    targets = {"BTC": 6_000.0, "ETH": -4_000.0, "SOL": 3_000.0}
    currents = {"BTC": 0.0, "ETH": 1_000.0, "SOL": 0.0}
    assert apply_caps(targets, currents, EQUITY) == pytest.approx(targets)


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (15_000.0, 10_000.0),  # long over the coin cap
        (10_001.0, 10_000.0),
        (10_000.0, 10_000.0),  # exactly at the cap
        (9_999.0, 9_999.0),
        (-9_999.0, -9_999.0),
        (-10_000.0, -10_000.0),
        (-10_001.0, -10_000.0),
        (-12_000.0, -10_000.0),  # short over the coin cap
    ],
)
def test_apply_caps_clamps_a_coin_to_one_times_equity(target, expected):
    assert apply_caps({"BTC": target}, {"BTC": 0.0}, EQUITY) == pytest.approx({"BTC": expected})


def test_apply_caps_does_not_clamp_a_target_equal_to_its_current_notional():
    assert apply_caps({"BTC": 13_000.0}, {"BTC": 13_000.0}, EQUITY) == pytest.approx(
        {"BTC": 13_000.0}
    )


def test_apply_caps_gross_exactly_at_the_cap_is_not_scaled():
    targets = {"BTC": 15_000.0, "ETH": -12_000.0}  # clamped to 10,000 and -10,000: gross 20,000
    expected = {"BTC": 10_000.0, "ETH": -10_000.0}
    assert apply_caps(targets, {"BTC": 0.0, "ETH": 0.0}, EQUITY) == pytest.approx(expected)


def test_apply_caps_scales_the_targets_by_one_common_factor_when_gross_exceeds_the_cap():
    targets = {"BTC": 9_000.0, "ETH": 9_000.0, "SOL": -6_000.0}  # gross 24,000: factor 5/6
    expected = {"BTC": 7_500.0, "ETH": 7_500.0, "SOL": -5_000.0}
    assert apply_caps(targets, dict.fromkeys(targets, 0.0), EQUITY) == pytest.approx(expected)


def test_apply_caps_clamps_each_coin_before_scaling_the_gross():
    targets = {"BTC": 40_000.0, "ETH": 7_500.0, "SOL": -7_500.0}
    # Clamped to 10,000 / 7,500 / -7,500: gross 25,000, factor 0.8. Scaling the raw targets
    # first and clamping after would leave ETH and SOL far smaller.
    expected = {"BTC": 8_000.0, "ETH": 6_000.0, "SOL": -6_000.0}
    assert apply_caps(targets, dict.fromkeys(targets, 0.0), EQUITY) == pytest.approx(expected)


def test_apply_caps_caps_scale_with_equity():
    targets = {"BTC": 4_000.0, "ETH": 3_000.0, "SOL": -1_250.0}
    # Equity 2,500: coin cap 2,500, gross cap 5,000. Clamped to 2,500 / 2,500 / -1,250,
    # gross 6,250, factor 0.8.
    expected = {"BTC": 2_000.0, "ETH": 2_000.0, "SOL": -1_000.0}
    assert apply_caps(targets, dict.fromkeys(targets, 0.0), 2_500.0) == pytest.approx(expected)


@pytest.mark.parametrize("held", [6_000.0, -6_000.0])
def test_apply_caps_scales_only_the_changing_targets_to_fit_around_a_held_position(held):
    targets = {"BTC": held, "ETH": 10_000.0, "SOL": -10_000.0}
    currents = {"BTC": held, "ETH": 0.0, "SOL": 0.0}
    # Held gross is |held| = 6,000, so the changing targets (gross 20,000) get the 14,000
    # of room that is left: factor 0.7. The held leg is untouched, long or short.
    expected = {"BTC": held, "ETH": 7_000.0, "SOL": -7_000.0}
    assert apply_caps(targets, currents, EQUITY) == pytest.approx(expected)


def test_apply_caps_counts_a_changing_target_not_its_current_toward_the_gross():
    targets = {"BTC": 6_000.0, "ETH": 10_000.0, "SOL": -10_000.0}
    currents = {"BTC": 6_000.0, "ETH": 3_000.0, "SOL": 2_000.0}
    expected = {"BTC": 6_000.0, "ETH": 7_000.0, "SOL": -7_000.0}  # same factor 0.7 as above
    assert apply_caps(targets, currents, EQUITY) == pytest.approx(expected)


@pytest.mark.parametrize("held_pair", [(12_000.0, -10_000.0), (10_000.0, -10_000.0)])
def test_apply_caps_zeroes_changing_targets_once_held_positions_fill_the_cap(held_pair):
    # Held gross is 22,000 (over the 20,000 cap) or exactly 20,000 (no room): either way
    # nothing is left for SOL, and the held legs stay as they are, even above the coin cap.
    btc, eth = held_pair
    targets = {"BTC": btc, "ETH": eth, "SOL": 5_000.0}
    currents = {"BTC": btc, "ETH": eth, "SOL": 0.0}
    expected = {"BTC": btc, "ETH": eth, "SOL": 0.0}
    assert apply_caps(targets, currents, EQUITY) == pytest.approx(expected)


def test_apply_caps_counts_a_key_missing_from_currents_as_zero():
    targets = {"BTC": 10_000.0, "ETH": 10_000.0, "SOL": 10_000.0}
    # BTC is held at 10,000, so ETH and SOL (missing, so changing from 0) share the 10,000
    # of room that is left: factor 0.5.
    expected = {"BTC": 10_000.0, "ETH": 5_000.0, "SOL": 5_000.0}
    assert apply_caps(targets, {"BTC": 10_000.0}, EQUITY) == pytest.approx(expected)


def test_apply_caps_clamps_a_target_whose_key_is_missing_from_currents():
    assert apply_caps({"ETH": 15_000.0}, {}, EQUITY) == pytest.approx({"ETH": 10_000.0})


def test_apply_caps_returns_the_keys_of_targets_only():
    targets = {"BTC": 3_000.0}
    currents = {"BTC": 0.0, "ETH": 2_000.0}
    assert apply_caps(targets, currents, EQUITY) == pytest.approx({"BTC": 3_000.0})


# ------------------------------------------------------------------ needs_trade


@pytest.mark.parametrize(
    ("target", "current", "unit", "expected"),
    [
        (600.0, 500.0, 1_000.0, True),  # difference exactly 0.1 unit
        (400.0, 500.0, 1_000.0, True),  # exactly 0.1 unit, the other way
        (599.0, 500.0, 1_000.0, False),  # just under
        (401.0, 500.0, 1_000.0, False),
        (500.0, 500.0, 1_000.0, False),
        (1_320.0, 1_000.0, 3_200.0, True),  # 320 = 0.1 * 3200
        (680.0, 1_000.0, 3_200.0, True),
        (1_319.0, 1_000.0, 3_200.0, False),
        (-100.0, 100.0, 1_000.0, True),  # crossing zero, a difference of 200
        (50.0, -50.0, 1_000.0, True),  # a difference of exactly 100
        (49.0, -50.0, 1_000.0, False),
    ],
)
def test_needs_trade_threshold_is_a_tenth_of_a_unit_inclusive(target, current, unit, expected):
    assert needs_trade(target, current, unit) is expected


# ------------------------------------------------------------------ to_quantity


@pytest.mark.parametrize(
    ("notional", "price", "spec", "expected"),
    [
        (5_600.0, 80_000.0, "BTC", 0.07),  # 0.07 BTC = 7 contracts = 700 lots
        (8_000.0, 80_000.0, "BTC", 0.1),
        (5_607.99, 80_000.0, "BTC", 0.07),  # 700.99875 lots: just under 701, floors to 700
        (5_608.0, 80_000.0, "BTC", 0.0701),  # exactly 701 lots
        (1_000.0, 150.0, "SOL", 6.66),  # 666.67 lots floors to 666
        (5.99, 100.0, "SOL", 0.05),  # 5.99 lots floors to 5
        (6.0, 100.0, "SOL", 0.06),  # exactly 6 lots
        (599.0, 100.0, "MIN5", 5.0),  # 5.99 contracts floors to 5, which meets the minimum
        (500.0, 100.0, "MIN5", 5.0),
        (0.0, 80_000.0, "BTC", 0.0),
    ],
)
def test_to_quantity_floors_to_whole_lots(notional, price, spec, expected):
    assert to_quantity(notional, price, *SPECS[spec]) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("notional", "price", "spec", "expected"),
    [
        (7.99, 80_000.0, "BTC", 0.0),  # 0.0099875 contracts: under one lot
        (8.0, 80_000.0, "BTC", 0.0001),  # exactly one lot, which meets the minimum
        (1.49, 150.0, "SOL", 0.0),
        (1.5, 150.0, "SOL", 0.01),
        (499.0, 100.0, "MIN5", 0.0),  # 4.99 contracts floors to 4, under the minimum of 5
    ],
)
def test_to_quantity_around_the_minimum_size(notional, price, spec, expected):
    assert to_quantity(notional, price, *SPECS[spec]) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("notional", "price", "spec", "expected"),
    [
        (-5_600.0, 80_000.0, "BTC", -0.07),
        (-5_607.99, 80_000.0, "BTC", -0.07),  # rounds toward zero, not to -0.0701
        (-1_000.0, 150.0, "SOL", -6.66),
        (-599.0, 100.0, "MIN5", -5.0),
        (-8.0, 80_000.0, "BTC", -0.0001),
        (-7.99, 80_000.0, "BTC", 0.0),  # under the minimum
        (-499.0, 100.0, "MIN5", 0.0),
    ],
)
def test_to_quantity_keeps_the_sign_and_rounds_toward_zero(notional, price, spec, expected):
    assert to_quantity(notional, price, *SPECS[spec]) == pytest.approx(expected)


# Each row is a clean decimal quantity that naive float arithmetic gets wrong: either the lot
# count comes out one short (4,200.7 / 60,010 / 0.01 / 0.01 lands just under 700), or the
# product keeps a stray digit (7 lots * 0.01 * 0.01 is 0.0007000000000000001).
NOISY = [
    (4_200.7, 60_010.0, "BTC", 0.07),  # a notional that should give exactly 0.07 BTC
    (232.0, 80_000.0, "BTC", 0.0029),
    (56.0, 80_000.0, "BTC", 0.0007),
    (456.0, 80_000.0, "BTC", 0.0057),
    (560.0, 80_000.0, "BTC", 0.007),
    (47.0, 100.0, "SOL", 0.47),
    (57.0, 100.0, "SOL", 0.57),
    (141.0, 150.0, "SOL", 0.94),
    (-4_200.7, 60_010.0, "BTC", -0.07),
]


@pytest.mark.parametrize(("notional", "price", "spec", "expected"), NOISY)
def test_to_quantity_does_not_lose_a_lot_to_float_noise(notional, price, spec, expected):
    assert to_quantity(notional, price, *SPECS[spec]) == pytest.approx(expected)


@pytest.mark.parametrize(("notional", "price", "spec", "expected"), NOISY)
def test_to_quantity_result_carries_no_float_noise(notional, price, spec, expected):
    # Exact equality on purpose: the docstring promises the result is rounded to remove float
    # noise, and pytest.approx would accept 0.0007000000000000001 for 0.0007.
    assert to_quantity(notional, price, *SPECS[spec]) == expected


# ------------------------------------------------------------------ stops


@pytest.mark.parametrize(
    ("entry", "qty", "atr_value", "expected"),
    [
        (80_000.0, 0.5, 2_000.0, 75_000.0),  # long: 80000 - 2.5 * 2000
        (80_000.0, 0.01, 2_000.0, 75_000.0),  # only the sign of qty matters
        (80_000.0, -0.5, 2_000.0, 85_000.0),  # short: 80000 + 2.5 * 2000
        (80_000.0, -0.01, 2_000.0, 85_000.0),
        (3_000.0, 2.0, 100.0, 2_750.0),
        (3_000.0, -2.0, 100.0, 3_250.0),
    ],
)
def test_initial_stop_is_two_and_a_half_atr_from_entry(entry, qty, atr_value, expected):
    assert initial_stop(entry, qty, atr_value) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("stop", "candidate", "qty", "expected"),
    [
        (75_000.0, 76_000.0, 0.5, 76_000.0),  # long: the higher stop is tighter
        (76_000.0, 75_000.0, 0.5, 76_000.0),
        (75_000.0, 75_000.0, 0.5, 75_000.0),
        (85_000.0, 84_000.0, -0.5, 84_000.0),  # short: the lower stop is tighter
        (84_000.0, 85_000.0, -0.5, 84_000.0),
        (85_000.0, 85_000.0, -0.5, 85_000.0),
    ],
)
def test_tighten_takes_the_higher_stop_for_a_long_and_the_lower_for_a_short(
    stop, candidate, qty, expected
):
    assert tighten(stop, candidate, qty) == pytest.approx(expected)


# stop_after_trade fills at 80,000 with ATR 2,000: the fresh stop is 75,000 for a long and
# 85,000 for a short.
@pytest.mark.parametrize(
    ("old_qty", "new_qty", "old_stop", "expected"),
    [
        (0.0, 0.5, None, 75_000.0),  # opens a long
        (0.0, -0.5, None, 85_000.0),  # opens a short
        (0.5, -0.3, 79_000.0, 85_000.0),  # long flips to a smaller short: fresh, not 79,000
        (0.5, -0.8, 79_000.0, 85_000.0),  # long flips to a larger short
        (-0.5, 0.3, 81_000.0, 75_000.0),  # short flips to a smaller long: fresh, not 81,000
        (-0.5, 0.8, 81_000.0, 75_000.0),  # short flips to a larger long
        (0.5, 0.8, 72_000.0, 75_000.0),  # long adds, fresh is tighter (higher)
        (0.5, 0.8, 77_000.0, 77_000.0),  # long adds, old is tighter
        (-0.5, -0.8, 88_000.0, 85_000.0),  # short adds, fresh is tighter (lower)
        (-0.5, -0.8, 83_000.0, 83_000.0),  # short adds, old is tighter
        (0.5, 0.3, 72_000.0, 72_000.0),  # long reduces, old stop kept though fresh is tighter
        (0.5, 0.3, 77_000.0, 77_000.0),  # long reduces, old stop kept
        (-0.5, -0.3, 88_000.0, 88_000.0),  # short reduces, old stop kept though fresh is tighter
        (-0.5, -0.3, 83_000.0, 83_000.0),  # short reduces, old stop kept
    ],
)
def test_stop_after_trade_for_a_position_that_remains(old_qty, new_qty, old_stop, expected):
    assert stop_after_trade(old_qty, new_qty, old_stop, 80_000.0, 2_000.0) == pytest.approx(
        expected
    )


@pytest.mark.parametrize(("old_qty", "old_stop"), [(0.5, 72_000.0), (-0.5, 88_000.0), (0.0, None)])
def test_stop_after_trade_is_none_when_the_trade_leaves_the_position_flat(old_qty, old_stop):
    assert stop_after_trade(old_qty, 0.0, old_stop, 80_000.0, 2_000.0) is None


# ------------------------------------------------------------------ stop_fill


@pytest.mark.parametrize(
    ("qty", "stop", "bar_open", "bar_high", "bar_low", "expected"),
    [
        # Long, stop 75,000: it fills at the open on a gap, else at the stop once the low hits it.
        (0.5, 75_000.0, 74_000.0, 76_000.0, 73_000.0, 74_000.0),  # gap through the stop
        (0.5, 75_000.0, 75_000.0, 76_000.0, 74_000.0, 75_000.0),  # opens on the stop
        (0.5, 75_000.0, 78_000.0, 79_000.0, 75_000.0, 75_000.0),  # low touches the stop
        (0.5, 75_000.0, 78_000.0, 79_000.0, 72_000.0, 75_000.0),  # low crosses the stop
        # Short, stop 85,000: the mirror image, with the open and the high.
        (-0.5, 85_000.0, 86_000.0, 87_000.0, 84_000.0, 86_000.0),  # gap through the stop
        (-0.5, 85_000.0, 85_000.0, 86_000.0, 84_000.0, 85_000.0),  # opens on the stop
        (-0.5, 85_000.0, 82_000.0, 85_000.0, 81_000.0, 85_000.0),  # high touches the stop
        (-0.5, 85_000.0, 82_000.0, 88_000.0, 81_000.0, 85_000.0),  # high crosses the stop
    ],
)
def test_stop_fill_fills_at_the_open_on_a_gap_else_at_the_stop(
    qty, stop, bar_open, bar_high, bar_low, expected
):
    fill = stop_fill(qty, stop, bar_open, bar_high, bar_low)
    assert fill == pytest.approx(expected)


@pytest.mark.parametrize(
    ("qty", "stop", "bar_open", "bar_high", "bar_low"),
    [
        (0.5, 75_000.0, 78_000.0, 79_000.0, 75_001.0),  # low stops just above a long's stop
        (0.5, 75_000.0, 78_000.0, 95_000.0, 76_000.0),  # a long ignores how high the bar goes
        (-0.5, 85_000.0, 82_000.0, 84_999.0, 81_000.0),  # high stops just below a short's stop
        (-0.5, 85_000.0, 82_000.0, 83_000.0, 60_000.0),  # a short ignores how low the bar goes
    ],
)
def test_stop_fill_is_none_when_the_bar_misses_the_stop(qty, stop, bar_open, bar_high, bar_low):
    assert stop_fill(qty, stop, bar_open, bar_high, bar_low) is None


# ------------------------------------------------------------------ costs


@pytest.mark.parametrize(
    ("side", "price", "expected"),
    [
        (1.0, 80_000.0, 80_040.0),  # buying pays 0.05% more
        (-1.0, 80_000.0, 79_960.0),  # selling gets 0.05% less
        (1.0, 150.0, 150.075),
        (-1.0, 150.0, 149.925),
        (0.25, 80_000.0, 80_040.0),  # only the sign of side matters
        (-7.0, 80_000.0, 79_960.0),
    ],
)
def test_slipped_moves_the_price_against_the_trader(side, price, expected):
    assert slipped(price, side) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("notional", "expected"),
    [(10_000.0, 5.0), (-10_000.0, 5.0), (3_200.0, 1.6), (0.0, 0.0)],  # 0.05% of |notional|
)
def test_fee_is_five_basis_points_of_the_absolute_notional(notional, expected):
    assert fee(notional) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("qty", "price", "rate", "expected"),
    [
        (0.1, 80_000.0, 0.0001, -0.8),  # a long pays when the rate is positive
        (-0.1, 80_000.0, 0.0001, 0.8),  # and the short on the other side receives
        (0.1, 80_000.0, -0.0001, 0.8),  # a negative rate reverses who pays
        (-0.1, 80_000.0, -0.0001, -0.8),
        (2.0, 3_000.0, 0.0005, -3.0),
        (0.1, 80_000.0, 0.0, 0.0),
        (0.0, 80_000.0, 0.0001, 0.0),
    ],
)
def test_funding_payment_is_minus_qty_times_price_times_rate(qty, price, rate, expected):
    assert funding_payment(qty, price, rate) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("equity", "peak", "expected"),
    [
        (8_000.0, 10_000.0, 0.2),
        (9_500.0, 10_000.0, 0.05),
        (7_500.0, 12_000.0, 0.375),
        (0.0, 10_000.0, 1.0),
        (10_000.0, 10_000.0, 0.0),  # at the peak
        (11_000.0, 10_000.0, 0.0),  # above it
    ],
)
def test_drawdown_is_the_fraction_below_the_peak_and_never_negative(equity, peak, expected):
    assert drawdown(equity, peak) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("daily_costs", "expected"),
    [
        ([1.0, 2.0, 3.0], 90.0),  # mean 2 * 30 * 1.5
        ([4.0], 180.0),
        ([0.5, 1.5, 1.0, 3.0], 67.5),  # mean 1.5
        ([1.0, 1.0, 10.0], 180.0),  # mean 4: the mean, not the median (1)
    ],
)
def test_monthly_cap_is_the_mean_daily_cost_times_thirty_times_headroom(daily_costs, expected):
    assert monthly_cap(daily_costs) == pytest.approx(expected)


# ------------------------------------------------------------------ another account's constants
#
# The keyword-only parameters let a second account (the intraday one) size and stop with
# its own constants. Passing the daily constants explicitly gives the defaults' answers.


def test_unit_notional_with_custom_risk_and_stop_multiple():
    # 0.01 * 10000 * 80000 / (2.0 * 400) = 10,000; the defaults would give 3,200 at ATR 2,000
    assert unit_notional(10_000.0, 400.0, 80_000.0, risk=0.01, stop_mult=2.0) == pytest.approx(
        10_000.0
    )
    assert unit_notional(10_000.0, 2_000.0, 80_000.0, risk=0.02, stop_mult=2.5) == unit_notional(
        10_000.0, 2_000.0, 80_000.0
    )


def test_target_notional_with_custom_weights():
    weights = {"Long": 1.0, "Short": -1.0, "Flat": 0.0}
    assert target_notional("Long", 3_200.0, 777.0, weights=weights) == pytest.approx(3_200.0)
    assert target_notional("Short", 3_200.0, 777.0, weights=weights) == pytest.approx(-3_200.0)
    assert target_notional("Flat", 3_200.0, 777.0, weights=weights) == pytest.approx(0.0)
    # A signal missing from the custom weights keeps the current notional, Buy included.
    assert target_notional("Buy", 3_200.0, 777.0, weights=weights) == pytest.approx(777.0)
    assert target_notional(None, 3_200.0, 777.0, weights=weights) == pytest.approx(777.0)
    assert target_notional("Sell", 3_200.0, 777.0, weights={"Sell": -0.5}) == pytest.approx(
        target_notional("Sell", 3_200.0, 777.0)
    )


@pytest.mark.parametrize(
    ("target", "current", "unit", "expected"),
    [
        (750.0, 500.0, 1_000.0, True),  # exactly 0.25 unit
        (749.0, 500.0, 1_000.0, False),  # just under: the default 0.1 would trade
        (250.0, 500.0, 1_000.0, True),
        (600.0, 500.0, 1_000.0, False),  # 0.1 unit is a trade by default, not at 0.25
    ],
)
def test_needs_trade_with_a_custom_threshold(target, current, unit, expected):
    assert needs_trade(target, current, unit, threshold=0.25) is expected
    assert needs_trade(target, current, unit, threshold=0.1) is needs_trade(target, current, unit)


@pytest.mark.parametrize(
    ("qty", "stop_mult", "expected"),
    [
        (0.5, 2.0, 76_000.0),  # long: 80000 - 2.0 * 2000
        (-0.5, 2.0, 84_000.0),  # short: 80000 + 2.0 * 2000
        (0.5, 3.0, 74_000.0),
        (-0.5, 3.0, 86_000.0),
    ],
)
def test_initial_stop_with_a_custom_multiple(qty, stop_mult, expected):
    assert initial_stop(80_000.0, qty, 2_000.0, stop_mult=stop_mult) == pytest.approx(expected)
    assert initial_stop(80_000.0, qty, 2_000.0, stop_mult=2.5) == initial_stop(
        80_000.0, qty, 2_000.0
    )


@pytest.mark.parametrize(
    ("old_qty", "new_qty", "old_stop", "expected"),
    [
        (0.0, 0.5, None, 76_000.0),  # opens a long: fresh stop 2.0 ATR below the fill
        (0.0, -0.5, None, 84_000.0),  # opens a short
        (0.5, -0.3, 79_000.0, 84_000.0),  # flips: fresh
        (0.5, 0.8, 75_000.0, 76_000.0),  # adds, fresh (76,000) is tighter than the old
        (0.5, 0.8, 77_000.0, 77_000.0),  # adds, old is tighter
        (0.5, 0.3, 72_000.0, 72_000.0),  # reduces: old stop kept
    ],
)
def test_stop_after_trade_passes_the_multiple_to_the_fresh_stop(
    old_qty, new_qty, old_stop, expected
):
    assert stop_after_trade(
        old_qty, new_qty, old_stop, 80_000.0, 2_000.0, stop_mult=2.0
    ) == pytest.approx(expected)
    assert stop_after_trade(old_qty, new_qty, old_stop, 80_000.0, 2_000.0, stop_mult=2.5) == (
        stop_after_trade(old_qty, new_qty, old_stop, 80_000.0, 2_000.0)
    )
    assert stop_after_trade(old_qty, 0.0, old_stop, 80_000.0, 2_000.0, stop_mult=2.0) is None
