from fontTools.pens.basePen import BasePen
from functools import partial
from itertools import count
import sympy as sp
import sys

n = 3  # Max Bezier degree; 3 for cubic, 2 for quadratic

t, x, y = sp.symbols("t x y", real=True)
c = sp.symbols("c", real=False)  # Complex representation instead of x/y

X = tuple(sp.symbols("x:%d" % (n + 1), real=True))
Y = tuple(sp.symbols("y:%d" % (n + 1), real=True))
P = tuple(zip(*(sp.symbols("p:%d[%s]" % (n + 1, w), real=True) for w in "01")))
C = tuple(sp.symbols("c:%d" % (n + 1), real=False))

# Cubic Bernstein basis functions
BinomialCoefficient = [(1, 0)]
for i in range(1, n + 1):
    last = BinomialCoefficient[-1]
    this = tuple(last[j - 1] + last[j] for j in range(len(last))) + (0,)
    BinomialCoefficient.append(this)
BinomialCoefficient = tuple(tuple(item[:-1]) for item in BinomialCoefficient)
del last, this

BernsteinPolynomial = tuple(
    tuple(c * t**i * (1 - t) ** (n - i) for i, c in enumerate(coeffs))
    for n, coeffs in enumerate(BinomialCoefficient)
)

BezierCurve = tuple(
    tuple(
        sum(P[i][j] * bernstein for i, bernstein in enumerate(bernsteins))
        for j in range(2)
    )
    for n, bernsteins in enumerate(BernsteinPolynomial)
)
BezierCurveC = tuple(
    sum(C[i] * bernstein for i, bernstein in enumerate(bernsteins))
    for n, bernsteins in enumerate(BernsteinPolynomial)
)


def green(f, curveXY):
    f = -sp.integrate(sp.sympify(f), y)
    f = f.subs({x: curveXY[0], y: curveXY[1]})
    f = sp.integrate(f * sp.diff(curveXY[0], t), (t, 0, 1))
    return f


class _BezierFuncsLazy(dict):
    def __init__(self, symfunc):
        self._symfunc = symfunc
        self._bezfuncs = {}

    def __missing__(self, i):
        args = ["p%d" % d for d in range(i + 1)]
        f = green(self._symfunc, BezierCurve[i])
        f = sp.gcd_terms(f.collect(sum(P, ())))  # Optimize
        return sp.lambdify(args, f)


class GreenPen(BasePen):
    _BezierFuncs = {}

    @classmethod
    def _getGreenBezierFuncs(celf, func):
        funcstr = str(func)
        if not funcstr in celf._BezierFuncs:
            celf._BezierFuncs[funcstr] = _BezierFuncsLazy(func)
        return celf._BezierFuncs[funcstr]

    def __init__(self, func, glyphset=None):
        BasePen.__init__(self, glyphset)
        self._funcs = self._getGreenBezierFuncs(func)
        self.value = 0

    def _moveTo(self, p0):
        self._startPoint = p0

    def _closePath(self):
        p0 = self._getCurrentPoint()
        if p0 != self._startPoint:
            self._lineTo(self._startPoint)

    def _endPath(self):
        p0 = self._getCurrentPoint()
        if p0 != self._startPoint:
            # Green theorem is not defined on open contours.
            raise NotImplementedError

    def _lineTo(self, p1):
        p0 = self._getCurrentPoint()
        self.value += self._funcs[1](p0, p1)

    def _qCurveToOne(self, p1, p2):
        p0 = self._getCurrentPoint()
        self.value += self._funcs[2](p0, p1, p2)

    def _curveToOne(self, p1, p2, p3):
        p0 = self._getCurrentPoint()
        self.value += self._funcs[3](p0, p1, p2, p3)


# Sample pens.
# Do not use this in real code.
# Use fontTools.pens.momentsPen.MomentsPen instead.
AreaPen = partial(GreenPen, func=1)
MomentXPen = partial(GreenPen, func=x)
MomentYPen = partial(GreenPen, func=y)
MomentXXPen = partial(GreenPen, func=x * x)
MomentYYPen = partial(GreenPen, func=y * y)
MomentXYPen = partial(GreenPen, func=x * y)


