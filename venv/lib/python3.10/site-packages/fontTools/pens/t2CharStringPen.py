# Copyright (c) 2009 Type Supply LLC
# Author: Tal Leming

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from fontTools.cffLib.specializer import commandsToProgram, specializeCommands
from fontTools.misc.psCharStrings import T2CharString
from fontTools.misc.roundTools import otRound, roundFunc
from fontTools.pens.basePen import BasePen


class T2CharStringPen(BasePen):
    """Pen to draw Type 2 CharStrings.

    The 'roundTolerance' argument controls the rounding of point coordinates.
    It is defined as the maximum absolute difference between the original
    float and the rounded integer value.
    The default tolerance of 0.5 means that all floats are rounded to integer;
    a value of 0 disables rounding; values in between will only round floats
    which are close to their integral part within the tolerated range.
    """

    def __init__(
        self,
        width: float | None,
        glyphSet: Dict[str, Any] | None,
        roundTolerance: float = 0.5,
        CFF2: bool = False,
    ) -> None:
        super(T2CharStringPen, self).__init__(glyphSet)
        self.round = roundFunc(roundTolerance)
        self._CFF2 = CFF2
        self._width = width
        self._commands: List[Tuple[str | bytes, List[float]]] = []
        self._p0 = (0, 0)

    def _p(self, pt: Tuple[float, float]) -> List[float]:
        p0 = self._p0
        pt = self._p0 = (self.round(pt[0]), self.round(pt[1]))
        return [pt[0] - p0[0], pt[1] - p0[1]]

    def _moveTo(self, pt: Tuple[float, float]) -> None:
        self._commands.append(("rmoveto", self._p(pt)))

    def _lineTo(self, pt: Tuple[float, float]) -> None:
        self._commands.append(("rlineto", self._p(pt)))

    def _curveToOne(
        self,
        pt1: Tuple[float, float],
        pt2: Tuple[float, float],
        pt3: Tuple[float, float],
    ) -> None:
        _p = self._p
        self._commands.append(("rrcurveto", _p(pt1) + _p(pt2) + _p(pt3)))

    def _closePath(self) -> None:
        pass

    def _endPath(self) -> None:
        pass

    def getCharString(
        self,
        private: Dict | None = None,
        globalSubrs: List | None = None,
        optimize: bool = True,
    ) -> T2CharString:
        commands = self._commands
        if optimize:
            maxstack = 48 if not self._CFF2 else 513
            commands = specializeCommands(
                commands, generalizeFirst=False, maxstack=maxstack
            )
        program = commandsToProgram(commands)
        if self._width is not None:
            assert (
                not self._CFF2
            ), "CFF2 does not allow encoding glyph width in CharString."
            program.insert(0, otRound(self._width))
        if not self._CFF2:
            program.append("endchar")
        charString = T2CharString(
            program=program, private=private, globalSubrs=globalSubrs
        )
        return charString
