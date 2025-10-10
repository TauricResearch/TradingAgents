from fontTools.pens.basePen import BasePen, OpenContourError

try:
    import cython
except (AttributeError, ImportError):
    # if cython not installed, use mock module with no-op decorators and types
    from fontTools.misc import cython
COMPILED = cython.compiled


__all__ = ["MomentsPen"]


class MomentsPen(BasePen):

    def __init__(self, glyphset=None):
        BasePen.__init__(self, glyphset)

        self.area = 0
        self.momentX = 0
        self.momentY = 0
        self.momentXX = 0
        self.momentXY = 0
        self.momentYY = 0

    def _moveTo(self, p0):
        self._startPoint = p0

    def _closePath(self):
        p0 = self._getCurrentPoint()
        if p0 != self._startPoint:
            self._lineTo(self._startPoint)

    def _endPath(self):
        p0 = self._getCurrentPoint()
        if p0 != self._startPoint:
            raise OpenContourError("Glyph statistics is not defined on open contours.")

    @cython.locals(r0=cython.double)
    @cython.locals(r1=cython.double)
    @cython.locals(r2=cython.double)
    @cython.locals(r3=cython.double)
    @cython.locals(r4=cython.double)
    @cython.locals(r5=cython.double)
    @cython.locals(r6=cython.double)
    @cython.locals(r7=cython.double)
    @cython.locals(r8=cython.double)
    @cython.locals(r9=cython.double)
    @cython.locals(r10=cython.double)
    @cython.locals(r11=cython.double)
    @cython.locals(r12=cython.double)
    @cython.locals(x0=cython.double, y0=cython.double)
    @cython.locals(x1=cython.double, y1=cython.double)
    def _lineTo(self, p1):
        x0, y0 = self._getCurrentPoint()
        x1, y1 = p1

        r0 = x1 * y0
        r1 = x1 * y1
        r2 = x1**2
        r3 = r2 * y1
        r4 = y0 - y1
        r5 = r4 * x0
        r6 = x0**2
        r7 = 2 * y0
        r8 = y0**2
        r9 = y1**2
        r10 = x1**3
        r11 = y0**3
        r12 = y1**3

        self.area += -r0 / 2 - r1 / 2 + x0 * (y0 + y1) / 2
        self.momentX += -r2 * y0 / 6 - r3 / 3 - r5 * x1 / 6 + r6 * (r7 + y1) / 6
        self.momentY += (
            -r0 * y1 / 6 - r8 * x1 / 6 - r9 * x1 / 6 + x0 * (r8 + r9 + y0 * y1) / 6
        )
        self.momentXX += (
            -r10 * y0 / 12
            - r10 * y1 / 4
            - r2 * r5 / 12
            - r4 * r6 * x1 / 12
            + x0**3 * (3 * y0 + y1) / 12
        )
        self.momentXY += (
            -r2 * r8 / 24
            - r2 * r9 / 8
            - r3 * r7 / 24
            + r6 * (r7 * y1 + 3 * r8 + r9) / 24
            - x0 * x1 * (r8 - r9) / 12
        )
        self.momentYY += (
            -r0 * r9 / 12
            - r1 * r8 / 12
            - r11 * x1 / 12
            - r12 * x1 / 12
            + x0 * (r11 + r12 + r8 * y1 + r9 * y0) / 12
        )

    @cython.locals(r0=cython.double)
    @cython.locals(r1=cython.double)
    @cython.locals(r2=cython.double)
    @cython.locals(r3=cython.double)
    @cython.locals(r4=cython.double)
    @cython.locals(r5=cython.double)
    @cython.locals(r6=cython.double)
    @cython.locals(r7=cython.double)
    @cython.locals(r8=cython.double)
    @cython.locals(r9=cython.double)
    @cython.locals(r10=cython.double)
    @cython.locals(r11=cython.double)
    @cython.locals(r12=cython.double)
    @cython.locals(r13=cython.double)
    @cython.locals(r14=cython.double)
    @cython.locals(r15=cython.double)
    @cython.locals(r16=cython.double)
    @cython.locals(r17=cython.double)
    @cython.locals(r18=cython.double)
    @cython.locals(r19=cython.double)
    @cython.locals(r20=cython.double)
    @cython.locals(r21=cython.double)
    @cython.locals(r22=cython.double)
    @cython.locals(r23=cython.double)
    @cython.locals(r24=cython.double)
    @cython.locals(r25=cython.double)
    @cython.locals(r26=cython.double)
    @cython.locals(r27=cython.double)
    @cython.locals(r28=cython.double)
    @cython.locals(r29=cython.double)
    @cython.locals(r30=cython.double)
    @cython.locals(r31=cython.double)
    @cython.locals(r32=cython.double)
    @cython.locals(r33=cython.double)
    @cython.locals(r34=cython.double)
    @cython.locals(r35=cython.double)
    @cython.locals(r36=cython.double)
    @cython.locals(r37=cython.double)
    @cython.locals(r38=cython.double)
    @cython.locals(r39=cython.double)
    @cython.locals(r40=cython.double)
    @cython.locals(r41=cython.double)
    @cython.locals(r42=cython.double)
    @cython.locals(r43=cython.double)
    @cython.locals(r44=cython.double)
    @cython.locals(r45=cython.double)
    @cython.locals(r46=cython.double)
    @cython.locals(r47=cython.double)
    @cython.locals(r48=cython.double)
    @cython.locals(r49=cython.double)
    @cython.locals(r50=cython.double)
    @cython.locals(r51=cython.double)
    @cython.locals(r52=cython.double)
    @cython.locals(r53=cython.double)
    @cython.locals(x0=cython.double, y0=cython.double)
    @cython.locals(x1=cython.double, y1=cython.double)
    @cython.locals(x2=cython.double, y2=cython.double)
    def _qCurveToOne(self, p1, p2):
        x0, y0 = self._getCurrentPoint()
        x1, y1 = p1
        x2, y2 = p2

        r0 = 2 * y1
        r1 = r0 * x2
        r2 = x2 * y2
        r3 = 3 * r2
        r4 = 2 * x1
        r5 = 3 * y0
        r6 = x1**2
        r7 = x2**2
        r8 = 4 * y1
        r9 = 10 * y2
        r10 = 2 * y2
        r11 = r4 * x2
        r12 = x0**2
        r13 = 10 * y0
        r14 = r4 * y2
        r15 = x2 * y0
        r16 = 4 * x1
        r17 = r0 * x1 + r2
        r18 = r2 * r8
        r19 = y1**2
        r20 = 2 * r19
        r21 = y2**2
        r22 = r21 * x2
        r23 = 5 * r22
        r24 = y0**2
        r25 = y0 * y2
        r26 = 5 * r24
        r27 = x1**3
        r28 = x2**3
        r29 = 30 * y1
        r30 = 6 * y1
        r31 = 10 * r7 * x1
        r32 = 5 * y2
        r33 = 12 * r6
        r34 = 30 * x1
        r35 = x1 * y1
        r36 = r3 + 20 * r35
        r37 = 12 * x1
        r38 = 20 * r6
        r39 = 8 * r6 * y1
        r40 = r32 * r7
        r41 = 60 * y1
        r42 = 20 * r19
        r43 = 4 * r19
        r44 = 15 * r21
        r45 = 12 * x2
        r46 = 12 * y2
        r47 = 6 * x1
        r48 = 8 * r19 * x1 + r23
        r49 = 8 * y1**3
        r50 = y2**3
        r51 = y0**3
        r52 = 10 * y1
        r53 = 12 * y1

        self.area += (
            -r1 / 6
            - r3 / 6
            + x0 * (r0 + r5 + y2) / 6
            + x1 * y2 / 3
            - y0 * (r4 + x2) / 6
        )
        self.momentX += (
            -r11 * (-r10 + y1) / 30
            + r12 * (r13 + r8 + y2) / 30
            + r6 * y2 / 15
            - r7 * r8 / 30
            - r7 * r9 / 30
            + x0 * (r14 - r15 - r16 * y0 + r17) / 30
            - y0 * (r11 + 2 * r6 + r7) / 30
        )
        self.momentY += (
            -r18 / 30
            - r20 * x2 / 30
            - r23 / 30
            - r24 * (r16 + x2) / 30
            + x0 * (r0 * y2 + r20 + r21 + r25 + r26 + r8 * y0) / 30
            + x1 * y2 * (r10 + y1) / 15
            - y0 * (r1 + r17) / 30
        )
        self.momentXX += (
            r12 * (r1 - 5 * r15 - r34 * y0 + r36 + r9 * x1) / 420
            + 2 * r27 * y2 / 105
            - r28 * r29 / 420
            - r28 * y2 / 4
            - r31 * (r0 - 3 * y2) / 420
            - r6 * x2 * (r0 - r32) / 105
            + x0**3 * (r30 + 21 * y0 + y2) / 84
            - x0
            * (
                r0 * r7
                + r15 * r37
                - r2 * r37
                - r33 * y2
                + r38 * y0
                - r39
                - r40
                + r5 * r7
            )
            / 420
            - y0 * (8 * r27 + 5 * r28 + r31 + r33 * x2) / 420
        )
        self.momentXY += (
            r12 * (r13 * y2 + 3 * r21 + 105 * r24 + r41 * y0 + r42 + r46 * y1) / 840
            - r16 * x2 * (r43 - r44) / 840
            - r21 * r7 / 8
            - r24 * (r38 + r45 * x1 + 3 * r7) / 840
            - r41 * r7 * y2 / 840
            - r42 * r7 / 840
            + r6 * y2 * (r32 + r8) / 210
            + x0
            * (
                -r15 * r8
                + r16 * r25
                + r18
                + r21 * r47
                - r24 * r34
                - r26 * x2
                + r35 * r46
                + r48
            )
            / 420
            - y0 * (r16 * r2 + r30 * r7 + r35 * r45 + r39 + r40) / 420
        )
        self.momentYY += (
            -r2 * r42 / 420
            - r22 * r29 / 420
            - r24 * (r14 + r36 + r52 * x2) / 420
            - r49 * x2 / 420
            - r50 * x2 / 12
            - r51 * (r47 + x2) / 84
            + x0
            * (
                r19 * r46
                + r21 * r5
                + r21 * r52
                + r24 * r29
                + r25 * r53
                + r26 * y2
                + r42 * y0
                + r49
                + 5 * r50
                + 35 * r51
            )
            / 420
            + x1 * y2 * (r43 + r44 + r9 * y1) / 210
            - y0 * (r19 * r45 + r2 * r53 - r21 * r4 + r48) / 420
        )

    @cython.locals(r0=cython.double)
    @cython.locals(r1=cython.double)
    @cython.locals(r2=cython.double)
    @cython.locals(r3=cython.double)
    @cython.locals(r4=cython.double)
    @cython.locals(r5=cython.double)
    @cython.locals(r6=cython.double)
    @cython.locals(r7=cython.double)
    @cython.locals(r8=cython.double)
    @cython.locals(r9=cython.double)
    @cython.locals(r10=cython.double)
    @cython.locals(r11=cython.double)
    @cython.locals(r12=cython.double)
    @cython.locals(r13=cython.double)
    @cython.locals(r14=cython.double)
    @cython.locals(r15=cython.double)
    @cython.locals(r16=cython.double)
    @cython.locals(r17=cython.double)
    @cython.locals(r18=cython.double)
    @cython.locals(r19=cython.double)
    @cython.locals(r20=cython.double)
    @cython.locals(r21=cython.double)
    @cython.locals(r22=cython.double)
    @cython.locals(r23=cython.double)
    @cython.locals(r24=cython.double)
    @cython.locals(r25=cython.double)
    @cython.locals(r26=cython.double)
    @cython.locals(r27=cython.double)
    @cython.locals(r28=cython.double)
    @cython.locals(r29=cython.double)
    @cython.locals(r30=cython.double)
    @cython.locals(r31=cython.double)
    @cython.locals(r32=cython.double)
    @cython.locals(r33=cython.double)
    @cython.locals(r34=cython.double)
    @cython.locals(r35=cython.double)
    @cython.locals(r36=cython.double)
    @cython.locals(r37=cython.double)
    @cython.locals(r38=cython.double)
    @cython.locals(r39=cython.double)
    @cython.locals(r40=cython.double)
    @cython.locals(r41=cython.double)
    @cython.locals(r42=cython.double)
    @cython.locals(r43=cython.double)
    @cython.locals(r44=cython.double)
    @cython.locals(r45=cython.double)
    @cython.locals(r46=cython.double)
    @cython.locals(r47=cython.double)
    @cython.locals(r48=cython.double)
    @cython.locals(r49=cython.double)
    @cython.locals(r50=cython.double)
    @cython.locals(r51=cython.double)
    @cython.locals(r52=cython.double)
    @cython.locals(r53=cython.double)
    @cython.locals(r54=cython.double)
    @cython.locals(r55=cython.double)
    @cython.locals(r56=cython.double)
    @cython.locals(r57=cython.double)
    @cython.locals(r58=cython.double)
    @cython.locals(r59=cython.double)
    @cython.locals(r60=cython.double)
    @cython.locals(r61=cython.double)
    @cython.locals(r62=cython.double)
    @cython.locals(r63=cython.double)
    @cython.locals(r64=cython.double)
    @cython.locals(r65=cython.double)
    @cython.locals(r66=cython.double)
    @cython.locals(r67=cython.double)
    @cython.locals(r68=cython.double)
    @cython.locals(r69=cython.double)
    @cython.locals(r70=cython.double)
    @cython.locals(r71=cython.double)
    @cython.locals(r72=cython.double)
    @cython.locals(r73=cython.double)
    @cython.locals(r74=cython.double)
    @cython.locals(r75=cython.double)
    @cython.locals(r76=cython.double)
    @cython.locals(r77=cython.double)
    @cython.locals(r78=cython.double)
    @cython.locals(r79=cython.double)
    @cython.locals(r80=cython.double)
    @cython.locals(r81=cython.double)
    @cython.locals(r82=cython.double)
    @cython.locals(r83=cython.double)
    @cython.locals(r84=cython.double)
    @cython.locals(r85=cython.double)
    @cython.locals(r86=cython.double)
    @cython.locals(r87=cython.double)
    @cython.locals(r88=cython.double)
    @cython.locals(r89=cython.double)
    @cython.locals(r90=cython.double)
    @cython.locals(r91=cython.double)
    @cython.locals(r92=cython.double)
    @cython.locals(r93=cython.double)
    @cython.locals(r94=cython.double)
    @cython.locals(r95=cython.double)
    @cython.locals(r96=cython.double)
    @cython.locals(r97=cython.double)
    @cython.locals(r98=cython.double)
    @cython.locals(r99=cython.double)
    @cython.locals(r100=cython.double)
    @cython.locals(r101=cython.double)
    @cython.locals(r102=cython.double)
    @cython.locals(r103=cython.double)
    @cython.locals(r104=cython.double)
    @cython.locals(r105=cython.double)
    @cython.locals(r106=cython.double)
    @cython.locals(r107=cython.double)
    @cython.locals(r108=cython.double)
    @cython.locals(r109=cython.double)
    @cython.locals(r110=cython.double)
    @cython.locals(r111=cython.double)
    @cython.locals(r112=cython.double)
    @cython.locals(r113=cython.double)
    @cython.locals(r114=cython.double)
    @cython.locals(r115=cython.double)
    @cython.locals(r116=cython.double)
    @cython.locals(r117=cython.double)
    @cython.locals(r118=cython.double)
    @cython.locals(r119=cython.double)
    @cython.locals(r120=cython.double)
    @cython.locals(r121=cython.double)
    @cython.locals(r122=cython.double)
    @cython.locals(r123=cython.double)
    @cython.locals(r124=cython.double)
    @cython.locals(r125=cython.double)
    @cython.locals(r126=cython.double)
    @cython.locals(r127=cython.double)
    @cython.locals(r128=cython.double)
    @cython.locals(r129=cython.double)
    @cython.locals(r130=cython.double)
    @cython.locals(r131=cython.double)
    @cython.locals(r132=cython.double)
    @cython.locals(x0=cython.double, y0=cython.double)
    @cython.locals(x1=cython.double, y1=cython.double)
    @cython.locals(x2=cython.double, y2=cython.double)
    @cython.locals(x3=cython.double, y3=cython.double)
    def _curveToOne(self, p1, p2, p3):
        x0, y0 = self._getCurrentPoint()
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = p3

        r0 = 6 * y2
        r1 = r0 * x3
        r2 = 10 * y3
        r3 = r2 * x3
        r4 = 3 * y1
        r5 = 6 * x1
        r6 = 3 * x2
        r7 = 6 * y1
        r8 = 3 * y2
        r9 = x2**2
        r10 = 45 * r9
        r11 = r10 * y3
        r12 = x3**2
        r13 = r12 * y2
        r14 = r12 * y3
        r15 = 7 * y3
        r16 = 15 * x3
        r17 = r16 * x2
        r18 = x1**2
        r19 = 9 * r18
        r20 = x0**2
        r21 = 21 * y1
        r22 = 9 * r9
        r23 = r7 * x3
        r24 = 9 * y2
        r25 = r24 * x2 + r3
        r26 = 9 * x2
        r27 = x2 * y3
        r28 = -r26 * y1 + 15 * r27
        r29 = 3 * x1
        r30 = 45 * x1
        r31 = 12 * x3
        r32 = 45 * r18
        r33 = 5 * r12
        r34 = r8 * x3
        r35 = 105 * y0
        r36 = 30 * y0
        r37 = r36 * x2
        r38 = 5 * x3
        r39 = 15 * y3
        r40 = 5 * y3
        r41 = r40 * x3
        r42 = x2 * y2
        r43 = 18 * r42
        r44 = 45 * y1
        r45 = r41 + r43 + r44 * x1
        r46 = y2 * y3
        r47 = r46 * x3
        r48 = y2**2
        r49 = 45 * r48
        r50 = r49 * x3
        r51 = y3**2
        r52 = r51 * x3
        r53 = y1**2
        r54 = 9 * r53
        r55 = y0**2
        r56 = 21 * x1
        r57 = 6 * x2
        r58 = r16 * y2
        r59 = r39 * y2
        r60 = 9 * r48
        r61 = r6 * y3
        r62 = 3 * y3
        r63 = r36 * y2
        r64 = y1 * y3
        r65 = 45 * r53
        r66 = 5 * r51
        r67 = x2**3
        r68 = x3**3
        r69 = 630 * y2
        r70 = 126 * x3
        r71 = x1**3
        r72 = 126 * x2
        r73 = 63 * r9
        r74 = r73 * x3
        r75 = r15 * x3 + 15 * r42
        r76 = 630 * x1
        r77 = 14 * x3
        r78 = 21 * r27
        r79 = 42 * x1
        r80 = 42 * x2
        r81 = x1 * y2
        r82 = 63 * r42
        r83 = x1 * y1
        r84 = r41 + r82 + 378 * r83
        r85 = x2 * x3
        r86 = r85 * y1
        r87 = r27 * x3
        r88 = 27 * r9
        r89 = r88 * y2
        r90 = 42 * r14
        r91 = 90 * x1
        r92 = 189 * r18
        r93 = 378 * r18
        r94 = r12 * y1
        r95 = 252 * x1 * x2
        r96 = r79 * x3
        r97 = 30 * r85
        r98 = r83 * x3
        r99 = 30 * x3
        r100 = 42 * x3
        r101 = r42 * x1
        r102 = r10 * y2 + 14 * r14 + 126 * r18 * y1 + r81 * r99
        r103 = 378 * r48
        r104 = 18 * y1
        r105 = r104 * y2
        r106 = y0 * y1
        r107 = 252 * y2
        r108 = r107 * y0
        r109 = y0 * y3
        r110 = 42 * r64
        r111 = 378 * r53
        r112 = 63 * r48
        r113 = 27 * x2
        r114 = r27 * y2
        r115 = r113 * r48 + 42 * r52
        r116 = x3 * y3
        r117 = 54 * r42
        r118 = r51 * x1
        r119 = r51 * x2
        r120 = r48 * x1
        r121 = 21 * x3
        r122 = r64 * x1
        r123 = r81 * y3
        r124 = 30 * r27 * y1 + r49 * x2 + 14 * r52 + 126 * r53 * x1
        r125 = y2**3
        r126 = y3**3
        r127 = y1**3
        r128 = y0**3
        r129 = r51 * y2
        r130 = r112 * y3 + r21 * r51
        r131 = 189 * r53
        r132 = 90 * y2

        self.area += (
            -r1 / 20
            - r3 / 20
            - r4 * (x2 + x3) / 20
            + x0 * (r7 + r8 + 10 * y0 + y3) / 20
            + 3 * x1 * (y2 + y3) / 20
            + 3 * x2 * y3 / 10
            - y0 * (r5 + r6 + x3) / 20
        )
        self.momentX += (
            r11 / 840
            - r13 / 8
            - r14 / 3
            - r17 * (-r15 + r8) / 840
            + r19 * (r8 + 2 * y3) / 840
            + r20 * (r0 + r21 + 56 * y0 + y3) / 168
            + r29 * (-r23 + r25 + r28) / 840
            - r4 * (10 * r12 + r17 + r22) / 840
            + x0
            * (
                12 * r27
                + r30 * y2
                + r34
                - r35 * x1
                - r37
                - r38 * y0
                + r39 * x1
                - r4 * x3
                + r45
            )
            / 840
            - y0 * (r17 + r30 * x2 + r31 * x1 + r32 + r33 + 18 * r9) / 840
        )
        self.momentY += (
            -r4 * (r25 + r58) / 840
            - r47 / 8
            - r50 / 840
            - r52 / 6
            - r54 * (r6 + 2 * x3) / 840
            - r55 * (r56 + r57 + x3) / 168
            + x0
            * (
                r35 * y1
                + r40 * y0
                + r44 * y2
                + 18 * r48
                + 140 * r55
                + r59
                + r63
                + 12 * r64
                + r65
                + r66
            )
            / 840
            + x1 * (r24 * y1 + 10 * r51 + r59 + r60 + r7 * y3) / 280
            + x2 * y3 * (r15 + r8) / 56
            - y0 * (r16 * y1 + r31 * y2 + r44 * x2 + r45 + r61 - r62 * x1) / 840
        )
        self.momentXX += (
            -r12 * r72 * (-r40 + r8) / 9240
            + 3 * r18 * (r28 + r34 - r38 * y1 + r75) / 3080
            + r20
            * (
                r24 * x3
                - r72 * y0
                - r76 * y0
                - r77 * y0
                + r78
                + r79 * y3
                + r80 * y1
                + 210 * r81
                + r84
            )
            / 9240
            - r29
            * (
                r12 * r21
                + 14 * r13
                + r44 * r9
                - r73 * y3
                + 54 * r86
                - 84 * r87
                - r89
                - r90
            )
            / 9240
            - r4 * (70 * r12 * x2 + 27 * r67 + 42 * r68 + r74) / 9240
            + 3 * r67 * y3 / 220
            - r68 * r69 / 9240
            - r68 * y3 / 4
            - r70 * r9 * (-r62 + y2) / 9240
            + 3 * r71 * (r24 + r40) / 3080
            + x0**3 * (r24 + r44 + 165 * y0 + y3) / 660
            + x0
            * (
                r100 * r27
                + 162 * r101
                + r102
                + r11
                + 63 * r18 * y3
                + r27 * r91
                - r33 * y0
                - r37 * x3
                + r43 * x3
                - r73 * y0
                - r88 * y1
                + r92 * y2
                - r93 * y0
                - 9 * r94
                - r95 * y0
                - r96 * y0
                - r97 * y1
                - 18 * r98
                + r99 * x1 * y3
            )
            / 9240
            - y0
            * (
                r12 * r56
                + r12 * r80
                + r32 * x3
                + 45 * r67
                + 14 * r68
                + 126 * r71
                + r74
                + r85 * r91
                + 135 * r9 * x1
                + r92 * x2
            )
            / 9240
        )
        self.momentXY += (
            -r103 * r12 / 18480
            - r12 * r51 / 8
            - 3 * r14 * y2 / 44
            + 3 * r18 * (r105 + r2 * y1 + 18 * r46 + 15 * r48 + 7 * r51) / 6160
            + r20
            * (
                1260 * r106
                + r107 * y1
                + r108
                + 28 * r109
                + r110
                + r111
                + r112
                + 30 * r46
                + 2310 * r55
                + r66
            )
            / 18480
            - r54 * (7 * r12 + 18 * r85 + 15 * r9) / 18480
            - r55 * (r33 + r73 + r93 + r95 + r96 + r97) / 18480
            - r7 * (42 * r13 + r82 * x3 + 28 * r87 + r89 + r90) / 18480
            - 3 * r85 * (r48 - r66) / 220
            + 3 * r9 * y3 * (r62 + 2 * y2) / 440
            + x0
            * (
                -r1 * y0
                - 84 * r106 * x2
                + r109 * r56
                + 54 * r114
                + r117 * y1
                + 15 * r118
                + 21 * r119
                + 81 * r120
                + r121 * r46
                + 54 * r122
                + 60 * r123
                + r124
                - r21 * x3 * y0
                + r23 * y3
                - r54 * x3
                - r55 * r72
                - r55 * r76
                - r55 * r77
                + r57 * y0 * y3
                + r60 * x3
                + 84 * r81 * y0
                + 189 * r81 * y1
            )
            / 9240
            + x1
            * (
                r104 * r27
                - r105 * x3
                - r113 * r53
                + 63 * r114
                + r115
                - r16 * r53
                + 28 * r47
                + r51 * r80
            )
            / 3080
            - y0
            * (
                54 * r101
                + r102
                + r116 * r5
                + r117 * x3
                + 21 * r13
                - r19 * y3
                + r22 * y3
                + r78 * x3
                + 189 * r83 * x2
                + 60 * r86
                + 81 * r9 * y1
                + 15 * r94
                + 54 * r98
            )
            / 9240
        )
        self.momentYY += (
            -r103 * r116 / 9240
            - r125 * r70 / 9240
            - r126 * x3 / 12
            - 3 * r127 * (r26 + r38) / 3080
            - r128 * (r26 + r30 + x3) / 660
            - r4 * (r112 * x3 + r115 - 14 * r119 + 84 * r47) / 9240
            - r52 * r69 / 9240
            - r54 * (r58 + r61 + r75) / 9240
            - r55
            * (r100 * y1 + r121 * y2 + r26 * y3 + r79 * y2 + r84 + 210 * x2 * y1)
            / 9240
            + x0
            * (
                r108 * y1
                + r110 * y0
                + r111 * y0
                + r112 * y0
                + 45 * r125
                + 14 * r126
                + 126 * r127
                + 770 * r128
                + 42 * r129
                + r130
                + r131 * y2
                + r132 * r64
                + 135 * r48 * y1
                + 630 * r55 * y1
                + 126 * r55 * y2
                + 14 * r55 * y3
                + r63 * y3
                + r65 * y3
                + r66 * y0
            )
            / 9240
            + x1
            * (
                27 * r125
                + 42 * r126
                + 70 * r129
                + r130
                + r39 * r53
                + r44 * r48
                + 27 * r53 * y2
                + 54 * r64 * y2
            )
            / 3080
            + 3 * x2 * y3 * (r48 + r66 + r8 * y3) / 220
            - y0
            * (
                r100 * r46
                + 18 * r114
                - 9 * r118
                - 27 * r120
                - 18 * r122
                - 30 * r123
                + r124
                + r131 * x2
                + r132 * x3 * y1
                + 162 * r42 * y1
                + r50
                + 63 * r53 * x3
                + r64 * r99
            )
            / 9240
        )


if __name__ == "__main__":
    from fontTools.misc.symfont import x, y, printGreenPen

    printGreenPen(
        "MomentsPen",
        [
            ("area", 1),
            ("momentX", x),
            ("momentY", y),
            ("momentXX", x**2),
            ("momentXY", x * y),
            ("momentYY", y**2),
        ],
    )
