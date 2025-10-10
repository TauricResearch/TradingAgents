from .interpolatableHelpers import *
import logging

log = logging.getLogger("fontTools.varLib.interpolatable")


def test_contour_order(glyph0, glyph1):
    # We try matching both the StatisticsControlPen vector
    # and the StatisticsPen vector.
    #
    # If either method found a identity matching, accept it.
    # This is crucial for fonts like Kablammo[MORF].ttf and
    # Nabla[EDPT,EHLT].ttf, since they really confuse the
    # StatisticsPen vector because of their area=0 contours.

    n = len(glyph0.controlVectors)
    matching = None
    matching_cost = 0
    identity_cost = 0
    done = n <= 1
    if not done:
        m0Control = glyph0.controlVectors
        m1Control = glyph1.controlVectors
        (
            matching_control,
            matching_cost_control,
            identity_cost_control,
        ) = matching_for_vectors(m0Control, m1Control)
        done = matching_cost_control == identity_cost_control
    if not done:
        m0Green = glyph0.greenVectors
        m1Green = glyph1.greenVectors
        (
            matching_green,
            matching_cost_green,
            identity_cost_green,
        ) = matching_for_vectors(m0Green, m1Green)
        done = matching_cost_green == identity_cost_green

    if not done:
        # See if reversing contours in one master helps.
        # That's a common problem.  Then the wrong_start_point
        # test will fix them.
        #
        # Reverse the sign of the area (0); the rest stay the same.
        if not done:
            m1ControlReversed = [(-m[0],) + m[1:] for m in m1Control]
            (
                matching_control_reversed,
                matching_cost_control_reversed,
                identity_cost_control_reversed,
            ) = matching_for_vectors(m0Control, m1ControlReversed)
            done = matching_cost_control_reversed == identity_cost_control_reversed
        if not done:
            m1GreenReversed = [(-m[0],) + m[1:] for m in m1Green]
            (
                matching_control_reversed,
                matching_cost_green_reversed,
                identity_cost_green_reversed,
            ) = matching_for_vectors(m0Green, m1GreenReversed)
            done = matching_cost_green_reversed == identity_cost_green_reversed

        if not done:
            # Otherwise, use the worst of the two matchings.
            if (
                matching_cost_control / identity_cost_control
                < matching_cost_green / identity_cost_green
            ):
                matching = matching_control
                matching_cost = matching_cost_control
                identity_cost = identity_cost_control
            else:
                matching = matching_green
                matching_cost = matching_cost_green
                identity_cost = identity_cost_green

    this_tolerance = matching_cost / identity_cost if identity_cost else 1
    log.debug(
        "test-contour-order: tolerance %g",
        this_tolerance,
    )
    return this_tolerance, matching
