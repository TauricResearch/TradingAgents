"""
Tests specific to the bezier module.
"""

from matplotlib.bezier import inside_circle, split_bezier_intersecting_with_closedpath


def test_split_bezier_with_large_values():
    # These numbers come from gh-27753
    arrow_path = [(96950809781500.0, 804.7503795623779),
                  (96950809781500.0, 859.6242585800646),
                  (96950809781500.0, 914.4981375977513)]
    in_f = inside_circle(96950809781500.0, 804.7503795623779, 0.06)
    split_bezier_intersecting_with_closedpath(arrow_path, in_f)
    # All we are testing is that this completes
    # The failure case is an infinite loop resulting from floating point precision
    # pytest will timeout if that occurs
