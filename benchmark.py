import time
import pandas as pd
import numpy as np

# We want to benchmark the difference between iterating with a list comprehension
# vs vectorized str.lower() method for pd.DataFrame column manipulation.

# Let's create a DataFrame with many columns to see the difference clearly.
# For a typical stock dataframe, the number of columns is small (e.g. 6-7).
# Let's benchmark for both a small DataFrame and a very large DataFrame.

def benchmark(num_cols, iterations):
    cols = [f"Col_{i}" for i in range(num_cols)]
    df = pd.DataFrame(columns=cols)

    start = time.time()
    for _ in range(iterations):
        _ = [str(c).lower() for c in df.columns]
    t1 = time.time() - start

    start = time.time()
    for _ in range(iterations):
        _ = df.columns.astype(str).str.lower()
    t2 = time.time() - start

    print(f"Num cols: {num_cols}, Iterations: {iterations}")
    print(f"List comprehension: {t1:.6f} s")
    print(f"Pandas str.lower(): {t2:.6f} s")
    print("-" * 30)

benchmark(10, 10000)
benchmark(100, 10000)
benchmark(1000, 10000)
