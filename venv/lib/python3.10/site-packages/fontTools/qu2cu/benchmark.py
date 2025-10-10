"""Benchmark the qu2cu algorithm performance."""

from .qu2cu import *
from fontTools.cu2qu import curve_to_quadratic
import random
import timeit

MAX_ERR = 0.5
NUM_CURVES = 5


def generate_curves(n):
    points = [
        tuple(float(random.randint(0, 2048)) for coord in range(2))
        for point in range(1 + 3 * n)
    ]
    curves = []
    for i in range(n):
        curves.append(tuple(points[i * 3 : i * 3 + 4]))
    return curves


def setup_quadratic_to_curves():
    curves = generate_curves(NUM_CURVES)
    quadratics = [curve_to_quadratic(curve, MAX_ERR) for curve in curves]
    return quadratics, MAX_ERR


def run_benchmark(module, function, setup_suffix="", repeat=25, number=1):
    setup_func = "setup_" + function
    if setup_suffix:
        print("%s with %s:" % (function, setup_suffix), end="")
        setup_func += "_" + setup_suffix
    else:
        print("%s:" % function, end="")

    def wrapper(function, setup_func):
        function = globals()[function]
        setup_func = globals()[setup_func]

        def wrapped():
            return function(*setup_func())

        return wrapped

    results = timeit.repeat(wrapper(function, setup_func), repeat=repeat, number=number)
    print("\t%5.1fus" % (min(results) * 1000000.0 / number))


def main():
    run_benchmark("qu2cu", "quadratic_to_curves")


if __name__ == "__main__":
    random.seed(1)
    main()
