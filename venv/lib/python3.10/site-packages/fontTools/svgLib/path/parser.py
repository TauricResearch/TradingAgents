# SVG Path specification parser.
# This is an adaptation from 'svg.path' by Lennart Regebro (@regebro),
# modified so that the parser takes a FontTools Pen object instead of
# returning a list of svg.path Path objects.
# The original code can be found at:
# https://github.com/regebro/svg.path/blob/4f9b6e3/src/svg/path/parser.py
# Copyright (c) 2013-2014 Lennart Regebro
# License: MIT

from .arc import EllipticalArc
import re


COMMANDS = set("MmZzLlHhVvCcSsQqTtAa")
ARC_COMMANDS = set("Aa")
UPPERCASE = set("MZLHVCSQTA")

COMMAND_RE = re.compile("([MmZzLlHhVvCcSsQqTtAa])")

# https://www.w3.org/TR/css-syntax-3/#number-token-diagram
#   but -6.e-5 will be tokenized as "-6" then "-5" and confuse parsing
FLOAT_RE = re.compile(
    r"[-+]?"  # optional sign
    r"(?:"
    r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?"  # int/float
    r"|"
    r"(?:\.[0-9]+(?:[eE][-+]?[0-9]+)?)"  # float with leading dot (e.g. '.42')
    r")"
)
BOOL_RE = re.compile("^[01]")
SEPARATOR_RE = re.compile(f"[, \t]")


def _tokenize_path(pathdef):
    arc_cmd = None
    for x in COMMAND_RE.split(pathdef):
        if x in COMMANDS:
            arc_cmd = x if x in ARC_COMMANDS else None
            yield x
            continue

        if arc_cmd:
            try:
                yield from _tokenize_arc_arguments(x)
            except ValueError as e:
                raise ValueError(f"Invalid arc command: '{arc_cmd}{x}'") from e
        else:
            for token in FLOAT_RE.findall(x):
                yield token


ARC_ARGUMENT_TYPES = (
    ("rx", FLOAT_RE),
    ("ry", FLOAT_RE),
    ("x-axis-rotation", FLOAT_RE),
    ("large-arc-flag", BOOL_RE),
    ("sweep-flag", BOOL_RE),
    ("x", FLOAT_RE),
    ("y", FLOAT_RE),
)


def _tokenize_arc_arguments(arcdef):
    raw_args = [s for s in SEPARATOR_RE.split(arcdef) if s]
    if not raw_args:
        raise ValueError(f"Not enough arguments: '{arcdef}'")
    raw_args.reverse()

    i = 0
    while raw_args:
        arg = raw_args.pop()

        name, pattern = ARC_ARGUMENT_TYPES[i]
        match = pattern.search(arg)
        if not match:
            raise ValueError(f"Invalid argument for '{name}' parameter: {arg!r}")

        j, k = match.span()
        yield arg[j:k]
        arg = arg[k:]

        if arg:
            raw_args.append(arg)

        # wrap around every 7 consecutive arguments
        if i == 6:
            i = 0
        else:
            i += 1

    if i != 0:
        raise ValueError(f"Not enough arguments: '{arcdef}'")


