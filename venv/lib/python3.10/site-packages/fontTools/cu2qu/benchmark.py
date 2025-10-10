"""Benchmark the cu2qu algorithm performance."""

from .cu2qu import *
import random
import timeit

MAX_ERR = 0.05


def generate_curve():
    return [
        tuple(float(random.randint(0, 2048)) for coord in range(2))
        for point in range(4)
    ]


def setup_curve_to_quadratic():
    return generate_curve(), MAX_ERR


def setup_curves_to_quadratic():
    num_curves = 3
    return ([generate_curve() for curve in range(num_curves)], [MAX_ERR] * num_curves)


def run_benchmark(module, function, setup_suffix="", repeat=5, number=1000):
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
    run_benchmark("cu2qu", "curve_to_quadratic")
    run_benchmark("cu2qu", "curves_to_quadratic")


if __name__ == "__main__":
    random.seed(1)
    main()
