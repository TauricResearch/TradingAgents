## 2024-05-24 - [Avoid Pandas Vectorized String Operations on Tiny Arrays]
**Learning:** While `df.columns.astype(str).str.lower()` is faster for large datasets (e.g., 1000+ columns), it is actually a micro-deoptimization for typical DataFrames with few columns. The overhead of pandas' `.str` accessor dispatch and Index object creation outweighs the raw iteration speed of a simple Python list comprehension `[str(c).lower() for c in df.columns]`.
**Action:** Do not replace list comprehensions with pandas vectorized string accessors when the array size is known to be very small (like DataFrame columns), unless the number of columns is explicitly known to be massive.

## 2024-05-25 - [Avoid stdlib statistics for math ops on performance-critical code]
**Learning:** The Python standard library `statistics` module (e.g., `statistics.mean`, `statistics.stdev`, `statistics.pvariance`) has significant overhead compared to simple built-in math operations (like `sum()` and generator expressions). Benchmarks showed an ~10x-14x performance improvement when replacing `statistics` functions with simple, pure-Python implementations using `sum()` and `len()`.
**Action:** When performing calculations in performance-sensitive areas (like portfolio risk evaluation over many ticks/prices), use built-in operations rather than the `statistics` module.