def parse_path(pathdef, pen, current_pos=(0, 0), arc_class=EllipticalArc):
    """Parse SVG path definition (i.e. "d" attribute of <path> elements)
    and call a 'pen' object's moveTo, lineTo, curveTo, qCurveTo and closePath
    methods.

    If 'current_pos' (2-float tuple) is provided, the initial moveTo will
    be relative to that instead being absolute.

    If the pen has an "arcTo" method, it is called with the original values
    of the elliptical arc curve commands:

    .. code-block::

        pen.arcTo(rx, ry, rotation, arc_large, arc_sweep, (x, y))

    Otherwise, the arcs are approximated by series of cubic Bezier segments
    ("curveTo"), one every 90 degrees.
    """
    # In the SVG specs, initial movetos are absolute, even if
    # specified as 'm'. This is the default behavior here as well.
    # But if you pass in a current_pos variable, the initial moveto
    # will be relative to that current_pos. This is useful.
    current_pos = complex(*current_pos)

    elements = list(_tokenize_path(pathdef))
    # Reverse for easy use of .pop()
    elements.reverse()

    start_pos = None
    command = None
    last_control = None

    have_arcTo = hasattr(pen, "arcTo")

    while elements:
        if elements[-1] in COMMANDS:
            # New command.
            last_command = command  # Used by S and T
            command = elements.pop()
            absolute = command in UPPERCASE
            command = command.upper()
        else:
            # If this element starts with numbers, it is an implicit command
            # and we don't change the command. Check that it's allowed:
            if command is None:
                raise ValueError(
                    "Unallowed implicit command in %s, position %s"
                    % (pathdef, len(pathdef.split()) - len(elements))
                )
            last_command = command  # Used by S and T

        if command == "M":
            # Moveto command.
            x = elements.pop()
            y = elements.pop()
            pos = float(x) + float(y) * 1j
            if absolute:
                current_pos = pos
            else:
                current_pos += pos

            # M is not preceded by Z; it's an open subpath
            if start_pos is not None:
                pen.endPath()

            pen.moveTo((current_pos.real, current_pos.imag))

            # when M is called, reset start_pos
            # This behavior of Z is defined in svg spec:
            # http://www.w3.org/TR/SVG/paths.html#PathDataClosePathCommand
            start_pos = current_pos

            # Implicit moveto commands are treated as lineto commands.
            # So we set command to lineto here, in case there are
            # further implicit commands after this moveto.
            command = "L"

        elif command == "Z":
            # Close path
            if current_pos != start_pos:
                pen.lineTo((start_pos.real, start_pos.imag))
            pen.closePath()
            current_pos = start_pos
            start_pos = None
            command = None  # You can't have implicit commands after closing.

        elif command == "L":
            x = elements.pop()
            y = elements.pop()
            pos = float(x) + float(y) * 1j
            if not absolute:
                pos += current_pos
            pen.lineTo((pos.real, pos.imag))
            current_pos = pos

        elif command == "H":
            x = elements.pop()
            pos = float(x) + current_pos.imag * 1j
            if not absolute:
                pos += current_pos.real
            pen.lineTo((pos.real, pos.imag))
            current_pos = pos

        elif command == "V":
            y = elements.pop()
            pos = current_pos.real + float(y) * 1j
            if not absolute:
                pos += current_pos.imag * 1j
            pen.lineTo((pos.real, pos.imag))
            current_pos = pos

        elif command == "C":
            control1 = float(elements.pop()) + float(elements.pop()) * 1j
            control2 = float(elements.pop()) + float(elements.pop()) * 1j
            end = float(elements.pop()) + float(elements.pop()) * 1j

            if not absolute:
                control1 += current_pos
                control2 += current_pos
                end += current_pos

            pen.curveTo(
                (control1.real, control1.imag),
                (control2.real, control2.imag),
                (end.real, end.imag),
            )
            current_pos = end
            last_control = control2

        elif command == "S":
            # Smooth curve. First control point is the "reflection" of
            # the second control point in the previous path.

            if last_command not in "CS":
                # If there is no previous command or if the previous command
                # was not an C, c, S or s, assume the first control point is
                # coincident with the current point.
                control1 = current_pos
            else:
                # The first control point is assumed to be the reflection of
                # the second control point on the previous command relative
                # to the current point.
                control1 = current_pos + current_pos - last_control

            control2 = float(elements.pop()) + float(elements.pop()) * 1j
            end = float(elements.pop()) + float(elements.pop()) * 1j

            if not absolute:
                control2 += current_pos
                end += current_pos

            pen.curveTo(
                (control1.real, control1.imag),
                (control2.real, control2.imag),
                (end.real, end.imag),
            )
            current_pos = end
            last_control = control2

        elif command == "Q":
            control = float(elements.pop()) + float(elements.pop()) * 1j
            end = float(elements.pop()) + float(elements.pop()) * 1j

            if not absolute:
                control += current_pos
                end += current_pos

            pen.qCurveTo((control.real, control.imag), (end.real, end.imag))
            current_pos = end
            last_control = control

        elif command == "T":
            # Smooth curve. Control point is the "reflection" of
            # the second control point in the previous path.

            if last_command not in "QT":
                # If there is no previous command or if the previous command
                # was not an Q, q, T or t, assume the first control point is
                # coincident with the current point.
                control = current_pos
            else:
                # The control point is assumed to be the reflection of
                # the control point on the previous command relative
                # to the current point.
                control = current_pos + current_pos - last_control

            end = float(elements.pop()) + float(elements.pop()) * 1j

            if not absolute:
                end += current_pos

            pen.qCurveTo((control.real, control.imag), (end.real, end.imag))
            current_pos = end
            last_control = control

        elif command == "A":
            rx = abs(float(elements.pop()))
            ry = abs(float(elements.pop()))
            rotation = float(elements.pop())
            arc_large = bool(int(elements.pop()))
            arc_sweep = bool(int(elements.pop()))
            end = float(elements.pop()) + float(elements.pop()) * 1j

            if not absolute:
                end += current_pos

            # if the pen supports arcs, pass the values unchanged, otherwise
            # approximate the arc with a series of cubic bezier curves
            if have_arcTo:
                pen.arcTo(
                    rx,
                    ry,
                    rotation,
                    arc_large,
                    arc_sweep,
                    (end.real, end.imag),
                )
            else:
                arc = arc_class(
                    current_pos, rx, ry, rotation, arc_large, arc_sweep, end
                )
                arc.draw(pen)

            current_pos = end

    # no final Z command, it's an open path
    if start_pos is not None:
        pen.endPath()