def printGreenPen(penName, funcs, file=sys.stdout, docstring=None):
    if docstring is not None:
        print('"""%s"""' % docstring)

    print(
        """from fontTools.pens.basePen import BasePen, OpenContourError
try:
	import cython
except (AttributeError, ImportError):
	# if cython not installed, use mock module with no-op decorators and types
	from fontTools.misc import cython
COMPILED = cython.compiled


__all__ = ["%s"]

class %s(BasePen):

	def __init__(self, glyphset=None):
		BasePen.__init__(self, glyphset)
"""
        % (penName, penName),
        file=file,
    )
    for name, f in funcs:
        print("		self.%s = 0" % name, file=file)
    print(
        """
	def _moveTo(self, p0):
		self._startPoint = p0

	def _closePath(self):
		p0 = self._getCurrentPoint()
		if p0 != self._startPoint:
			self._lineTo(self._startPoint)

	def _endPath(self):
		p0 = self._getCurrentPoint()
		if p0 != self._startPoint:
			raise OpenContourError(
							"Glyph statistics is not defined on open contours."
			)
""",
        end="",
        file=file,
    )

    for n in (1, 2, 3):
        subs = {P[i][j]: [X, Y][j][i] for i in range(n + 1) for j in range(2)}
        greens = [green(f, BezierCurve[n]) for name, f in funcs]
        greens = [sp.gcd_terms(f.collect(sum(P, ()))) for f in greens]  # Optimize
        greens = [f.subs(subs) for f in greens]  # Convert to p to x/y
        defs, exprs = sp.cse(
            greens,
            optimizations="basic",
            symbols=(sp.Symbol("r%d" % i) for i in count()),
        )

        print()
        for name, value in defs:
            print("	@cython.locals(%s=cython.double)" % name, file=file)
        if n == 1:
            print(
                """\
	@cython.locals(x0=cython.double, y0=cython.double)
	@cython.locals(x1=cython.double, y1=cython.double)
	def _lineTo(self, p1):
		x0,y0 = self._getCurrentPoint()
		x1,y1 = p1
""",
                file=file,
            )
        elif n == 2:
            print(
                """\
	@cython.locals(x0=cython.double, y0=cython.double)
	@cython.locals(x1=cython.double, y1=cython.double)
	@cython.locals(x2=cython.double, y2=cython.double)
	def _qCurveToOne(self, p1, p2):
		x0,y0 = self._getCurrentPoint()
		x1,y1 = p1
		x2,y2 = p2
""",
                file=file,
            )
        elif n == 3:
            print(
                """\
	@cython.locals(x0=cython.double, y0=cython.double)
	@cython.locals(x1=cython.double, y1=cython.double)
	@cython.locals(x2=cython.double, y2=cython.double)
	@cython.locals(x3=cython.double, y3=cython.double)
	def _curveToOne(self, p1, p2, p3):
		x0,y0 = self._getCurrentPoint()
		x1,y1 = p1
		x2,y2 = p2
		x3,y3 = p3
""",
                file=file,
            )
        for name, value in defs:
            print("		%s = %s" % (name, value), file=file)

        print(file=file)
        for name, value in zip([f[0] for f in funcs], exprs):
            print("		self.%s += %s" % (name, value), file=file)

    print(
        """
if __name__ == '__main__':
	from fontTools.misc.symfont import x, y, printGreenPen
	printGreenPen('%s', ["""
        % penName,
        file=file,
    )
    for name, f in funcs:
        print("		      ('%s', %s)," % (name, str(f)), file=file)
    print("		     ])", file=file)


if __name__ == "__main__":
    import sys

    if sys.argv[1:]:
        penName = sys.argv[1]
        funcs = [(name, eval(f)) for name, f in zip(sys.argv[2::2], sys.argv[3::2])]
        printGreenPen(penName, funcs, file=sys.stdout)
